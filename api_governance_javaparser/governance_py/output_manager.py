"""
输出目录管理。

每次执行都创建独立目录，目录名包含项目名和时间戳。
这样多次运行不会覆盖上一次结果，也方便对比不同项目、不同版本的扫描结果。
"""
from datetime import datetime
from pathlib import Path
import re


def safe_name(name: str) -> str:
    """把项目名转换成适合作为文件夹/文件名前缀的字符串。"""
    cleaned = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fa5]+", "_", name.strip())
    return cleaned.strip("_") or "project"


def create_run_dir(output_root: Path, project_name: str) -> Path:
    """创建本次扫描输出目录。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = output_root / f"{safe_name(project_name)}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir
