import ast
import os
import re
from typing import Any, Dict, Optional, List, Tuple


def _split_keywords(value):
    if not value:
        return []
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    return [str(x).strip() for x in value if str(x).strip()]


def _path_allowed(file_path: str, include_keywords=None, exclude_keywords=None) -> bool:
    normalized = file_path.replace("\\", "/").lower()
    include_keywords = [x.lower() for x in _split_keywords(include_keywords)]
    exclude_keywords = [x.lower() for x in _split_keywords(exclude_keywords)]

    if exclude_keywords and any(k in normalized for k in exclude_keywords):
        return False
    if include_keywords and not any(k in normalized for k in include_keywords):
        return False
    return True


def _walk_files(code_dir: str, suffix: str, include_keywords=None, exclude_keywords=None):
    for root, _, files in os.walk(code_dir):
        for name in files:
            if not name.endswith(suffix):
                continue
            file_path = os.path.join(root, name)
            if _path_allowed(file_path, include_keywords, exclude_keywords):
                yield file_path, name


def empty_result(language: str = "unknown") -> Dict[str, Any]:
    return {
        "matched": False,
        "source_file": "",
        "function_name": "",
        "status_codes": [],
        "business_codes": [],
        "exception_messages": [],
        "enum_or_constant_hints": [],
        "validation_hints": [],
        "validation_rules": [],
        "request_class": "",
        "logic_snippet": "",
        "language": language,
    }


# =========================
# Java Spring Boot 代码扫描
# =========================
def _clean_mapping_value(value: str) -> str:
    value = (value or "").strip().strip('"').strip("'")
    if not value:
        return ""
    return value if value.startswith("/") else "/" + value


def java_mapping_to_swagger_path(class_mapping: str, method_mapping: str) -> str:
    joined = _clean_mapping_value(class_mapping).rstrip("/") + _clean_mapping_value(method_mapping)
    joined = re.sub(r"/+", "/", joined)
    return joined or "/"


def extract_java_annotation_values(annotation_args: str) -> List[str]:
    """提取 Spring Mapping 注解里的路径。

    兼容：
        @GetMapping
        @GetMapping("/x")
        @GetMapping(value = "/x")
        @GetMapping(path = "/x")
        @GetMapping(value = { "/", "/{userId}" })
        @GetMapping({ "/", "/{userId}" })

    注意：路径变量本身也包含大括号，例如 "/{userId}"。
    旧实现用正则找 { ... }，会在路径变量的 } 处提前截断，导致只能识别 "/"。
    这里直接提取注解参数中的字符串字面量，更稳。
    """
    if not annotation_args:
        return [""]

    text = annotation_args.strip()
    values = re.findall(r'"([^"]*)"', text)
    if values:
        return values

    return [""]

def extract_java_annotation_value(annotation_args: str) -> str:
    values = extract_java_annotation_values(annotation_args)
    return values[0] if values else ""


def _normalize_api_path(path: str) -> str:
    path = re.sub(r"/+", "/", path or "/")
    if len(path) > 1:
        path = path.rstrip("/")
    return path or "/"


def _path_matches(candidate: str, target: str) -> bool:
    c = _normalize_api_path(candidate)
    t = _normalize_api_path(target)
    if c == t:
        return True

    # 兼容 Swagger 与 Java 中路径变量名称不同的情况
    c_generic = re.sub(r'\{[^/{}]+\}', '{}', c)
    t_generic = re.sub(r'\{[^/{}]+\}', '{}', t)
    return c_generic == t_generic

def java_http_status_to_code(status_name: str) -> Optional[int]:
    mapping = {
        "OK": 200,
        "CREATED": 201,
        "NO_CONTENT": 204,
        "BAD_REQUEST": 400,
        "UNAUTHORIZED": 401,
        "FORBIDDEN": 403,
        "NOT_FOUND": 404,
        "METHOD_NOT_ALLOWED": 405,
        "CONFLICT": 409,
        "UNPROCESSABLE_ENTITY": 422,
        "INTERNAL_SERVER_ERROR": 500,
    }
    return mapping.get(status_name)


def _find_java_method_body(text: str, brace_index: int) -> str:
    brace_count = 0
    body_end = brace_index
    for i in range(brace_index, len(text)):
        if text[i] == "{":
            brace_count += 1
        elif text[i] == "}":
            brace_count -= 1
            if brace_count == 0:
                body_end = i + 1
                break
    return text[brace_index:body_end]


