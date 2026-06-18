"""
Java 扫描器调用模块。

Python 不直接解析 Java 源码，而是调用 JavaParser 扫描器 jar。
这样做的原因：
1. JavaParser 更适合解析 Java AST；
2. Python 只负责流程编排和报告输出，降低误判和维护成本；
3. 后续如果 Java 侧规则升级，不影响 Python 报告层。
"""
from pathlib import Path
import subprocess


def run_java_scanner(scanner_jar: Path, source_path: Path, project_name: str, output_json: Path, rule_config: Path = None) -> None:
    """调用 Java 扫描器并输出 scanner_result.json。"""
    if not scanner_jar.exists():
        raise FileNotFoundError(
            f"未找到 Java 扫描器 jar：{scanner_jar}\n"
            "请先进入 java-scanner 目录执行：mvn clean package"
        )
    if not source_path.exists():
        raise FileNotFoundError(f"源码目录不存在：{source_path}")

    cmd = [
        "java",
        "-jar",
        str(scanner_jar),
        "--source-path",
        str(source_path),
        "--project-name",
        project_name,
        "--output-json",
        str(output_json),
    ]
    if rule_config and rule_config.exists():
        cmd.extend(["--config-json", str(rule_config)])
    subprocess.run(cmd, check=True)
