"""
接口入参规范扫描工具 Python 入口。

使用方式：
python run_governance_scan.py --source-path ./RuoYi --project-name RuoYi

执行流程：
1. 创建本次扫描输出目录；
2. 调用 JavaParser 扫描器 jar 解析 Java 源码；
3. 读取 scanner_result.json；
4. 输出 xlsx、summary、prompt_context。
"""
import argparse
from pathlib import Path

from governance_py.config import GovernanceConfig
from governance_py.java_scanner import run_java_scanner
from governance_py.output_manager import create_run_dir, safe_name
from governance_py.report_writer import (
    load_scan_result,
    write_xlsx_report,
    write_prompt_context,
    write_summary,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="接口入参规范扫描工具")
    parser.add_argument("--source-path", required=True, help="Java 项目源码目录")
    parser.add_argument("--project-name", default="", help="项目名称，不传则使用源码目录名")
    parser.add_argument("--output-root", default="", help="输出根目录，不传则使用默认 governance_output")
    parser.add_argument("--scanner-jar", default="", help="Java 扫描器 jar 路径")
    parser.add_argument("--rule-config", default="", help="规则配置文件路径，不传则使用 governance_rules.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = GovernanceConfig()

    source_path = Path(args.source_path).resolve()
    project_name = args.project_name.strip() or source_path.name
    output_root = Path(args.output_root).resolve() if args.output_root else config.output_root
    scanner_jar = Path(args.scanner_jar).resolve() if args.scanner_jar else config.scanner_jar
    rule_config = Path(args.rule_config).resolve() if args.rule_config else config.rule_config

    run_dir = create_run_dir(output_root, project_name)
    project_prefix = safe_name(project_name)

    result_json = run_dir / f"{project_prefix}_scanner_result.json"
    xlsx_report = run_dir / f"{project_prefix}_governance_report.xlsx"
    summary = run_dir / f"{project_prefix}_governance_summary.txt"
    prompt_context = run_dir / f"{project_prefix}_governance_prompt_context.txt"

    run_java_scanner(scanner_jar, source_path, project_name, result_json, rule_config)
    scan_result = load_scan_result(result_json)

    write_xlsx_report(scan_result, xlsx_report)
    write_summary(scan_result, summary)
    write_prompt_context(scan_result, prompt_context)

    print("扫描完成：")
    print(f"输出目录：{run_dir}")
    print(f"明细报告XLSX：{xlsx_report}")
    print(f"摘要报告：{summary}")
    print(f"规则配置：{rule_config if rule_config.exists() else '内置默认配置'}")


if __name__ == "__main__":
    main()