def _parse_annotation_args(args: str) -> Dict[str, Any]:
    args = args or ""
    result: Dict[str, Any] = {}

    msg = re.search(r'message\s*=\s*"([^"]*)"', args)
    if msg:
        result["message"] = msg.group(1)

    value = re.search(r'(?:value\s*=\s*)?"?([\w.|+\\-]+)"?', args.strip().strip("()"))
    if value and "message" not in value.group(0):
        result["value"] = value.group(1)

    for key in ["min", "max", "regexp"]:
        m = re.search(key + r'\s*=\s*"?([^,")]+)"?', args)
        if m:
            result[key] = m.group(1)
    return result


def _extract_java_validation_rules_by_class(code_dir: str, include_keywords=None, exclude_keywords=None) -> Dict[str, List[Dict[str, Any]]]:
    rules_by_class: Dict[str, List[Dict[str, Any]]] = {}
    field_re = re.compile(
        r'((?:\s*@(NotNull|NotBlank|NotEmpty|Size|Min|Max|Pattern|Email|DecimalMin|DecimalMax)\s*(?:\([^)]*\))?\s*)+)\s*'
        r'private\s+([\w<>.]+)\s+(\w+)\s*;',
        re.S,
    )
    ann_re = re.compile(r'@(NotNull|NotBlank|NotEmpty|Size|Min|Max|Pattern|Email|DecimalMin|DecimalMax)\s*(\([^)]*\))?', re.S)

    for file_path, name in _walk_files(code_dir, ".java", include_keywords, exclude_keywords):
            try:
                text = open(file_path, "r", encoding="utf-8").read()
            except Exception:
                continue

            class_match = re.search(r'public\s+class\s+(\w+)', text)
            if not class_match:
                continue
            class_name = class_match.group(1)

            field_types = {fm.group(2): fm.group(1) for fm in re.finditer(r'private\s+([\w<>.]+)\s+(\w+)\s*;', text)}

            for m in field_re.finditer(text):
                annotations_block = m.group(1)
                field_type = m.group(3)
                field_name = m.group(4)
                for ann in ann_re.finditer(annotations_block):
                    ann_name = ann.group(1)
                    ann_args = ann.group(2) or ""
                    rule = {
                        "class_name": class_name,
                        "field": field_name,
                        "type": field_type,
                        "annotation": ann_name,
                        "location": "body",
                        "source_file": name,
                    }
                    rule.update(_parse_annotation_args(ann_args))
                    rules_by_class.setdefault(class_name, []).append(rule)

            # RuoYi 等项目常把校验注解写在 getter 上，而不是字段上。
            getter_re = re.compile(
                r'((?:\s*@(NotNull|NotBlank|NotEmpty|Size|Min|Max|Pattern|Email|DecimalMin|DecimalMax)\s*(?:\([^)]*\))?\s*)+)\s*'
                r'public\s+([\w<>.]+)\s+get([A-Z]\w*)\s*\(\s*\)\s*\{',
                re.S,
            )
            for gm in getter_re.finditer(text):
                annotations_block = gm.group(1)
                return_type = gm.group(3)
                prop = gm.group(4)[0].lower() + gm.group(4)[1:]
                field_type = field_types.get(prop, return_type)
                for ann in ann_re.finditer(annotations_block):
                    ann_name = ann.group(1)
                    ann_args = ann.group(2) or ""
                    rule = {
                        "class_name": class_name,
                        "field": prop,
                        "type": field_type,
                        "annotation": ann_name,
                        "location": "body",
                        "source_file": name,
                    }
                    rule.update(_parse_annotation_args(ann_args))
                    rules_by_class.setdefault(class_name, []).append(rule)
    return rules_by_class


def _validation_hints_from_rules(rules: List[Dict[str, Any]]) -> List[str]:
    hints = []
    for r in rules:
        args = []
        for key in ["value", "min", "max", "regexp", "message"]:
            if r.get(key) not in (None, ""):
                args.append(f"{key}={r.get(key)}")
        arg_text = f"({', '.join(args)})" if args else ""
        hints.append(f"{r.get('field')}: @{r.get('annotation')}{arg_text}, type={r.get('type')}, class={r.get('class_name')}")
    return hints


def _extract_request_body_class(snippet: str) -> str:
    m = re.search(r'@RequestBody\s+(\w+)\s+\w+', snippet)
    return m.group(1) if m else ""


