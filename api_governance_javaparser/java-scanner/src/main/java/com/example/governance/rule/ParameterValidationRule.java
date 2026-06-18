package com.example.governance.rule;

import com.example.governance.config.RuleConfig;
import com.example.governance.model.ControllerMethodInfo;
import com.example.governance.model.Issue;
import com.example.governance.model.ParamInfo;
import com.example.governance.util.PathUtils;
import com.example.governance.util.TypeUtils;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

/**
 * Controller 入参级规则。
 *
 * 默认策略保持保守，但不能过滤到没有价值：
 * 1. 接口请求参数 Map/List：输出建议项，因为无法做标准 Bean Validation 字段校验；
 * 2. 接口请求参数 对象：只有 DTO 已有字段校验时，才提示缺少 @Valid，避免无效提示；
 * 3. 前后端不分离对象绑定：只有 DTO 已经存在字段校验时，才提示缺少 @Valid；
 * 4. 简单类型、集合普通参数不做校验缺失判断，避免误报。
 */
public class ParameterValidationRule {
    private final RuleConfig config;

    public ParameterValidationRule(RuleConfig config) {
        this.config = config;
    }
    public List<Issue> check(String projectName, Path root, ControllerMethodInfo methodInfo, Set<String> validatedDtoTypes) {
        List<Issue> issues = new ArrayList<>();
        for (ParamInfo param : methodInfo.params) {
            if (shouldSkipParam(param)) {
                continue;
            }

            if (param.requestBody && param.collectionOrMap) {
                issues.add(buildIssue(projectName, root, methodInfo, param,
                        "request-body-non-bean",
                        "建议项",
                        "中",
                        "接口参数使用 Map/List，字段不方便单独检查",
                        "该接口直接使用 Map/List 接收参数，不方便对里面的每个字段做统一校验。",
                        "如果参数结构固定，建议改为明确的 Request DTO；如果是动态结构，可忽略。"));
                continue;
            }

            if (!TypeUtils.isLikelyDtoType(param.rawType, config)) {
                continue;
            }

            boolean dtoHasValidation = validatedDtoTypes.contains(param.simpleType);

            if (param.requestBody && !param.hasValid && dtoHasValidation) {
                issues.add(buildIssue(projectName, root, methodInfo, param,
                        "request-body-missing-valid",
                        "中风险",
                        "高",
                        "接口入参的字段校验可能未生效",
                        "这个接口参数的类里已经写了字段校验，但接口方法上没有触发校验，实际运行时可能不会生效。",
                        "建议补充接口参数校验触发方式，确保字段校验能够生效。"));
                continue;
            }

            if (!param.requestBody
                    && methodInfo.writeOperation
                    && methodInfo.validationSensitiveOperation
                    && dtoHasValidation
                    && !param.hasValid) {
                issues.add(buildIssue(projectName, root, methodInfo, param,
                        "form-object-missing-valid",
                        "中风险",
                        "中",
                        "写入类接口的参数校验可能未生效",
                        "这个写入类接口的参数类里已经写了字段校验，但接口方法上没有触发校验。",
                        "如果希望接口自动校验参数，建议补充对应的校验触发方式。"));
            }
        }
        return issues;
    }

    private boolean shouldSkipParam(ParamInfo param) {
        return param.simpleTypeFlag && !param.collectionOrMap;
    }

    private Issue buildIssue(String projectName, Path root, ControllerMethodInfo methodInfo, ParamInfo param,
                             String ruleId, String risk, String confidence, String type, String desc, String suggestion) {
        Issue issue = new Issue();
        issue.projectName = projectName;
        issue.ruleId = ruleId;
        issue.riskLevel = risk;
        issue.confidence = confidence;
        issue.issueType = type;
        issue.description = desc;
        issue.suggestion = suggestion;
        issue.filePath = PathUtils.relative(root, methodInfo.sourceFile);
        issue.line = param.line;
        issue.controllerClass = methodInfo.controllerClass;
        issue.methodName = methodInfo.methodName;
        issue.httpMethod = methodInfo.httpMethod;
        issue.parameterName = param.parameterName;
        issue.parameterType = param.rawType;
        issue.fieldName = "";
        issue.scanBasis = param.requestBody ? "接口请求参数" : "写入类接口参数";
        return issue;
    }
}
