"""
配置模块。

这个工具默认把每次扫描结果写入新的时间戳目录，避免覆盖历史结果。
如需调整输出根目录，可以在命令行传 --output-root。
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GovernanceConfig:
    # 默认输出根目录。最终目录会是：governance_output/项目名_时间戳
    output_root: Path = Path("governance_output")

    # Java 扫描器 jar 的默认路径。
    scanner_jar: Path = Path("java-scanner/target/api-governance-javaparser-scanner-1.0.0.jar")

    # 默认规则配置文件。换项目时通常优先改这个文件。
    rule_config: Path = Path("governance_rules.json")