def _extract_method_param_validation_rules(snippet: str) -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []
    # 处理 @RequestParam(name = "page") @Min(1) Integer page 这类参数校验
    param_re = re.compile(
        r'@(RequestParam|PathVariable)\s*(?:\(([^)]*)\))?\s*'
        r'(?:@(Min|Max|NotNull|NotBlank|NotEmpty|Size|Pattern|Email|DecimalMin|DecimalMax)\s*(\([^)]*\))?\s*)?'
        r'([\w<>.]+)\s+(\w+)',
        re.S,
    )
    for m in param_re.finditer(snippet):
        location_ann, location_args, ann_name, ann_args, typ, param_name = m.groups()
        location = "query" if location_ann == "RequestParam" else "path"
        real_name = param_name
        name_match = re.search(r'(?:name|value)\s*=\s*"([^"]+)"', location_args or "")
        if name_match:
            real_name = name_match.group(1)
        elif location_args and '"' in location_args:
            q = re.search(r'"([^"]+)"', location_args)
            if q:
                real_name = q.group(1)
        if ann_name:
            rule = {
                "class_name": "method_param",
                "field": real_name,
                "type": typ,
                "annotation": ann_name,
                "location": location,
                "source_file": "controller_method",
            }
            rule.update(_parse_annotation_args(ann_args or ""))
            rules.append(rule)
        # 无校验注解时也补一个类型错误用例线索，路径参数/查询参数很有用
        elif typ in {"Integer", "Long", "BigDecimal", "Double", "Float"}:
            rules.append({
                "class_name": "method_param",
                "field": real_name,
                "type": typ,
                "annotation": "TypeHint",
                "location": location,
                "source_file": "controller_method",
            })
    return rules


def _extract_class_mapping(text: str) -> str:
    # 先找到 class 之前最后一个 @RequestMapping，兼容 @RestController / 注释 / 其他注解夹在中间
    class_match = re.search(r'\bclass\s+\w+', text)
    if not class_match:
        return ""

    before_class = text[:class_match.start()]
    matches = list(re.finditer(r'@RequestMapping\s*(?:\((.*?)\))?', before_class, re.S))
    if not matches:
        return ""

    return extract_java_annotation_value(matches[-1].group(1) or "")

def _read_annotation_args(text: str, open_paren_index: int) -> Tuple[str, int]:
    """读取注解括号内容，支持字符串中的 {userId}，避免正则提前截断。"""
    depth = 0
    in_string = False
    escape = False
    start = open_paren_index + 1

    for i in range(open_paren_index, len(text)):
        ch = text[i]

        if escape:
            escape = False
            continue

        if ch == "\\":
            escape = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[start:i], i + 1

    return "", open_paren_index


def _iter_java_mapped_methods(text: str, method_annotation: str):
    """遍历 Controller 中指定 HTTP Mapping 的方法。

    重点兼容 RuoYi 这类写法：
        @GetMapping(value = { "/", "/{userId}" })
        @GetMapping("/authRole/{userId}")
        @DeleteMapping("/{userIds}")
    """
    ann_pattern = re.compile(r'@' + re.escape(method_annotation) + r'\b')

    for ann in ann_pattern.finditer(text):
        pos = ann.end()
        while pos < len(text) and text[pos].isspace():
            pos += 1

        args = ""
        end_pos = pos
        if pos < len(text) and text[pos] == "(":
            args, end_pos = _read_annotation_args(text, pos)

        method_decl = re.search(
            r'(?:public|private|protected)\s+[\w<>\[\],.? \t]+\s+(\w+)\s*\([^;{]*\)\s*(?:throws\s+[^{]+)?\{',
            text[end_pos:],
            re.S,
        )
        if not method_decl:
            continue

        method_name = method_decl.group(1)
        brace_index = end_pos + method_decl.end() - 1
        method_start = ann.start()

        class MethodMatch:
            def __init__(self, start, end, name):
                self._start = start
                self._end = end
                self._name = name

            def start(self):
                return self._start

            def end(self):
                return self._end

            def group(self, idx):
                return self._name if idx == 2 else None

        for mapping_value in extract_java_annotation_values(args):
            yield MethodMatch(method_start, brace_index + 1, method_name), mapping_value

def _find_service_method_body(code_dir: str, method_name: str, include_keywords=None, exclude_keywords=None) -> str:
    if not method_name:
        return ""
    pattern = re.compile(r'(?:public|private|protected)?\s+[\w<>?,.\s]+\s+' + re.escape(method_name) + r'\s*\([^)]*\)\s*\{', re.S)
    for file_path, name in _walk_files(code_dir, ".java", include_keywords, exclude_keywords):
            if "Service" not in name:
                continue
            try:
                text = open(file_path, "r", encoding="utf-8").read()
            except Exception:
                continue
            m = pattern.search(text)
            if m:
                return text[m.start(): m.end() - 1] + _find_java_method_body(text, m.end() - 1)
    return ""


