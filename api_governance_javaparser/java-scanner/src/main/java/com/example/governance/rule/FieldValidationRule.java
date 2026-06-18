package com.example.governance.rule;

import com.example.governance.config.RuleConfig;
import com.example.governance.model.DtoUsageInfo;
import com.example.governance.model.Issue;
import com.example.governance.parser.JavaSourceIndex;
import com.example.governance.util.AnnotationUtils;
import com.example.governance.util.PathUtils;
import com.example.governance.util.TypeUtils;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.FieldDeclaration;
import com.github.javaparser.ast.body.VariableDeclarator;

import java.nio.file.Path;
import java.util.*;

/**
 * DTO/Entity 字段级规则。
 *
 * 这一版采用“平衡模式”：
 * 1. 不再扫描所有 String 字段，避免报告爆炸；
 * 2. 登录/注册/账号类字段保持高价值检查；
 * 3. 写接口中的关键业务字段补充为中风险，提升参考价值；
 * 4. 普通 phone/email 默认不作为问题，只有认证相关 DTO 才作为建议项；
 * 5. 查询对象、VO、日志实体等在 DtoResolver 中已经过滤，这里只处理真实 Controller 入参类型。
 */
public class FieldValidationRule {
    private final RuleConfig config;

    public FieldValidationRule(RuleConfig config) {
        this.config = config;
    }

    public List<Issue> check(String projectName,
                             JavaSourceIndex index,
                             Map<String, Path> dtoTypeToFile,
                             Map<String, DtoUsageInfo> dtoUsageInfoMap,
                             boolean beanValidationUsed) {
        List<Issue> issues = new ArrayList<>();
        for (Map.Entry<String, Path> entry : dtoTypeToFile.entrySet()) {
            String dtoType = entry.getKey();
            Path file = entry.getValue();
            DtoUsageInfo usageInfo = dtoUsageInfoMap.get(dtoType);
            Optional<CompilationUnit> optional = index.getCompilationUnit(file);
            if (!optional.isPresent()) {
                continue;
            }
            CompilationUnit cu = optional.get();
            for (FieldDeclaration field : cu.findAll(FieldDeclaration.class)) {
                for (VariableDeclarator variable : field.getVariables()) {
                    issues.addAll(checkField(projectName, index.getSourceRoot(), file, dtoType,
                            usageInfo, field, variable, beanValidationUsed));
                }
            }
        }
        return issues;
    }

