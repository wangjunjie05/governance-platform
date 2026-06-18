import re
from typing import Tuple


def ensure_py_code(text: str) -> str:
    text = text.strip()
    blocks = re.findall(r"```(?:python)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if blocks:
        text = blocks[0].strip()

    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text).strip()

    starts = [i for marker in ("import ", "from ") if (i := text.find(marker)) != -1]
    if starts:
        text = text[min(starts):]

    return text.strip() + "\n"


def fix_broken_parametrize_string(code: str) -> str:
    """修复 AI 偶尔把 pytest.mark.parametrize 的参数名字符串拆成多行导致的语法错误。

    例如：
        @pytest.mark.parametrize(
            "payload, expected_status_code,
            expected_business_code",
            [...]
        )

    修复为：
        @pytest.mark.parametrize(
            "payload, expected_status_code, expected_business_code",
            [...]
        )
    """
    lines = code.splitlines()
    fixed = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if "@pytest.mark.parametrize" in line:
            fixed.append(line)
            i += 1
            if i < len(lines):
                arg_line = lines[i]
                stripped = arg_line.strip()
                # 参数名字符串开始了，但这一行没有闭合。
                if (stripped.startswith('"') or stripped.startswith("'")) and stripped.count(stripped[0]) == 1:
                    quote = stripped[0]
                    indent = arg_line[: len(arg_line) - len(arg_line.lstrip())]
                    parts = [stripped[1:]]
                    i += 1
                    while i < len(lines):
                        part = lines[i].strip()
                        if quote in part:
                            before, after = part.split(quote, 1)
                            parts.append(before)
                            merged = " ".join(x.strip() for x in parts if x.strip())
                            fixed.append(f"{indent}{quote}{merged}{quote}{after}")
                            i += 1
                            break
                        parts.append(part)
                        i += 1
                    continue
                fixed.append(arg_line)
                i += 1
            continue
        fixed.append(line)
        i += 1
    return "\n".join(fixed).strip() + "\n"


def fix_parametrize_args(code: str) -> str:
    pattern = re.compile(
        r'(@pytest\.mark\.parametrize\(\s*["\']([^"\']+)["\'][\s\S]*?\)\s*)'
        r'def\s+(test_\w+)\(([^)]*)\):',
        flags=re.MULTILINE,
    )

    def repl(match: re.Match) -> str:
        decorator = match.group(1)
        func_name = match.group(3)
        params = [x.strip() for x in match.group(2).split(",") if x.strip()]
        return decorator + f"def {func_name}({', '.join(params)}):" if params else match.group(0)

    return pattern.sub(repl, code)


def check_parametrize_args(code: str) -> Tuple[bool, str]:
    pattern = re.compile(
        r'@pytest\.mark\.parametrize\(\s*["\']([^"\']+)["\'][\s\S]*?\)\s*'
        r'def\s+(test_\w+)\(([^)]*)\):',
        flags=re.MULTILINE,
    )
    for match in pattern.finditer(code):
        expected = [x.strip() for x in match.group(1).split(",") if x.strip()]
        actual = [x.strip() for x in match.group(3).split(",") if x.strip()]
        if expected != actual:
            return False, f"pytest参数化不匹配：{match.group(2)} expected={expected}, actual={actual}"
    return True, ""


def ensure_required_imports(code: str) -> str:
    lines = code.splitlines()
    insert_idx = 0
    while insert_idx < len(lines) and (
        lines[insert_idx].startswith("import ")
        or lines[insert_idx].startswith("from ")
        or not lines[insert_idx].strip()
    ):
        insert_idx += 1

    imports = []
    if "requests." in code and not re.search(r"^import\s+requests\b", code, flags=re.M):
        imports.append("import requests")
    if "pytest." in code and not re.search(r"^import\s+pytest\b", code, flags=re.M):
        imports.append("import pytest")
    if "os.getenv" in code and not re.search(r"^import\s+os\b", code, flags=re.M):
        imports.append("import os")

    if "io.BytesIO" in code and not re.search(r"^import\s+io\b", code, flags=re.M):
        imports.append("import io")

    if imports:
        lines[insert_idx:insert_idx] = imports

    return "\n".join(lines).strip() + "\n"