def _append_called_service_methods(code_dir: str, controller_snippet: str, include_keywords=None, exclude_keywords=None) -> str:
    snippets = []
    for m in re.finditer(r'\w+Service\.(\w+)\s*\(', controller_snippet):
        body = _find_service_method_body(code_dir, m.group(1), include_keywords, exclude_keywords)
        if body:
            snippets.append("\n// Related service method:\n" + body)
    if not snippets:
        return controller_snippet
    return controller_snippet + "\n" + "\n".join(snippets)


def _extract_java_hints(snippet: str) -> Tuple[set, set, List[str], List[str]]:
    status_codes = set()
    business_codes = set()
    messages: List[str] = []
    hints: List[str] = []

    # throw new BusinessException(1001, "用户不存在") / throw new ServiceException("xxx")
    for sm in re.finditer(r'new\s+BusinessException\s*\(\s*(\d+)\s*,\s*"([^"]*)"\s*\)', snippet):
        business_codes.add(int(sm.group(1)))
        messages.append(sm.group(2))
        status_codes.add(400)

    for sm in re.finditer(r'new\s+ServiceException\s*\(\s*(?:String\.format\s*\()?"([^"]*)"', snippet):
        business_codes.add(500)
        messages.append(sm.group(1))
        status_codes.add(200)

    # Result.fail(1001, "xxx")
    for sm in re.finditer(r'Result\.fail\s*\(\s*(\d+)\s*,\s*"([^"]*)"', snippet):
        business_codes.add(int(sm.group(1)))
        messages.append(sm.group(2))

    # new Result<>(200, "ok", data)
    for sm in re.finditer(r'new\s+Result\s*<[^>]*>\s*\(\s*(\d+)\s*,\s*"([^"]*)"', snippet):
        business_codes.add(int(sm.group(1)))
        messages.append(sm.group(2))

    # 常见统一返回包装：Result/AjaxResult/BaseController success/toAjax/error
    if (re.search(r'Result\.ok\s*\(', snippet) or re.search(r'ApiResult\.success\s*\(', snippet)
            or re.search(r'AjaxResult\.success\s*\(', snippet) or re.search(r'\bsuccess\s*\(', snippet)
            or re.search(r'\btoAjax\s*\(', snippet)):
        business_codes.add(200)
        messages.append("success")
        status_codes.add(200)

    if re.search(r'AjaxResult\.error\s*\(', snippet) or re.search(r'\berror\s*\(', snippet):
        business_codes.add(500)
        messages.append("error")
        status_codes.add(200)

    # throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "xxx")
    for sm in re.finditer(r'HttpStatus\.([A-Z_]+)\s*,\s*"([^"]*)"', snippet):
        code = java_http_status_to_code(sm.group(1))
        if code is not None:
            status_codes.add(code)
        messages.append(sm.group(2))

    # @ResponseStatus(HttpStatus.BAD_REQUEST)
    for sm in re.finditer(r'@ResponseStatus\s*\(\s*HttpStatus\.([A-Z_]+)\s*\)', snippet):
        code = java_http_status_to_code(sm.group(1))
        if code is not None:
            status_codes.add(code)

    for hm in re.finditer(r'if\s*\((.*?)\)\s*(?:\{|throw|return)', snippet, re.S):
        condition = re.sub(r'\s+', ' ', hm.group(1)).strip()
        if condition:
            hints.append(condition)

    return status_codes, business_codes, messages, hints


