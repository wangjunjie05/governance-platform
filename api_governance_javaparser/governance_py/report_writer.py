"""
报告输出模块。

职责：
1. 把 Java 扫描器输出的 scanner_result.json 转成 XLSX 明细报告；
2. 生成 summary 文本摘要，方便快速查看项目扫描情况；
3. 生成 prompt_context，后续接 AI 生成接口测试脚本时可以作为上下文。

设计原则：
- 不在 Python 侧重新判断 Java 代码是否违规，避免扫描逻辑分散；
- Python 侧只做展示、排序、汇总、报告输出；
- 报告内容尽量清晰，方便人工复核。
"""
from collections import Counter
from pathlib import Path
import json

from governance_py.xlsx_writer import write_xlsx


REPORT_HEADERS = [
    "风险等级",
    "问题位置",
    "问题类型",
    "问题说明",
    "处理建议",
    "提示原因",
    "涉及类型",
    "字段名",
    "文件路径",
    "行号",
]

RISK_ORDER = {"高风险": 0, "中风险": 1, "建议项": 2}


def display_text(value) -> str:
    """
    报告展示文案统一处理。

    Java 扫描器内部为了方便维护，会保留一些偏技术化的描述，
    例如 @RequestBody、Bean Validation、Controller、printStackTrace 等。
    这些词对开发维护有用，但放到给人看的报告里不够直观。

    这里把技术词统一转成更日常的说明，只影响 XLSX、summary、prompt 的展示，
    不影响扫描规则，也不影响 scanner_result.json 原始结果。
    """
    if value is None:
        return ""
    text = str(value)

    replacements = [
        ("company-", "project-"),
        ("@RequestBody 使用 Map/List 等非 Bean 入参", "接口参数使用 Map/List，字段不方便单独检查"),
        ("@RequestBody 对象入参缺少 @Valid/@Validated", "接口入参的字段校验可能未生效"),
        ("写接口对象绑定入参缺少 @Valid/@Validated", "写入类接口的参数校验可能未生效"),
        ("该接口使用 Map/List 等非 Bean 类型作为请求体，字段级 Bean Validation 不易统一管理。", "该接口直接使用 Map/List 接收参数，不方便对里面的每个字段做统一校验。"),
        ("该 @RequestBody 入参类型中已经定义了 Bean Validation 字段校验，但 Controller 参数未声明 @Valid/@Validated，字段校验可能不会生效。", "这个接口参数的类里已经写了字段校验，但接口方法上没有触发校验，实际运行时可能不会生效。"),
        ("该写接口使用对象绑定入参，且入参类型中已经定义了 Bean Validation 字段校验，但方法参数未声明 @Valid/@Validated。", "这个写入类接口的参数类里已经写了字段校验，但接口方法上没有触发校验。"),
        ("建议在该参数前增加 @Valid 或 @Validated，确保 DTO 字段校验生效。", "建议补充接口参数校验触发方式，确保字段校验能够生效。"),
        ("如果项目希望自动触发字段校验，建议在该参数前增加 @Valid 或 @Validated。", "如果希望接口自动校验参数，建议补充对应的校验触发方式。"),
        ("建议结合业务含义确认是否必填；如为必填字段，补充对应 Bean Validation 注解。", "建议结合业务确认该字段是否必须填写；如果必须填写，补充对应的字段校验。"),
        ("Request DTO", "请求参数类"),
        ("DTO", "参数类"),
        ("字段级", "字段"),
        ("异常处理方法返回类型为", "错误处理的返回格式是"),
        ("建议异常处理统一返回项目规定的响应对象，避免异常信息格式不一致。", "建议错误处理也使用项目统一的返回格式，避免错误信息格式不一致。"),
        ("Bean Validation", "字段校验"),
        ("Controller 入参类型关联字段扫描", "接口入参字段检查"),
        ("@RequestBody", "接口请求参数"),
        ("写接口对象绑定入参", "写入类接口参数"),
        ("扩展规则：统一异常处理", "补充检查：错误是否统一处理"),
        ("扩展规则：异常处理返回结构", "补充检查：错误返回格式"),
        ("扩展规则：异常处理", "补充检查：错误处理方式"),
        ("扩展规则：统一返回结构", "补充检查：接口返回格式"),
        ("扩展规则：分页参数", "补充检查：分页参数"),
        ("统一异常处理检查", "是否有统一错误处理"),
        ("异常处理返回结构检查", "错误返回格式是否统一"),
        ("异常处理堆栈打印检查", "是否直接打印错误信息"),
        ("统一返回结构检查", "接口返回格式是否统一"),
        ("分页参数检查", "分页参数是否完整"),
        ("项目缺少统一异常处理", "项目可能缺少统一错误处理"),
        ("异常处理返回结构可能未统一", "错误返回格式可能不统一"),
        ("异常处理直接打印堆栈", "错误处理里直接打印错误信息"),
        ("Controller 返回值可能未统一", "接口返回格式可能不统一"),
        ("分页接口参数可能不完整", "分页接口可能缺少分页参数"),
        ("未识别到完整的全局异常处理类（@ControllerAdvice/@RestControllerAdvice + @ExceptionHandler）。", "未识别到统一处理接口错误的代码。"),
        ("建议增加统一异常处理类，统一捕获异常并返回规范错误信息；如项目已有自定义实现，可在 governance_rules.json 中补充注解或关闭该规则。", "建议统一处理接口错误，并返回固定格式的错误信息；如果项目已有自己的处理方式，可在配置中补充或关闭该检查。"),
        ("异常处理方法中存在 printStackTrace 调用，可能导致错误信息处理不统一。", "错误处理代码中直接打印了错误信息，可能导致日志和返回处理不统一。"),
        ("建议改为统一日志记录和统一错误返回，不要在异常处理器中直接 printStackTrace。", "建议改为统一记录日志，并统一返回错误信息，不要直接打印错误。"),
        ("不在配置的统一返回类型列表中", "不在配置的统一返回格式列表中"),
        ("统一返回类型", "统一返回格式"),
        ("统一返回结构", "统一返回格式"),
        ("Controller", "接口类"),
        ("DTO", "参数类"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text




def display_line_number(value) -> str:
    """行号展示处理。

    如果 JavaParser 无法定位到具体源码行，可能会返回 0、空值或非数字。
    报告里不展示“0”或“未知”，直接留空，避免影响阅读。
    """
    if value is None or value == "":
        return ""
    try:
        line = int(value)
    except (TypeError, ValueError):
        return str(value)
    return str(line) if line > 0 else ""

def load_scan_result(json_path: Path) -> dict:
    """读取 Java 扫描器输出的 JSON 文件。"""
    with json_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def sort_issues(issues: list) -> list:
    """
    统一的问题排序规则。

    排序目的：
    - 打开明细报告时先看到最需要关注的问题；
    - 同风险等级下按问题位置、类型、字段聚合，方便阅读。
    """
    return sorted(
        issues,
        key=lambda x: (
            RISK_ORDER.get(x.get("riskLevel", ""), 9),
            issue_location(x),
            x.get("parameterType", ""),
            x.get("fieldName", ""),
            x.get("issueType", ""),
        ),
    )


def compact_config_path(path_value: str) -> str:
    """
    规则配置路径展示优化。

    扫描器内部会记录完整路径，但报告里展示一长串本机绝对路径没什么价值，
    还会暴露个人电脑目录。这里统一压缩为文件名或“已加载”。
    """
    if not path_value:
        return "内置默认配置"
    if path_value == "内置默认配置":
        return path_value
    return path_value.replace("\\", "/").rstrip("/").split("/")[-1] or "已加载"


def enabled_project_rules(scan_result: dict) -> list:
    """获取启用的扩展规则。"""
    return [display_text(rule) for rule in scan_result.get("enabledProjectRules", [])]




def implemented_check_lines() -> list:
    """返回当前工具已经实现的检查范围说明。

    这部分只用于 summary 展示，不参与扫描判断。
    文案尽量用日常说法，方便非开发人员也能看懂。
    """
    return [
        "- 参数检查：是否缺少必填、长度、范围、取值格式等基础校验",
        "- 错误处理检查：是否有统一错误处理、错误返回是否统一、是否直接打印错误信息",
        "- 返回格式检查：写入类接口返回结果是否尽量保持统一",
    ]


def overall_risk_level(risk_counter: Counter) -> str:
    """根据问题数量给出一个简单的整体结论。

    这个结论只用于快速阅读 summary，不替代人工判断：
    - 有高风险：需要优先关注；
    - 没有高风险但有较多中风险：建议复核；
    - 只有少量建议项：整体风险较低。
    """
    high = risk_counter.get("高风险", 0)
    medium = risk_counter.get("中风险", 0)
    if high >= 5:
        return "较高（存在较多高风险问题，建议优先处理）"
    if high > 0:
        return "中等（存在高风险问题，建议重点复核）"
    if medium >= 20:
        return "中等（中风险问题较多，建议结合业务复核）"
    if medium > 0:
        return "较低（以中风险和建议项为主）"
    return "较低（未发现明显高风险问题）"


def issue_key(issue: dict) -> tuple:
    """
    用于 TOP 汇总的去重 key。

    不直接按整条 description 去重，是因为同一类问题可能出现在不同字段/不同接口，
    summary 里更适合展示“问题类型 + 出现次数”。
    """
    return (
        issue.get("riskLevel", ""),
        issue.get("issueType", ""),
    )


def top_issue_lines(issues: list, risk_level: str, limit: int = 10) -> list:
    """
    生成某个风险等级的 TOP 问题列表。

    展示形式：
    - 账号类字段缺少必填校验（2处）
    - 密码字段缺少长度限制（1处）
    """
    filtered = [i for i in issues if i.get("riskLevel") == risk_level]
    if not filtered:
        return ["- 无"]
    counter = Counter(issue_key(i) for i in filtered)
    lines = []
    for (_, issue_type), count in counter.most_common(limit):
        lines.append(f"- {display_text(issue_type)}（{count}处）")
    return lines


def project_rule_result_lines(scan_result: dict, issues: list) -> list:
    """
    生成扩展规则检查结果。

    Java 侧只有在规则未通过时才会生成 issue；如果某条扩展规则已启用，
    但没有对应 issue，就可以认为本次扫描未发现该规则问题。
    """
    rules = enabled_project_rules(scan_result)
    if not rules:
        return ["- 未启用"]

    # 规则名称和 ruleId 关键词的简单映射，用来判断某条规则是否产生了问题。
    rule_keywords = {
        "是否有统一错误处理": "global-exception-handler",
        "错误返回格式是否统一": "exception-handler-return-type",
        "是否直接打印错误信息": "exception-print-stacktrace",
        "接口返回格式是否统一": "unified-return-type",
        "分页参数是否完整": "page-params",
    }
    lines = []
    for rule in rules:
        keyword = rule_keywords.get(rule, "")
        failed = False
        if keyword:
            failed = any(keyword in str(i.get("ruleId", "")) for i in issues)
        if failed:
            lines.append(f"- × {rule}：发现问题，详见明细报告")
        else:
            lines.append(f"- √ {rule}：未发现明显问题")
    return lines


def issue_location(issue: dict) -> str:
    """
    生成统一的“问题位置”。

    为什么要这样做：
    - 接口级问题通常能拿到 Controller / 方法名 / 请求方法；
    - 字段级问题通常只知道 DTO 类和字段名；
    - 如果在明细报告中同时展示 Controller、方法名、请求方法，会出现有的行有值、有的行为空，
      容易让使用者误以为工具漏扫。

    这里统一收敛成“问题位置”：
    - 字段级：SysUser.userName
    - 入参级：SysUserController.add(SysUser)
    - 扩展规则：项目级检查
    """
    param_type = str(issue.get("parameterType") or "").strip()
    field_name = str(issue.get("fieldName") or "").strip()
    controller = str(issue.get("controllerClass") or "").strip()
    method = str(issue.get("methodName") or "").strip()
    param_name = str(issue.get("parameterName") or "").strip()

    if param_type and field_name:
        return f"{param_type}.{field_name}"
    if controller and method:
        if param_type:
            return f"{controller}.{method}({param_type})"
        if param_name:
            return f"{controller}.{method}({param_name})"
        return f"{controller}.{method}"
    if param_type:
        return param_type
    if issue.get("filePath"):
        location = str(issue.get("filePath"))
        line_text = display_line_number(issue.get("line"))
        if line_text:
            location += f":{line_text}"
        return location
    return "项目级检查"


def build_report_rows(scan_result: dict) -> list:
    """
    生成明细报告二维数据。

    第一行是表头，后续每行是一条问题。
    """
    rows = [REPORT_HEADERS]
    for item in sort_issues(scan_result.get("issues", [])):
        row = [
            item.get("riskLevel", ""),
            issue_location(item),
            item.get("issueType", ""),
            item.get("description", ""),
            item.get("suggestion", ""),
            item.get("scanBasis", ""),
            item.get("parameterType", ""),
            item.get("fieldName", ""),
            item.get("filePath", ""),
            display_line_number(item.get("line", "")),
        ]
        rows.append([display_text(value) for value in row])
    return rows


def write_xlsx_report(scan_result: dict, output_file: Path) -> None:
    """
    输出 XLSX 明细报告。

    XLSX 是默认明细报告格式，适合直接用 Excel/WPS 查看。
    这里使用项目内置的轻量 xlsx_writer，不需要安装任何第三方 Python 包。
    """
    rows = build_report_rows(scan_result)
    write_xlsx(rows, output_file, sheet_name="扫描明细")


def write_summary(scan_result: dict, output_file: Path) -> None:
    """输出文本摘要，方便快速查看扫描结果。"""
    issues = sort_issues(scan_result.get("issues", []))
    risk_counter = Counter(item.get("riskLevel", "未知") for item in issues)
    type_counter = Counter(display_text(item.get("issueType", "未知")) for item in issues)

    lines = [
        "接口入参规范扫描摘要",
        "=" * 32,
        f"项目名称：{scan_result.get('projectName', '')}",
        f"源码路径：{scan_result.get('sourcePath', '')}",
        f"Java 文件数：{scan_result.get('javaFileCount', 0)}",
        f"接口类数量：{scan_result.get('controllerCount', 0)}",
        f"接口入参数量：{scan_result.get('requestParamCount', 0)}",
        f"参与字段检查的参数类型数：{scan_result.get('dtoFieldScanClassCount', 0)}",
        f"项目是否使用字段校验：{'是' if scan_result.get('beanValidationUsed') else '否'}",
        f"规则配置：{compact_config_path(scan_result.get('ruleConfigPath', ''))}",
        f"启用补充检查：{'、'.join(enabled_project_rules(scan_result)) or '无'}",
        "",
        "扫描结论：",
        f"- 整体风险等级：{overall_risk_level(risk_counter)}",
        "",
        "当前检查内容：",
        *implemented_check_lines(),
        "",
        f"问题总数：{len(issues)}",
        "",
        "风险等级统计：",
    ]
    for key in ["高风险", "中风险", "建议项", "未知"]:
        if risk_counter.get(key):
            lines.append(f"- {key}：{risk_counter[key]}")

    lines.append("")
    lines.append("问题类型统计：")
    for key, value in type_counter.items():
        lines.append(f"- {key}：{value}")

    scanned_dtos = scan_result.get("scannedDtoClasses", [])
    lines.append("")
    lines.append("参与字段检查的参数类型：")
    if scanned_dtos:
        for dto in scanned_dtos:
            lines.append(f"- {dto}")
    else:
        lines.append("- 无")

    lines.append("")
    lines.append("高风险TOP问题：")
    lines.extend(top_issue_lines(issues, "高风险"))

    lines.append("")
    lines.append("中风险TOP问题：")
    lines.extend(top_issue_lines(issues, "中风险"))

    lines.append("")
    lines.append("补充检查结果：")
    lines.extend(project_rule_result_lines(scan_result, issues))

    output_file.write_text("\n".join(lines), encoding="utf-8")


def write_prompt_context(scan_result: dict, output_file: Path, max_items: int = 30) -> None:
    """输出给 AI 测试生成模块使用的精简上下文。"""
    issues = sort_issues(scan_result.get("issues", []))[:max_items]
    lines = ["【接口入参规范扫描结果】"]
    if not issues:
        lines.append("未发现明显的入参校验问题。")
    for item in issues:
        location = item.get("filePath", "")
        line_text = display_line_number(item.get("line"))
        if line_text:
            location += f":{line_text}"
        lines.append(
            f"- {display_text(item.get('riskLevel', ''))}｜{display_text(item.get('issueType', ''))}｜"
            f"{issue_location(item)}｜{location}"
        )

    lines.append("")
    lines.append("高风险TOP问题：")
    lines.extend(top_issue_lines(scan_result.get("issues", []), "高风险"))

    output_file.write_text("\n".join(lines), encoding="utf-8")
