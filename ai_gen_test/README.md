# AI 接口测试生成工具

基于 Swagger、代码扫描、日志分析，使用 AI 生成 pytest + requests 接口测试脚本。

## 运行方式

```bash
# 使用 config.yaml 配置
python generate_api_tests.py

# 指定参数
python generate_api_tests.py --spec swaggerr.json --mode swagger --exception-mode basic

# 使用接口规范扫描补充信息
python generate_api_tests.py --governance-context ../api_governance_javaparser/governance_output/RuoYi/RuoYi_governance_prompt_context.txt
```

## 三种生成模式

| 模式 | 说明 |
|------|------|
| `swagger` | 仅使用 Swagger 文档 |
| `swagger_code` | Swagger + 代码扫描 |
| `swagger_code_log` | Swagger + 代码扫描 + 日志分析 |

## 异常用例模式

| 模式 | 说明 |
|------|------|
| `basic` | 每类异常生成代表用例 |
| `full` | 可执行异常场景全部生成执行 |

## governance_context 用法

将 JavaParser 扫描生成的 `*_governance_prompt_context.txt` 文件路径传入：

```bash
python generate_api_tests.py --governance-context ../api_governance_javaparser/governance_output/RuoYi/RuoYi_governance_prompt_context.txt
```

或在 `config.yaml` 中配置：

```yaml
governance_context: ../api_governance_javaparser/governance_output/RuoYi/RuoYi_governance_prompt_context.txt
```

不传时原流程完全不变。

## mitmproxy 日志采集

```bash
# 启动代理
python proxy_capture/capture_api_log.py

# 访问接口后，日志保存到 proxy_capture/logs/api_access.log
```

## 输出目录

运行结果保存在 `runs/` 目录下：

```
runs/
└── 20260617_123456_789_swagger_code_log_basic/
    ├── generated_tests/      # 生成的测试脚本
    ├── pytest_reports/       # pytest 执行报告
    ├── summary.txt           # 统计汇总
    └── run_report.xlsx       # 详细报告
```

## 常用命令

```bash
# 查看帮助
python generate_api_tests.py --help

# 只生成 /system/user 模块
python generate_api_tests.py --api-prefix /system/user

# 重复执行 3 次
python generate_api_tests.py --repeat 3
```