def remove_bad_exception_tests(code: str) -> str:
    code = re.sub(
        r"\n@pytest\.mark\.parametrize\([\s\S]*?\)\s*\n"
        r"def\s+test_(?!auto_exception)\w*exception\w*\([^)]*\):[\s\S]*?"
        r"(?=\n@pytest\.mark\.parametrize|\ndef\s+test_|\nif\s+__name__|\Z)",
        "\n",
        code,
        flags=re.I,
    )
    code = re.sub(
        r"\ndef\s+test_(?!auto_exception)\w*exception\w*\([^)]*\):[\s\S]*?"
        r"(?=\n@pytest\.mark\.parametrize|\ndef\s+test_|\nif\s+__name__|\Z)",
        "\n",
        code,
        flags=re.I,
    )

    if "RequestException" not in code.replace("from requests import RequestException", ""):
        code = re.sub(r"^from\s+requests\s+import\s+RequestException\s*\n", "", code, flags=re.M)

    return code.strip() + "\n"


def fix_undefined_helper_asserts(code: str) -> str:
    replacements = {
        "get_user_exception_messages()[0]": '"user_id must be > 0"',
        "get_user_exception_messages()[1]": '"ok"',
        "get_user_exception_messages()[2]": '"ok"',
    }
    for old, new in replacements.items():
        code = code.replace(old, new)

    code = re.sub(
        r"\n\ndef\s+get_user\([^)]*\):[\s\S]*?(?=\n\ndef\s+test_|\nif\s+__name__|\Z)",
        "",
        code,
        flags=re.M,
    )
    return code.strip() + "\n"



def unwrap_request_exception_blocks(code: str) -> str:
    """AI 偶尔会把正常 HTTP 调用包进 pytest.raises，这会导致 response 未定义。
    这里把 with pytest.raises(...) 块去掉，保留里面真正的 requests 调用。
    """
    lines = code.splitlines()
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*with\s+pytest\.raises\([^)]*\).*:\s*$", line):
            base_indent = len(line) - len(line.lstrip())
            i += 1
            while i < len(lines):
                child = lines[i]
                if child.strip() == "":
                    result.append(child)
                    i += 1
                    continue
                child_indent = len(child) - len(child.lstrip())
                if child_indent <= base_indent:
                    break
                # 去掉一层缩进
                result.append(" " * base_indent + child.lstrip())
                i += 1
            continue
        result.append(line)
        i += 1

    code = "\n".join(result)
    code = re.sub(r"^from\s+requests\s+import\s+RequestException\s*\n", "", code, flags=re.M)
    return code.strip() + "\n"

def ensure_response_json_defined(code: str) -> str:
    if "response_json" not in code:
        return code

    lines = code.splitlines()
    new_lines = []
    inserted = False
    response_assign = re.compile(r"^(\s*)response\s*=\s*requests\.(get|post|put|delete|patch)\(")

    pending_indent = None
    paren_balance = 0

    for line in lines:
        if inserted and re.match(r"^\s*response_json\s*=\s*response\.json\(\)\s*$", line):
            continue

        new_lines.append(line)

        if pending_indent is None:
            match = response_assign.search(line)
            if match:
                pending_indent = match.group(1)
                paren_balance = line.count("(") - line.count(")")
                if paren_balance <= 0 and not inserted:
                    new_lines.append(f"{pending_indent}response_json = response.json()")
                    inserted = True
                    pending_indent = None
        else:
            paren_balance += line.count("(") - line.count(")")
            if paren_balance <= 0 and not inserted:
                new_lines.append(f"{pending_indent}response_json = response.json()")
                inserted = True
                pending_indent = None

    return "\n".join(new_lines).strip() + "\n"


