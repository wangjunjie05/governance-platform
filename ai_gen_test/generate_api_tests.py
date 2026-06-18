import argparse
import os
from pathlib import Path

import yaml

from core.config import (
    BASE_URL,
    CODE_DIR,
    EXCEPTION_MODE,
    GENERATION_MODE,
    LOG_FILE,
    MAX_NORMAL_CASES_PER_API,
    VALID_EXCEPTION_MODES,
    VALID_GENERATION_MODES,
)
from core.generator import main


def load_config(path: str) -> dict:
    if not path:
        return {}
    cfg_path = Path(path)
    if not cfg_path.exists():
        return {}
    with cfg_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}



def apply_runtime_config(cfg: dict) -> None:
    """把 config.yaml 里的运行配置同步到环境变量。"""
    if not isinstance(cfg, dict):
        return

    auth = cfg.get("auth") or {}
    if isinstance(auth, dict):
        mapping = {
            "login_url": "AUTH_LOGIN_PATH",
            "login_path": "AUTH_LOGIN_PATH",
            "username": "AUTH_USERNAME",
            "password": "AUTH_PASSWORD",
            "username_field": "AUTH_USERNAME_FIELD",
            "password_field": "AUTH_PASSWORD_FIELD",
            "token_path": "AUTH_TOKEN_JSON_PATHS",
            "token_paths": "AUTH_TOKEN_JSON_PATHS",
            "header_prefix": "AUTH_HEADER_PREFIX",
            "enable_refresh": "AUTH_ENABLE_REFRESH",
            "cookie_first": "AUTH_COOKIE_FIRST",
            "replay_header_names": "AUTH_REPLAY_HEADER_NAMES",
        }
        for key, env_key in mapping.items():
            value = auth.get(key)
            if value in (None, ""):
                continue
            if isinstance(value, (list, tuple)):
                value = ",".join(str(x) for x in value)
            os.environ[env_key] = str(value)

    ollama = cfg.get("ollama") or {}
    if isinstance(ollama, dict):
        mapping = {
            "url": "OLLAMA_URL",
            "model": "OLLAMA_MODEL",
            "timeout": "OLLAMA_TIMEOUT",
            "retry": "OLLAMA_RETRY",
            "num_predict": "NUM_PREDICT",
            "temperature": "TEMPERATURE",
        }
        for key, env_key in mapping.items():
            value = ollama.get(key)
            if value not in (None, ""):
                os.environ[env_key] = str(value)

    generation_workers = cfg.get("generate_workers")
    if generation_workers not in (None, ""):
        os.environ["GENERATE_WORKERS"] = str(generation_workers)

    gateway_prefixes = cfg.get("gateway_prefixes")
    if gateway_prefixes not in (None, ""):
        if isinstance(gateway_prefixes, (list, tuple)):
            gateway_prefixes = ",".join(str(x) for x in gateway_prefixes)
        os.environ["API_GATEWAY_PREFIXES"] = str(gateway_prefixes)


def pick(cli_value, cfg: dict, key: str, default=None):
    if cli_value not in (None, ""):
        return cli_value
    value = cfg.get(key)
    if value not in (None, ""):
        return value
    return default


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成 pytest 接口自动化测试脚本")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="配置文件路径，默认读取当前目录 config.yaml；命令行参数优先级高于配置文件。",
    )
    parser.add_argument("--spec", default="", help="Swagger/OpenAPI 文件路径。未传时读取配置文件 spec。")
    parser.add_argument(
        "--mode",
        default="",
        choices=sorted(VALID_GENERATION_MODES),
        help="知识库模式：swagger、swagger_code、swagger_code_log",
    )
    parser.add_argument(
        "--exception-mode",
        default="",
        choices=sorted(VALID_EXCEPTION_MODES),
        help="异常用例模式：basic=每类异常生成代表用例；full=可执行异常场景全部生成执行。默认 basic。",
    )
    parser.add_argument("--repeat", type=int, default=None, help="重复执行次数。默认 1。")
    parser.add_argument(
        "--max-normal-cases-per-api",
        type=int,
        default=None,
        help="每个接口最多补充的正常基线用例数。默认 3。",
    )
    parser.add_argument("--code-dir", default="", help="后端源码根目录。")
    parser.add_argument("--log-file", default="", help="接口访问日志文件。")
    parser.add_argument("--api-prefix", default="", help="只生成指定路径前缀的接口，多个用逗号分隔。")
    parser.add_argument("--api-keyword", default="", help="只生成路径中包含指定关键字的接口，多个用逗号分隔。")
    parser.add_argument("--code-include", default="", help="代码扫描包含关键字，多个用逗号分隔。")
    parser.add_argument("--code-exclude", default="", help="代码扫描排除关键字，多个用逗号分隔。")
    parser.add_argument("--base-url", default="", help="执行生成用例时使用的接口根地址。")
    parser.add_argument("--governance-context", default="", help="接口规范扫描补充信息文件路径（可选）。")

    args = parser.parse_args()
    cfg = load_config(args.config)
    apply_runtime_config(cfg)

    spec = pick(args.spec, cfg, "spec", "swaggerr.json")
    if not spec:
        raise SystemExit("缺少 Swagger 文件路径，请在 config.yaml 中配置 spec 或使用 --spec 指定。")

    main(
        spec,
        mode=pick(args.mode, cfg, "mode", GENERATION_MODE),
        repeat=int(pick(args.repeat, cfg, "repeat", 1)),
        exception_mode=pick(args.exception_mode, cfg, "exception_mode", EXCEPTION_MODE),
        max_normal_cases_per_api=int(pick(args.max_normal_cases_per_api, cfg, "max_normal_cases_per_api", MAX_NORMAL_CASES_PER_API)),
        code_dir=pick(args.code_dir, cfg, "code_dir", CODE_DIR),
        log_file=pick(args.log_file, cfg, "log_file", LOG_FILE),
        api_prefixes=pick(args.api_prefix, cfg, "api_prefix", ""),
        api_keywords=pick(args.api_keyword, cfg, "api_keyword", ""),
        code_include=pick(args.code_include, cfg, "code_include", ""),
        code_exclude=pick(args.code_exclude, cfg, "code_exclude", "target,.git,node_modules,dist"),
        base_url=pick(args.base_url, cfg, "base_url", BASE_URL),
        governance_context=pick(args.governance_context, cfg, "governance_context", ""),
    )
