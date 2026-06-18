# 接口规范扫描工具（JavaParser 版）

这是一个用于 Java / Spring MVC / Spring Boot 项目的接口规范专项检查工具，主要补充现有静态扫描工具不容易覆盖的接口入参校验、错误处理和返回格式问题。

它不替代 SonarQube、P3C、CheckStyle、PMD、SpotBugs 等通用代码质量工具，而是作为补充工具使用。默认策略偏保守，目标是减少误报，让结果更适合作为开发自查、测试设计和接口规范检查的参考。

## 一、工具能检查什么

### 1. 参数检查

检查接口参数是否缺少一些基础限制，主要包括：

```text
1. 必填检查
   例如账号、密码、验证码、关键业务字段是否缺少必填限制。

2. 长度检查
   例如密码、名称、标题、配置项等文本字段是否缺少长度限制。

3. 范围检查
   例如年龄、数量、金额、排序值、页大小等数值字段是否缺少最小值、最大值限制。

4. 取值检查
   例如状态、类型、字典类字段是否缺少允许值限制。

5. Map/List 参数提示
   如果接口直接使用 Map/List 接收参数，工具会提示这类参数不方便逐个字段做统一检查。
```

### 2. 错误处理检查

检查接口出错时是否有比较统一的处理方式，主要包括：

```text
1. 是否有统一错误处理
   检查项目中是否存在统一处理接口错误的代码。

2. 错误返回格式是否统一
   检查错误处理方法的返回格式是否和项目常用返回格式一致。

3. 是否直接打印错误信息
   检查错误处理代码中是否直接打印错误信息，这种写法容易导致日志和返回处理不统一。
```

### 3. 返回格式检查

检查写入类接口的返回结果是否尽量保持统一。查询、校验、下拉树、导出等接口的返回形式差异较大，默认不做强判断，避免误报。

默认识别的常见返回格式包括：

```text
AjaxResult
TableDataInfo
ResponseEntity
R
Result
ApiResult
CommonResult
ResponseResult
```

如果项目有自己的统一返回对象，可以在 `governance_rules.json` 里的 `unifiedReturnTypes` 中补充。

## 二、哪些内容不建议用这个工具判断

下面这些问题不适合仅靠 Java 源码静态扫描判断，工具默认不做强检查：

```text
1. Java 编码规范问题
   建议继续使用 SonarQube、P3C、CheckStyle、PMD、SpotBugs。

2. Maven 依赖冲突、版本问题
   建议使用 mvn dependency:tree 或已有依赖扫描工具。

3. 数据库设计问题
   例如主键、字段类型、关系表设计，需要结合数据库 DDL 和设计评审。

4. 数据量和分页是否满足真实业务量
   需要结合实际数据量和业务场景，静态扫描无法准确判断。

5. for 循环访问数据库导致的性能问题
   理论上可以扫，但误报较高，更适合代码评审、性能测试或专门规则处理。
```

## 三、环境要求

### 运行扫描需要

```text
1. Python 3.8 及以上
   Python 侧只使用标准库，不需要额外 pip install。

2. JDK 8 及以上
   用于运行 JavaParser 扫描器 jar。
   建议使用 JDK 8 / JDK 11 / JDK 17。

3. 扫描器 jar
   java-scanner/target/api-governance-javaparser-scanner-1.0.0.jar
```

### 重新构建 jar 需要

```text
1. Maven 3.6 及以上
2. 能访问 Maven 依赖，或已准备好内网 Maven 仓库 / 本地 Maven 仓库
```

主要 Maven 依赖：

```text
javaparser-core
Gson
maven-shade-plugin
```

离线环境建议先在外网机器完成 Maven 构建，再把完整工具目录带入内网使用。

## 四、目录结构

```text
api_governance_javaparser/
├── governance_rules.json                    # 规则配置文件，换项目优先改这里
├── run_governance_scan.py                   # Python 执行入口
├── governance_py/                           # Python 报告层
│   ├── config.py                            # 默认路径配置
│   ├── java_scanner.py                      # 调用 Java 扫描器
│   ├── output_manager.py                    # 输出目录管理
│   ├── report_writer.py                     # XLSX / summary / prompt 输出
│   └── xlsx_writer.py                       # XLSX 明细报告输出，不依赖第三方库
└── java-scanner/                            # JavaParser 扫描器
    ├── pom.xml
    └── target/
        └── api-governance-javaparser-scanner-1.0.0.jar
```