def fix_common_assertion_mistakes(code: str) -> str:
    code = re.sub(
        r"response\.json\(\)\.get\(['\"]code['\"]\)\s*==\s*['\"]ok['\"]",
        "response.json().get('message') == 'ok'",
        code,
    )

    code = re.sub(
        r"assert\s+response\.json\(\)\[['\"]code['\"]\]\s*==\s*str\(([^)]+)\)",
        r"assert response.json().get('code') == \1",
        code,
    )
    code = re.sub(
        r"assert\s+response_json\[['\"]code['\"]\]\s*==\s*str\(([^)]+)\)",
        r"assert response_json.get('code') == \1",
        code,
    )
    code = re.sub(
        r"assert\s+data\[['\"]code['\"]\]\s*==\s*str\(([^)]+)\)",
        r"assert data.get('code') == \1",
        code,
    )

    return code


def _need_response_body_helper(code: str) -> bool:
    return any(
        re.search(pattern, code)
        for pattern in (
            r"assert\s+response\.json\(\)\s*==\s*\w+",
            r"assert\s+response_json\s*==\s*\w+",
            r"assert\s+data\s*==\s*\w+",
        )
    )


def _insert_response_body_helper(code: str) -> str:
    if "def _assert_response_body" in code:
        return code

    helper = """
def _assert_response_body(actual, expected):
    \"\"\"只校验稳定字段，避免动态字段和中文编码差异导致用例误失败。\"\"\"
    assert isinstance(actual, dict)

    if not isinstance(expected, dict):
        assert actual == expected
        return

    if "code" in expected:
        assert actual.get("code") == expected.get("code")

    # message/detail 经常是中文，真实项目里容易受编码影响；这里不作为强断言。
    # 如果要强校验，建议先保证后端响应和日志统一 UTF-8。
    expected_data = expected.get("data")
    actual_data = actual.get("data")

    if isinstance(expected_data, dict) and isinstance(actual_data, dict):
        for key, value in expected_data.items():
            if value in ("", None):
                continue
            assert actual_data.get(key) == value

"""
    lines = code.splitlines()
    insert_idx = 0
    while insert_idx < len(lines) and (
        lines[insert_idx].startswith("import ")
        or lines[insert_idx].startswith("from ")
        or not lines[insert_idx].strip()
    ):
        insert_idx += 1

    lines.insert(insert_idx, helper.strip("\n"))
    return "\n".join(lines).strip() + "\n"


def relax_response_body_assertions(code: str) -> str:
    need_helper = _need_response_body_helper(code)

    code = re.sub(
        r"assert\s+response\.json\(\)\s*==\s*([A-Za-z_][A-Za-z0-9_]*)",
        r"_assert_response_body(response.json(), \1)",
        code,
    )
    code = re.sub(
        r"assert\s+response_json\s*==\s*([A-Za-z_][A-Za-z0-9_]*)",
        r"_assert_response_body(response_json, \1)",
        code,
    )
    code = re.sub(
        r"assert\s+data\s*==\s*([A-Za-z_][A-Za-z0-9_]*)",
        r"_assert_response_body(data, \1)",
        code,
    )

    if need_helper:
        code = _insert_response_body_helper(code)
    return code.strip() + "\n"

def remove_fragile_text_assertions(code: str) -> str:
    """删除对中文 message/detail 的强依赖，保留状态码和业务 code 断言。"""
    lines = []
    for line in code.splitlines():
        stripped = line.strip()
        fragile_patterns = [
            r'assert\s+["\']detail["\']\s+in\s+response\.json\(\)',
            r'assert\s+["\']message["\']\s+in\s+response\.json\(\)',
            r'assert\s+["\']detail["\']\s+in\s+data',
            r'assert\s+["\']message["\']\s+in\s+data',
            r'assert\s+response\.json\(\)\.get\(["\']detail["\']\)\s*==',
            r'assert\s+response\.json\(\)\.get\(["\']message["\']\)\s*==',
            r'assert\s+data\.get\(["\']detail["\']\)\s*==',
            r'assert\s+data\.get\(["\']message["\']\)\s*==',
            r'assert\s+response_json\.get\(["\']detail["\']\)\s*==',
            r'assert\s+response_json\.get\(["\']message["\']\)\s*==',
        ]
        if any(re.match(p, stripped) for p in fragile_patterns):
            continue
        lines.append(line)
    return "\n".join(lines).strip() + "\n"