    private List<Issue> checkField(String projectName, Path root, Path file, String dtoType,
                                   DtoUsageInfo usageInfo,
                                   FieldDeclaration field, VariableDeclarator variable,
                                   boolean beanValidationUsed) {
        List<Issue> issues = new ArrayList<>();
        String fieldName = variable.getNameAsString();
        String fieldType = variable.getType().asString();
        boolean stringField = TypeUtils.isStringType(fieldType);
        boolean authRelated = isAuthRelatedDto(dtoType) || (usageInfo != null && usageInfo.usedByAuthOperation);
        boolean writeRelated = usageInfo != null && usageInfo.usedByWriteOperation;

        // 账号/用户名：登录、注册、账号维护场景下优先级最高。
        if (stringField && config.usernameFields.contains(fieldName) && !hasRequired(field)) {
            issues.add(buildFieldIssue(projectName, root, file, dtoType, fieldName, field,
                    "username-missing-required", beanValidationUsed ? "高风险" : "中风险", "高",
                    "账号类字段缺少必填校验",
                    "账号/用户名类字段缺少 @NotBlank/@NotNull/@NotEmpty。",
                    "建议增加 @NotBlank，并按项目规范补充长度限制。"));
        }

        // 密码字段：必填和长度都比较有价值。
        if (stringField && config.passwordFields.contains(fieldName)) {
            if (!hasRequired(field)) {
                issues.add(buildFieldIssue(projectName, root, file, dtoType, fieldName, field,
                        "password-missing-required", beanValidationUsed ? "高风险" : "中风险", "高",
                        "密码字段缺少必填校验",
                        "密码字段缺少 @NotBlank/@NotNull/@NotEmpty。",
                        "建议增加 @NotBlank，并结合密码策略补充 @Size 或自定义校验。"));
            }
            if (!hasLength(field)) {
                issues.add(buildFieldIssue(projectName, root, file, dtoType, fieldName, field,
                        "password-missing-length", beanValidationUsed ? "中风险" : "建议项", "高",
                        "密码字段缺少长度限制",
                        "密码字段缺少 @Size/@Length 等长度限制。",
                        "建议根据密码策略增加长度限制，例如 @Size(min = 6, max = 20)。"));
            }
        }

        // 验证码/编码字段：认证相关一般有价值，普通 code 只作为中风险或建议。
        if (stringField && config.codeFields.contains(fieldName) && !hasRequired(field)) {
            issues.add(buildFieldIssue(projectName, root, file, dtoType, fieldName, field,
                    "code-missing-required", authRelated && beanValidationUsed ? "中风险" : "建议项", "中",
                    "验证码/编码字段缺少必填校验",
                    "验证码或编码类字段缺少必填校验。",
                    "如果该字段用于登录、注册、短信验证等场景，建议增加 @NotBlank。"));
        }

        // 普通 phone/email 不默认报，只有登录/注册/账号类 DTO 才作为建议项提示。
        if (authRelated && stringField && config.phoneFields.contains(fieldName)
                && !(AnnotationUtils.hasAny(field.getAnnotations(), "Pattern") || AnnotationUtils.hasAny(field.getAnnotations(), config.customValidationAnnotations))) {
            issues.add(buildFieldIssue(projectName, root, file, dtoType, fieldName, field,
                    "phone-missing-pattern", "建议项", "中",
                    "认证相关手机号字段缺少格式校验",
                    "登录、注册或账号相关入参中的手机号字段缺少 @Pattern 格式校验。",
                    "如果该字段用于登录、注册、找回密码等场景，建议按项目手机号规则增加 @Pattern 或统一自定义校验。"));
        }

        if (authRelated && stringField && config.emailFields.contains(fieldName)
                && !(AnnotationUtils.hasAny(field.getAnnotations(), "Email", "Pattern") || AnnotationUtils.hasAny(field.getAnnotations(), config.customValidationAnnotations))) {
            issues.add(buildFieldIssue(projectName, root, file, dtoType, fieldName, field,
                    "email-missing-format", "建议项", "中",
                    "认证相关邮箱字段缺少格式校验",
                    "登录、注册或账号相关入参中的邮箱字段缺少 @Email 或 @Pattern 格式校验。",
                    "如果该字段用于登录、注册、找回密码等场景，建议增加 @Email 或项目统一邮箱校验注解。"));
        }

        // 平衡模式补充：写接口中的关键业务字段缺少必填校验，作为中风险参考。
        if (writeRelated && config.businessRequiredFields.contains(fieldName) && !hasRequired(field)) {
            issues.add(buildFieldIssue(projectName, root, file, dtoType, fieldName, field,
                    "business-field-missing-required", beanValidationUsed ? "中风险" : "建议项", "中",
                    "写接口关键业务字段缺少校验",
                    "该字段属于写接口中的常见关键业务字段，但缺少 @NotBlank/@NotNull/@NotEmpty 等校验。",
                    "建议结合业务确认该字段是否必须填写；如果必须填写，补充对应的字段校验。"));
        }

        // 平衡模式补充：关键业务文本字段缺少长度限制，作为建议项而不是风险项。
        if (writeRelated && stringField && config.businessLengthFields.contains(fieldName) && !hasLength(field)) {
            issues.add(buildFieldIssue(projectName, root, file, dtoType, fieldName, field,
                    "business-string-missing-length", "建议项", "中",
                    "写接口关键文本字段缺少长度限制",
                    "该字段属于写接口中的常见文本字段，但缺少 @Size/@Length 等长度限制。",
                    "建议结合数据库字段长度或业务规则补充长度限制，避免过长数据进入后续处理。"));
        }

        // 数值范围校验：只对写接口中的高价值数值字段提示，避免把所有数字字段都报出来。
        // 对应“数值参数需要边界校验”的检查场景。
        boolean numericField = TypeUtils.isNumericType(fieldType);
        if (writeRelated && numericField && config.numericRangeFields.contains(fieldName) && !hasRange(field)) {
            issues.add(buildFieldIssue(projectName, root, file, dtoType, fieldName, field,
                    "numeric-field-missing-range", beanValidationUsed ? "中风险" : "建议项", "中",
                    "数值字段缺少范围校验",
                    "该字段属于写接口中的常见数值/状态字段，但缺少 @Min/@Max/@Range 等范围限制。",
                    "建议结合业务规则补充 @Min/@Max/@Range，或使用项目统一的范围校验注解。"));
        }

        // 枚举/字典取值校验：只对 status/type 等典型枚举字段提示。
        // 如果字段本身已经是 Enum 类型，说明代码层已有一定限制，不再提示。
        if (writeRelated && config.enumLikeFields.contains(fieldName)
                && !TypeUtils.looksLikeEnumType(fieldType)
                && !hasEnumLimit(field)) {
            issues.add(buildFieldIssue(projectName, root, file, dtoType, fieldName, field,
                    "enum-field-missing-limit", beanValidationUsed ? "中风险" : "建议项", "中",
                    "枚举/字典字段缺少取值限制",
                    "该字段看起来像状态、类型或字典字段，但缺少 @Pattern/@EnumValid/@DictValid 等取值限制。",
                    "建议使用枚举类型，或增加 @Pattern、@EnumValid、@DictValid 等校验，限制允许输入的取值范围。"));
        }
        return issues;
    }

