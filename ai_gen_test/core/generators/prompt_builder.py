import json
from core.config import BASE_URL
from typing import Any, Dict, List

MAX_LOG_PROMPT_CHARS = 3000
MAX_CODE_PROMPT_CHARS = 2000
MAX_EXCEPTION_PROMPT_CASES = 10


def _clip_text(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2, default=str)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...（已截断，原始长度 {len(text)} 字符）"


BASE_RULES = """
你是接口自动化测试工程师。请根据给定信息生成 pytest + requests 测试脚本。

输出要求：
1. 只输出完整 Python 代码，不要解释，不要 Markdown。
2. 代码必须从 import 开始。
3. BASE_URL 使用 os.getenv("BASE_URL", "{BASE_URL}")。
4. 必须至少生成一个 def test_ 开头的测试函数。
5. 如果使用 pytest.mark.parametrize，装饰器参数必须和测试函数入参完全一致。
6. 只调用 HTTP 接口，不要复制被测系统的业务函数。
7. 需要 requests 时必须 import requests；需要 pytest 时必须 import pytest。

断言要求：
1. 有日志样例时，以日志中的 request、http_status、business_code、response_body 为准。
2. HTTP 状态码和业务 code 是两个字段，不要把 expected_status_code 当业务 code。
3. 不要写 assert response.status_code in [...] 这种宽泛断言。
4. 非 2xx 响应如果只有 detail 字段，只断言 detail，不要强行断言 code。
5. 不要把 message 的值当成 code 断言，例如禁止 code == "ok"。
6. 需要使用 response_json 时，先统一写 response_json = response.json()。
7. 不要使用 assert response.json() == expected_response_body 这类整包响应体全等断言；只断言稳定字段，例如 HTTP状态码、业务code、必要的数据字段。
8. 中文 message/detail 不作为强断言，除非日志和服务端响应都明确保证 UTF-8 且完全一致。
9. 导出/download/export 类接口可能返回 Excel/ZIP/PDF 等二进制内容，不要调用 response.json()，只断言 HTTP 状态码或 Content-Type。
10. 上传/import/avatar 类接口通常是 multipart/form-data：必须使用 requests 的 files 参数，不要把文件内容字符串或乱码内容当普通 json 传参。
11. 不要使用 pytest.config.getoption 这类 pytest 内部接口获取 headers；认证头由 conftest.py 自动注入。
12. delete 类接口的路径参数如果是数组或多个 id，应拼成 1,2 这种路径段，不要传空数组作为正常用例。
13. importTemplate、template、export、download 类接口是下载/导出类接口，禁止生成 files 参数，禁止 open("test.xlsx")，禁止 response.json()。
14. avatar、upload、importData 类接口如需文件，必须使用 io.BytesIO 构造内存文件，禁止读取本地文件。
15. 生成代码尽量简洁，公共能力使用 api_test_utils.py 中的工具函数，不要把大量重复 helper 塞进每个 test 文件。


用例要求：
1. 有日志样例时优先覆盖日志中的真实场景。
2. 没有日志样例时，再结合代码扫描和 Swagger 推断基础用例。
3. 如果提供了【异常用例建议】，必须尽量为每条建议生成对应测试场景。
4. 缺少参数、参数为空、参数类型错误、超过长度、数值越界、非法枚举等都属于异常用例。
5. 异常用例可以断言 HTTP 状态码，错误 message/detail 不稳定时不要强断言中文。
6. 不要使用未定义的辅助函数。
7. 不要使用 pytest.raises(RequestException) 包裹 response.json()。
""".strip()


def build_prompt(api_doc: str, method: str, path: str, log_cases: List[Dict[str, Any]], code_info: Dict[str, Any], exception_cases: List[Dict[str, Any]] = None, governance_context: str = None) -> str:
    rules = BASE_RULES.replace("{BASE_URL}", BASE_URL)
    sections = [rules, "", "【接口信息】", api_doc]

    if log_cases:
        sections.extend([
            "",
            "【结构化访问日志】",
            "以下是真实调用样例，生成脚本时必须优先使用：",
            _clip_text(log_cases, MAX_LOG_PROMPT_CHARS),
        ])
    else:
        sections.extend(["", "【结构化访问日志】", "未命中该接口日志。"])

    if code_info and code_info.get("matched"):
        code_summary = {k: v for k, v in code_info.items() if k != "logic_snippet"}
        sections.extend([
            "",
            "【代码扫描结果】",
            _clip_text(code_summary, MAX_CODE_PROMPT_CHARS),
            "",
            "【相关代码片段】",
            _clip_text(code_info.get("logic_snippet", ""), MAX_CODE_PROMPT_CHARS),
        ])
    else:
        sections.extend(["", "【代码扫描结果】", "未匹配到明确代码信息。"])

    exception_cases = exception_cases or []
    if exception_cases:
        sections.extend([
            "",
            "【异常用例建议】",
            "以下异常场景由程序根据 DTO 校验注解、接口参数和代码异常分支自动扩展。生成测试脚本时应尽量覆盖这些异常场景：",
            _clip_text(exception_cases[:MAX_EXCEPTION_PROMPT_CASES], MAX_LOG_PROMPT_CHARS),
        ])
    else:
        sections.extend(["", "【异常用例建议】", "未生成明确异常用例建议。"])

    if governance_context:
        sections.extend([
            "",
            "【接口规范扫描补充信息】",
            "以下是接口规范扫描工具检测到的入参校验、错误处理等补充信息：",
            governance_context,
        ])

    return "\n".join(sections).strip() + "\n"


def build_fix_prompt(code: str, error_msg: str) -> str:
    return f"""
下面的 pytest 代码存在问题，请修复后输出完整 Python 代码。
只输出代码，不要解释，不要 Markdown。

报错信息：
{error_msg}

原始代码：
{code}

修复要求：
1. pytest.mark.parametrize 的参数名必须和测试函数入参一致。
2. 必须保证 pytest 能正常收集到测试函数。
3. 如果使用 response_json，必须先定义 response_json = response.json()。
""".strip() + "\n"


# Special rules: importTemplate/download/export/template must not generate open("*.xlsx") or files upload. avatar/upload/importData should use io.BytesIO in-memory files.