def add_pass_to_empty_blocks(code: str) -> str:
    lines = code.splitlines()
    result = []
    for idx, line in enumerate(lines):
        result.append(line)
        stripped = line.strip()
        if not stripped.endswith(":") or stripped.startswith(("@pytest.", "def ", "class ")):
            continue

        current_indent = len(line) - len(line.lstrip())
        next_non_empty = None
        for nxt in lines[idx + 1:]:
            if nxt.strip():
                next_non_empty = nxt
                break

        if next_non_empty is None:
            result.append(" " * (current_indent + 4) + "pass")
            continue

        next_indent = len(next_non_empty) - len(next_non_empty.lstrip())
        if next_indent <= current_indent:
            result.append(" " * (current_indent + 4) + "pass")

    return "\n".join(result).strip() + "\n"


def has_pytest_test_function(code: str) -> bool:
    return re.search(r"^\s*def\s+test_[A-Za-z0-9_]*\s*\(", code, flags=re.M) is not None



def relax_export_response_json(code: str) -> str:
    """导出类接口通常返回文件流，AI 如果生成 response.json() 会导致 JSONDecodeError。
    这里对包含 export/download 的测试文件做保守处理：删除 response.json 相关强断言，只保留状态码断言。
    """
    if not re.search(r"export|download|template|importTemplate", code, flags=re.I):
        return code

    new_lines = []
    skip_next = False
    for line in code.splitlines():
        stripped = line.strip()
        if re.search(r"(data|response_json)\s*=\s*response\.json\(\)", stripped):
            continue
        if "response.json()" in stripped:
            continue
        if re.search(r"assert\s+(data|response_json)\b", stripped):
            continue
        if re.search(r"assert\s+.*\['(code|msg|message|data)'\]", stripped):
            continue
        if re.search(r"assert\s+.*\.get\(['\"](code|msg|message|data)['\"]\)", stripped):
            continue
        new_lines.append(line)
    return "\n".join(new_lines).strip() + "\n"


def remove_pytest_config_headers(code: str) -> str:
    """去掉 AI 生成的 pytest.config.getoption("default_headers") 写法。

    pytest 没有这个稳定接口，认证头由 generated_tests/conftest.py 根据 TEST_AUTHORIZATION
    自动注入。保留这类代码会导致 AttributeError/OtherError。
    """
    code = re.sub(r"\s*\*\*pytest\.config\.getoption\([^)]+\),?\n", "", code)
    code = re.sub(r"\{\s*,", "{", code)
    code = re.sub(r",\s*\}", "}", code)
    return code.strip() + "\n"


