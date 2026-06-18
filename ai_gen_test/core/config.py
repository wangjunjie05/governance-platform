import os

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8080").rstrip("/")

RUNS_DIR = os.getenv("RUNS_DIR", "runs")
OUT_DIR = os.getenv("OUT_DIR", "out_tests")
SUMMARY_FILE = os.getenv("SUMMARY_FILE", "summary.txt")

LOG_FILE = os.getenv("LOG_FILE", os.path.join("..", "proxy_capture", "logs", "api_access.log"))
CODE_DIR = os.getenv("CODE_DIR", os.path.join("..", "demo-api"))

USE_OLLAMA = os.getenv("USE_OLLAMA", "1") == "1"
NUM_PREDICT = int(os.getenv("NUM_PREDICT", "1200"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.1"))
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "600"))
OLLAMA_RETRY = int(os.getenv("OLLAMA_RETRY", "2"))
PYTEST_TIMEOUT = int(os.getenv("PYTEST_TIMEOUT", "60"))
ENABLE_FIX_RETRY = os.getenv("ENABLE_FIX_RETRY", "1") == "1"

GENERATION_MODE = os.getenv("GENERATION_MODE", "swagger_code_log").strip().lower()
VALID_GENERATION_MODES = {"swagger", "swagger_code", "swagger_code_log"}

if GENERATION_MODE not in VALID_GENERATION_MODES:
    raise ValueError(f"GENERATION_MODE 只能是 {sorted(VALID_GENERATION_MODES)}，当前值：{GENERATION_MODE}")

EXCEPTION_MODE = os.getenv("EXCEPTION_MODE", "basic").strip().lower()
VALID_EXCEPTION_MODES = {"basic", "full"}

if EXCEPTION_MODE not in VALID_EXCEPTION_MODES:
    raise ValueError(f"EXCEPTION_MODE 只能是 {sorted(VALID_EXCEPTION_MODES)}，当前值：{EXCEPTION_MODE}")

MAX_NORMAL_CASES_PER_API = int(os.getenv("MAX_NORMAL_CASES_PER_API", "3"))

GENERATE_WORKERS = int(os.getenv("GENERATE_WORKERS", "4"))
GOVERNANCE_CONTEXT = os.getenv("GOVERNANCE_CONTEXT", "")


# 针对真实项目的可选过滤配置。命令行参数优先级高于环境变量。
# API_PATH_PREFIXES：只生成匹配这些路径前缀的接口，例如 /system/config
# API_PATH_KEYWORDS：只生成路径中包含这些关键字的接口，例如 system/config
# CODE_INCLUDE_KEYWORDS：代码扫描时只扫描路径中包含这些关键字的文件/目录
# CODE_EXCLUDE_KEYWORDS：代码扫描时排除路径中包含这些关键字的文件/目录
API_PATH_PREFIXES = [x.strip() for x in os.getenv("API_PATH_PREFIXES", "").split(",") if x.strip()]
API_PATH_KEYWORDS = [x.strip() for x in os.getenv("API_PATH_KEYWORDS", "").split(",") if x.strip()]
CODE_INCLUDE_KEYWORDS = [x.strip() for x in os.getenv("CODE_INCLUDE_KEYWORDS", "").split(",") if x.strip()]
CODE_EXCLUDE_KEYWORDS = [x.strip() for x in os.getenv("CODE_EXCLUDE_KEYWORDS", "target,.git,node_modules,dist").split(",") if x.strip()]

# 登录刷新配置：真实项目 token 过期时，pytest 插件可自动登录刷新一次。
AUTH_LOGIN_PATH = os.getenv("AUTH_LOGIN_PATH", "/login")
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "")
AUTH_USERNAME_FIELD = os.getenv("AUTH_USERNAME_FIELD", "username")
AUTH_PASSWORD_FIELD = os.getenv("AUTH_PASSWORD_FIELD", "password")
AUTH_TOKEN_JSON_PATHS = [x.strip() for x in os.getenv("AUTH_TOKEN_JSON_PATHS", "token,data.token,access_token,data.access_token").split(",") if x.strip()]
AUTH_HEADER_PREFIX = os.getenv("AUTH_HEADER_PREFIX", "Bearer")
AUTH_ENABLE_REFRESH = os.getenv("AUTH_ENABLE_REFRESH", "0").strip().lower() in {"1", "true", "yes", "y"}

AUTH_COOKIE_FIRST = os.getenv("AUTH_COOKIE_FIRST", "1").strip().lower() in {"1", "true", "yes", "y"}
AUTH_REPLAY_HEADER_NAMES = [
    x.strip()
    for x in os.getenv(
        "AUTH_REPLAY_HEADER_NAMES",
        "Cookie,Authorization,X-Token,token,access_token,isToken,repeatSubmit",
    ).split(",")
    if x.strip()
]

# 网关前缀。前后端分离项目常见 /dev-api；前后端不分离项目可配置为空。
API_GATEWAY_PREFIXES = [x.strip().rstrip("/") for x in os.getenv("API_GATEWAY_PREFIXES", "/dev-api,/prod-api").split(",") if x.strip()]