## 五、使用方式

### 1. 构建 Java 扫描器

如果压缩包中已经包含 jar，可以跳过这一步。

需要重新构建时执行：

```bash
cd api_governance_javaparser/java-scanner
mvn clean package
```

构建完成后会生成：

```text
java-scanner/target/api-governance-javaparser-scanner-1.0.0.jar
```

### 2. 执行扫描

回到工具根目录：

```bash
cd api_governance_javaparser
python run_governance_scan.py --source-path ./你的Java项目 --project-name 项目名
```

Windows 示例：

```powershell
python .\run_governance_scan.py --source-path C:\Users\Administrator\Desktop\RuoYi --project-name RuoYi
```

如果不传 `--project-name`，默认使用源码目录名。

### 3. 指定规则配置文件

默认读取当前目录下的：

```text
governance_rules.json
```

也可以手动指定：

```bash
python run_governance_scan.py \
  --source-path ./你的Java项目 \
  --project-name 项目名 \
  --rule-config ./governance_rules.json
```

### 4. 指定输出目录

默认输出到：

```text
governance_output/项目名_时间戳/
```

也可以指定输出根目录：

```bash
python run_governance_scan.py \
  --source-path ./你的Java项目 \
  --project-name 项目名 \
  --output-root ./output
```

## 六、输出文件说明

每次执行都会生成独立目录，不覆盖历史结果。

```text
governance_output/项目名_时间戳/
├── 项目名_scanner_result.json
├── 项目名_governance_report.xlsx
├── 项目名_governance_summary.txt
└── 项目名_governance_prompt_context.txt
```

文件说明：

```text
scanner_result.json：Java 扫描器原始结构化结果，主要用于排查工具问题。
report.xlsx：完整问题明细，推荐使用 Excel / WPS 打开查看。
summary.txt：扫描摘要，适合快速查看本次扫描概况。
prompt_context.txt：给后续 AI 生成测试脚本使用的上下文。
```

明细报告字段：

```text
风险等级
问题位置
问题类型
问题说明
处理建议
提示原因
涉及类型
字段名
文件路径
行号
```

其中：

```text
问题位置：问题大概出在哪里，例如某个参数类、某个字段或项目级检查。
提示原因：工具为什么提示这个问题，尽量用日常语言说明。
行号：能定位到具体源码行时才显示，无法定位时留空。
```

## 七、规则配置说明

主要配置文件：

```text
governance_rules.json
```

常用配置：

```text
excludedControllerKeywords：排除测试、示例类接口。
excludedPathKeywords：排除 demo、sample、tool 等目录。
readOperationKeywords：识别查询、导出、详情接口，默认不做字段级强检查。
writeOperationKeywords：识别新增、修改、删除、登录、注册等写入类接口。
usernameFields / passwordFields / phoneFields / emailFields / codeFields：重点字段名称。
businessRequiredFields：写接口中建议关注的业务字段。
businessLengthFields：写接口中建议关注长度限制的文本字段。
numericRangeFields：建议关注数值范围的字段。
enumLikeFields：建议关注状态、类型、字典等取值范围的字段。
customValidationAnnotations：项目自定义校验注解。
unifiedReturnTypes：项目统一返回对象白名单。
requireGlobalExceptionHandler：是否检查统一错误处理。
requireExceptionHandlerUnifiedReturn：是否检查错误返回格式。
forbidPrintStackTraceInExceptionHandler：是否检查是否直接打印错误信息。
requireUnifiedReturnType：是否检查写入类接口返回格式是否统一。
```

如果项目有自己的统一返回对象或自定义校验注解，优先修改配置文件，不建议直接改代码。

## 八、使用建议

```text
1. 第一次接入建议直接使用默认配置，先看整体结果。
2. 如果误报偏多，优先调整 governance_rules.json 中的字段关键词和排除规则。
3. 如果项目有统一返回对象，例如 Resp、BaseResponse、JsonResult，需要加入 unifiedReturnTypes。
4. 如果项目有自定义校验注解，例如 @Mobile、@EnumValid、@DictValid，需要加入 customValidationAnnotations。
5. 扫描结果建议作为人工复核和测试设计参考，不建议不经确认直接作为缺陷结论。
```