    private boolean isAuthRelatedDto(String dtoType) {
        if (dtoType == null) {
            return false;
        }
        String lower = dtoType.toLowerCase(Locale.ROOT);
        return lower.contains("login")
                || lower.contains("register")
                || lower.contains("auth")
                || lower.contains("account")
                || lower.contains("password")
                || lower.contains("pwd")
                || lower.contains("userdto")
                || lower.contains("userrequest");
    }

    private boolean hasRequired(FieldDeclaration field) {
        return AnnotationUtils.hasAny(field.getAnnotations(), "NotNull", "NotBlank", "NotEmpty");
    }

    private boolean hasLength(FieldDeclaration field) {
        return AnnotationUtils.hasAny(field.getAnnotations(), "Size", "Length")
                || AnnotationUtils.hasAny(field.getAnnotations(), config.customValidationAnnotations);
    }

    /** 是否已有数值范围校验。 */
    private boolean hasRange(FieldDeclaration field) {
        return AnnotationUtils.hasAny(field.getAnnotations(), config.rangeValidationAnnotations)
                || AnnotationUtils.hasAny(field.getAnnotations(), config.customValidationAnnotations);
    }

    /** 是否已有枚举/字典取值限制。 */
    private boolean hasEnumLimit(FieldDeclaration field) {
        return AnnotationUtils.hasAny(field.getAnnotations(), config.enumValidationAnnotations)
                || AnnotationUtils.hasAny(field.getAnnotations(), config.customValidationAnnotations);
    }

    private Issue buildFieldIssue(String projectName, Path root, Path file, String dtoType, String fieldName,
                                  FieldDeclaration field, String ruleId, String risk, String confidence,
                                  String type, String desc, String suggestion) {
        Issue issue = new Issue();
        issue.projectName = projectName;
        issue.ruleId = ruleId;
        issue.riskLevel = risk;
        issue.confidence = confidence;
        issue.issueType = type;
        issue.description = desc;
        issue.suggestion = suggestion;
        issue.filePath = PathUtils.relative(root, file);
        issue.line = field.getBegin().map(pos -> pos.line).orElse(0);
        issue.controllerClass = "";
        issue.methodName = "";
        issue.httpMethod = "";
        issue.parameterName = "";
        issue.parameterType = dtoType;
        issue.fieldName = fieldName;
        issue.scanBasis = "接口入参字段检查";
        return issue;
    }
}