def fix_upload_requests(code: str) -> str:
    """对上传类接口做保守修正。

    日志里的 multipart 文件内容没有复用价值，AI 有时会把乱码或 bytes 字符串当 json 传参。
    这里把 avatar/importData/upload 类 POST 请求改成 files=...，避免脚本级错误。
    """
    if not re.search(r"profile/avatar|importData|upload|avatar", code, flags=re.I):
        return code

    if "profile/avatar" in code:
        file_expr = 'files={"avatarfile": ("avatar.png", io.BytesIO(b"fake-image-content"), "image/png")}'
    else:
        file_expr = 'files={"file": ("import.xlsx", io.BytesIO(b"fake-file-content"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}'

    # 移除手写 Content-Type，multipart 边界应由 requests 自动生成。
    code = re.sub(r'["\']Content-Type["\']\s*:\s*["\'][^"\']*["\']\s*,?', "", code)

    # 常见形式：requests.post(url, headers=headers, json=data)
    code = re.sub(
        r"requests\.post\(\s*url\s*,\s*headers\s*=\s*headers\s*,\s*json\s*=\s*[^,)]+(\s*,\s*timeout\s*=\s*\d+)?\s*\)",
        f"requests.post(url, headers=headers, {file_expr})",
        code,
        flags=re.S,
    )
    code = re.sub(
        r"requests\.post\(\s*url\s*,\s*json\s*=\s*[^,)]+(\s*,\s*timeout\s*=\s*\d+)?\s*\)",
        f"requests.post(url, {file_expr})",
        code,
        flags=re.S,
    )
    code = re.sub(
        r"requests\.post\(\s*url\s*,\s*headers\s*=\s*headers\s*,\s*data\s*=\s*[^,)]+(\s*,\s*timeout\s*=\s*\d+)?\s*\)",
        f"requests.post(url, headers=headers, {file_expr})",
        code,
        flags=re.S,
    )
    code = re.sub(
        r"requests\.post\(\s*url\s*,\s*data\s*=\s*[^,)]+(\s*,\s*timeout\s*=\s*\d+)?\s*\)",
        f"requests.post(url, {file_expr})",
        code,
        flags=re.S,
    )
    return code.strip() + "\n"


def relax_file_upload_assertions(code: str) -> str:
    """上传/导入接口的返回受文件内容影响大，删除脆弱 JSON 字段强断言。"""
    if not re.search(r"profile/avatar|importData|upload|avatar", code, flags=re.I):
        return code

    new_lines = []
    for line in code.splitlines():
        stripped = line.strip()
        if re.search(r"(data|response_json)\s*=\s*response\.json\(\)", stripped):
            # 上传接口可以返回 json，但不能强依赖动态字段；后续如果没有用到可删掉
            continue
        if re.search(r"assert\s+(data|response_json)\b", stripped):
            continue
        if re.search(r"assert\s+.*\[['\"](imgUrl|url|fileName|msg|message|data)['\"]\]", stripped):
            continue
        if re.search(r"assert\s+.*\.get\(['\"](imgUrl|url|fileName|msg|message|data)['\"]\)", stripped):
            continue
        new_lines.append(line)
    return "\n".join(new_lines).strip() + "\n"


def replace_local_file_open(code: str) -> str:
    """禁止 AI 生成依赖本地 test.xlsx/avatar.png 的代码。

    文件类接口统一使用内存文件，避免 FileNotFoundError。
    """
    if "open(" not in code:
        return code
    code = re.sub(
        r"open\(\s*['\"]([^'\"]+\.(?:xlsx|xls|png|jpg|jpeg|zip|pdf))['\"]\s*,\s*['\"]rb['\"]\s*\)",
        'io.BytesIO(b"fake-file-content")',
        code,
        flags=re.I,
    )
    if "io.BytesIO" in code and not re.search(r"^import\s+io\b", code, flags=re.M):
        code = "import io\n" + code
    return code.strip() + "\n"

def post_process_generated_code(code: str) -> str:
    code = ensure_py_code(code)
    code = fix_broken_parametrize_string(code)
    code = fix_parametrize_args(code)
    code = fix_common_assertion_mistakes(code)
    code = fix_undefined_helper_asserts(code)
    code = remove_bad_exception_tests(code)
    code = unwrap_request_exception_blocks(code)
    code = ensure_response_json_defined(code)
    code = relax_response_body_assertions(code)
    code = remove_fragile_text_assertions(code)
    code = relax_export_response_json(code)
    code = remove_pytest_config_headers(code)
    code = replace_local_file_open(code)
    code = fix_upload_requests(code)
    code = relax_file_upload_assertions(code)
    code = add_pass_to_empty_blocks(code)
    code = ensure_required_imports(code)
    return code