def scan_java_code_for_endpoint(code_dir: str, path: str, method: str, include_keywords=None, exclude_keywords=None) -> Dict[str, Any]:
    result = empty_result("java")
    if not os.path.exists(code_dir):
        return result

    method_annotation = {
        "GET": "GetMapping",
        "POST": "PostMapping",
        "PUT": "PutMapping",
        "DELETE": "DeleteMapping",
        "PATCH": "PatchMapping",
    }.get(method.upper())
    if not method_annotation:
        return result

    validation_rules_by_class = _extract_java_validation_rules_by_class(code_dir, include_keywords, exclude_keywords)

    for file_path, name in _walk_files(code_dir, ".java", include_keywords, exclude_keywords):
            if "Controller" not in name:
                continue
            try:
                text = open(file_path, "r", encoding="utf-8").read()
            except Exception:
                continue

            class_mapping = _extract_class_mapping(text)
            for m, method_mapping in _iter_java_mapped_methods(text, method_annotation):
                full_path = java_mapping_to_swagger_path(class_mapping, method_mapping)
                if not _path_matches(full_path, path):
                    continue

                controller_snippet = text[m.start(): m.end() - 1] + _find_java_method_body(text, m.end() - 1)
                snippet = _append_called_service_methods(code_dir, controller_snippet, include_keywords, exclude_keywords)
                status_codes, business_codes, messages, hints = _extract_java_hints(snippet)
                request_class = _extract_request_body_class(controller_snippet)
                validation_rules = list(validation_rules_by_class.get(request_class, []))
                validation_rules.extend(_extract_method_param_validation_rules(controller_snippet))
                validation_hints = _validation_hints_from_rules(validation_rules)

                result.update({
                    "matched": True,
                    "source_file": file_path,
                    "function_name": m.group(2),
                    "request_class": request_class,
                    "logic_snippet": snippet[:5000],
                    "validation_hints": validation_hints,
                    "validation_rules": validation_rules,
                    "status_codes": sorted(status_codes),
                    "business_codes": sorted(business_codes),
                    "exception_messages": list(dict.fromkeys(messages)),
                    "enum_or_constant_hints": list(dict.fromkeys(hints)),
                })
                return result
    return result


# =========================
# Python FastAPI 兼容扫描
# =========================
def scan_python_code_for_endpoint(code_dir: str, path: str, method: str, include_keywords=None, exclude_keywords=None) -> Dict[str, Any]:
    result = empty_result("python")
    if not os.path.exists(code_dir):
        return result

    decorator_path = path
    method_lower = method.lower()

    for file_path, name in _walk_files(code_dir, ".py", include_keywords, exclude_keywords):
            try:
                text = open(file_path, "r", encoding="utf-8").read()
            except Exception:
                continue

            try:
                tree = ast.parse(text)
            except Exception:
                continue

            lines = text.splitlines()
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue

                matched = False
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        if dec.func.attr.lower() == method_lower and dec.args:
                            first_arg = dec.args[0]
                            if isinstance(first_arg, ast.Constant) and first_arg.value == decorator_path:
                                matched = True
                                break
                if not matched:
                    continue

                result["matched"] = True
                result["source_file"] = file_path
                result["function_name"] = node.name

                start = max(node.lineno - 1, 0)
                end = getattr(node, "end_lineno", node.lineno)
                snippet = "\n".join(lines[start:end])
                result["logic_snippet"] = snippet[:2500]

                status_codes = set()
                business_codes = set()
                messages = []
                hints = []

                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        func_name = ""
                        if isinstance(child.func, ast.Name):
                            func_name = child.func.id
                        elif isinstance(child.func, ast.Attribute):
                            func_name = child.func.attr

                        if func_name == "HTTPException":
                            for kw in child.keywords:
                                if kw.arg == "status_code" and isinstance(kw.value, ast.Constant):
                                    status_codes.add(kw.value.value)
                                if kw.arg == "detail" and isinstance(kw.value, ast.Constant):
                                    messages.append(str(kw.value.value))

                    if isinstance(child, ast.Return) and isinstance(child.value, ast.Dict):
                        for k, v in zip(child.value.keys, child.value.values):
                            if isinstance(k, ast.Constant) and k.value == "code" and isinstance(v, ast.Constant):
                                business_codes.add(v.value)
                            if isinstance(k, ast.Constant) and k.value == "message" and isinstance(v, ast.Constant):
                                messages.append(str(v.value))

                    if isinstance(child, ast.Compare):
                        try:
                            hints.append(ast.unparse(child))
                        except Exception:
                            pass

                result["status_codes"] = sorted(status_codes)
                result["business_codes"] = sorted(business_codes)
                result["exception_messages"] = list(dict.fromkeys(messages))
                result["enum_or_constant_hints"] = list(dict.fromkeys(hints))
                return result
    return result


def scan_code_for_endpoint(code_dir: str, path: str, method: str, include_keywords=None, exclude_keywords=None) -> Dict[str, Any]:
    java_result = scan_java_code_for_endpoint(code_dir, path, method, include_keywords, exclude_keywords)
    if java_result.get("matched"):
        return java_result
    return scan_python_code_for_endpoint(code_dir, path, method, include_keywords, exclude_keywords)
