package com.example.governance.config;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * 规则配置对象。
 *
 * 这个类对应根目录下的 governance_rules.json。
 * 设计目的：
 * 1. 把“哪些字段算重点字段”“哪些类/路径要排除”“哪些扩展规则要开启”从代码中抽出来；
 * 2. 换项目时优先改配置文件，而不是改 Java 代码；
 * 3. 默认配置走保守策略，避免真实项目中误报过多。
 *
 * 注意：
 * - 这里的字段全部用 public，是为了让 Gson 可以直接读取 JSON；
 * - 配置文件里可以只写要覆盖的字段，没写的字段会使用 defaultConfig() 的默认值；
 * - JSON 中额外的说明字段会被 Gson 忽略，不影响运行。
 */
public class RuleConfig {
    /** 排除 Controller 类名关键词，例如 TestController、DemoController。 */
    public List<String> excludedControllerKeywords = new ArrayList<>();

    /** 排除路径关键词，例如 /controller/tool/、/demo/。 */
    public List<String> excludedPathKeywords = new ArrayList<>();

    /** 查询类方法/路径关键词。命中后默认不做字段级风险扫描。 */
    public List<String> readOperationKeywords = new ArrayList<>();

    /** 写操作方法/路径关键词。用于前后端不分离对象绑定入参判断。 */
    public List<String> writeOperationKeywords = new ArrayList<>();

    /** 需要按账号类字段检查的字段名。 */
    public List<String> usernameFields = new ArrayList<>();

    /** 需要按密码字段检查的字段名。 */
    public List<String> passwordFields = new ArrayList<>();

    /** 手机号字段名。默认只在认证/账号相关 DTO 中作为建议项提示。 */
    public List<String> phoneFields = new ArrayList<>();

    /** 邮箱字段名。默认只在认证/账号相关 DTO 中作为建议项提示。 */
    public List<String> emailFields = new ArrayList<>();

    /** 验证码/编码字段名。 */
    public List<String> codeFields = new ArrayList<>();

    /** 写接口中疑似关键业务字段。缺少必填校验时默认输出中风险/建议项。 */
    public List<String> businessRequiredFields = new ArrayList<>();

    /** 写接口中疑似需要长度限制的文本字段。默认输出建议项。 */
    public List<String> businessLengthFields = new ArrayList<>();

    /**
     * 写接口中疑似需要数值范围限制的字段。
     * 例如 sort/orderNum/status/type 等字段，通常应通过 @Min/@Max/@Range 或枚举/字典校验限制范围。
     */
    public List<String> numericRangeFields = new ArrayList<>();

    /**
     * 写接口中疑似枚举/字典字段。
     * 例如 status/type/roleKey/dictType 等字段，通常应通过 @Pattern/@EnumValid/@DictValid 或枚举类型限制取值。
     */
    public List<String> enumLikeFields = new ArrayList<>();

    /** 范围校验注解。项目自定义的 @RangeValid 之类也可以加到配置里。 */
    public List<String> rangeValidationAnnotations = new ArrayList<>();

    /** 枚举/字典校验注解。项目自定义的 @DictValid/@EnumValid 可配置在这里。 */
    public List<String> enumValidationAnnotations = new ArrayList<>();

    /** 明确排除的 DTO/Entity 类型名。 */
    public List<String> excludedDtoNames = new ArrayList<>();

    /** 按类名后缀排除 DTO/Entity，例如 VO、Response、Result。 */
    public List<String> excludedDtoSuffixes = new ArrayList<>();

    /** 按类名包含关系排除 DTO/Entity，例如 OperLog、JobLog。 */
    public List<String> excludedDtoContains = new ArrayList<>();

    /** 项目自定义校验注解。比如项目封装了 @Mobile、@DictValid，可以加到这里。 */
    public List<String> customValidationAnnotations = new ArrayList<>();

    /** 是否检查全局异常处理类。默认开启，属于低误报扩展规则。 */
    public Boolean requireGlobalExceptionHandler = true;

    /** 全局异常处理注解名称。 */
    public List<String> globalExceptionAdviceAnnotations = new ArrayList<>();

    /** 异常处理方法注解名称。 */
    public List<String> exceptionHandlerAnnotations = new ArrayList<>();

    /**
     * 是否检查异常处理方法是否返回统一结构。
     * 只检查 @ExceptionHandler 方法的返回类型，低误报，默认开启。
     */
    public Boolean requireExceptionHandlerUnifiedReturn = true;

    /**
     * 是否检查异常处理方法里是否直接 printStackTrace。
     * 这类写法容易把系统异常细节直接暴露出来，默认开启。
     */
    public Boolean forbidPrintStackTraceInExceptionHandler = true;

    /** 是否检查 Controller 返回值统一。默认开启，用于发现接口返回结构不统一问题。 */
    public Boolean requireUnifiedReturnType = true;

    /** 允许的统一返回类型。只有 requireUnifiedReturnType=true 时才使用。 */
    public List<String> unifiedReturnTypes = new ArrayList<>();

    /** 是否检查分页接口参数。默认关闭，因为不同项目分页封装差异很大。 */
    public Boolean requirePageParamsForListApi = false;

    /** 分页接口中期望出现的页码参数名。 */
    public List<String> pageNumberParamNames = new ArrayList<>();

    /** 分页接口中期望出现的每页数量参数名。 */
    public List<String> pageSizeParamNames = new ArrayList<>();

    /** 创建默认配置。默认配置偏保守，优先降低误报。 */
    public static RuleConfig defaultConfig() {
        RuleConfig c = new RuleConfig();
        c.excludedControllerKeywords.addAll(Arrays.asList("testcontroller", "democontroller", "examplecontroller", "samplecontroller"));
        c.excludedPathKeywords.addAll(Arrays.asList("/controller/tool/", "/controller/demo/", "/controller/example/", "/demo/", "/sample/"));
        c.readOperationKeywords.addAll(Arrays.asList("list", "page", "query", "search", "select", "export", "download", "check", "tree", "view", "detail", "info", "profile", "index", "main", "monitor", "cache", "get", "find", "ajax", "option"));
        c.writeOperationKeywords.addAll(Arrays.asList("add", "save", "create", "insert", "edit", "update", "modify", "change", "submit", "register", "login", "reset", "password", "pwd", "delete", "remove", "import", "upload"));
        c.usernameFields.addAll(Arrays.asList("username", "userName", "loginName", "account", "accountName"));
        c.passwordFields.addAll(Arrays.asList("password", "oldPassword", "newPassword", "confirmPassword"));
        c.phoneFields.addAll(Arrays.asList("phone", "mobile", "mobilePhone", "telephone", "tel"));
        c.emailFields.add("email");
        c.codeFields.addAll(Arrays.asList("code", "captcha", "verifyCode", "smsCode", "uuid"));
        c.businessRequiredFields.addAll(Arrays.asList("name", "title", "type", "status", "sort", "orderNum", "parentId", "deptId", "roleId", "postId", "dictType", "dictLabel", "dictValue", "configKey", "configValue", "jobName", "jobGroup", "cronExpression", "menuName", "perms", "noticeTitle", "noticeType"));
        c.businessLengthFields.addAll(Arrays.asList("name", "title", "dictLabel", "dictValue", "configKey", "configValue", "jobName", "jobGroup", "cronExpression", "menuName", "perms", "noticeTitle"));
        c.numericRangeFields.addAll(Arrays.asList("sort", "orderNum", "order", "priority", "status", "type", "age", "count", "num", "number", "quantity", "amount", "price", "min", "max", "limit"));
        c.enumLikeFields.addAll(Arrays.asList("status", "type", "sex", "gender", "state", "flag", "enabled", "visible", "delFlag", "menuType", "noticeType", "dictType", "jobGroup", "roleKey"));
        c.rangeValidationAnnotations.addAll(Arrays.asList("Min", "Max", "Range", "DecimalMin", "DecimalMax", "Positive", "PositiveOrZero", "Negative", "NegativeOrZero"));
        c.enumValidationAnnotations.addAll(Arrays.asList("Pattern", "EnumValid", "DictValid", "InEnum", "ValueOfEnum"));
        c.excludedDtoNames.addAll(Arrays.asList("BaseEntity", "TreeEntity", "BaseController", "AjaxResult", "R", "Result", "TableDataInfo", "GenTable", "GenTableColumn"));
        c.excludedDtoSuffixes.addAll(Arrays.asList("Log", "Logs", "History", "Record", "Records", "VO", "Vo", "View", "Response", "Result", "Constant", "Constants", "Config", "Properties"));
        c.excludedDtoContains.addAll(Arrays.asList("OperLog", "JobLog", "Logininfor"));
        c.customValidationAnnotations.addAll(Arrays.asList("Mobile", "Phone", "DictValid", "EnumValid", "IdCard", "SensitiveWord"));
        c.globalExceptionAdviceAnnotations.addAll(Arrays.asList("RestControllerAdvice", "ControllerAdvice"));
        c.exceptionHandlerAnnotations.add("ExceptionHandler");
        c.unifiedReturnTypes.addAll(Arrays.asList("AjaxResult", "R", "Result", "ApiResult", "CommonResult", "ResponseResult", "TableDataInfo"));
        c.pageNumberParamNames.addAll(Arrays.asList("pageNum", "pageNo", "page", "current"));
        c.pageSizeParamNames.addAll(Arrays.asList("pageSize", "size", "limit"));
        return c;
    }
}
