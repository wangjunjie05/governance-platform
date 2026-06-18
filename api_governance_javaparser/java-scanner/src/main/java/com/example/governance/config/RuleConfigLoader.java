package com.example.governance.config;

import com.google.gson.Gson;

import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * 规则配置加载器。
 *
 * 运行时如果传入 --config-json，就读取该配置文件；
 * 如果没有传入，使用 RuleConfig.defaultConfig()。
 *
 * 为了保持简单稳定，这里采用“整项覆盖”的方式：
 * - 配置文件中某个列表不为空，就覆盖默认列表；
 * - 配置文件中某个布尔值会直接覆盖默认值；
 * - 不建议在配置文件中写空列表，除非你明确希望关闭该类规则。
 */
public final class RuleConfigLoader {
    private RuleConfigLoader() {
    }

    public static RuleConfig load(Path configPath) throws Exception {
        RuleConfig defaults = RuleConfig.defaultConfig();
        if (configPath == null || !Files.exists(configPath)) {
            return defaults;
        }
        Gson gson = new Gson();
        try (Reader reader = Files.newBufferedReader(configPath, StandardCharsets.UTF_8)) {
            RuleConfig user = gson.fromJson(reader, RuleConfig.class);
            return merge(defaults, user);
        }
    }

    private static RuleConfig merge(RuleConfig d, RuleConfig u) {
        if (u == null) return d;
        if (u.excludedControllerKeywords != null && !u.excludedControllerKeywords.isEmpty()) d.excludedControllerKeywords = u.excludedControllerKeywords;
        if (u.excludedPathKeywords != null && !u.excludedPathKeywords.isEmpty()) d.excludedPathKeywords = u.excludedPathKeywords;
        if (u.readOperationKeywords != null && !u.readOperationKeywords.isEmpty()) d.readOperationKeywords = u.readOperationKeywords;
        if (u.writeOperationKeywords != null && !u.writeOperationKeywords.isEmpty()) d.writeOperationKeywords = u.writeOperationKeywords;
        if (u.usernameFields != null && !u.usernameFields.isEmpty()) d.usernameFields = u.usernameFields;
        if (u.passwordFields != null && !u.passwordFields.isEmpty()) d.passwordFields = u.passwordFields;
        if (u.phoneFields != null && !u.phoneFields.isEmpty()) d.phoneFields = u.phoneFields;
        if (u.emailFields != null && !u.emailFields.isEmpty()) d.emailFields = u.emailFields;
        if (u.codeFields != null && !u.codeFields.isEmpty()) d.codeFields = u.codeFields;
        if (u.businessRequiredFields != null && !u.businessRequiredFields.isEmpty()) d.businessRequiredFields = u.businessRequiredFields;
        if (u.businessLengthFields != null && !u.businessLengthFields.isEmpty()) d.businessLengthFields = u.businessLengthFields;
        if (u.numericRangeFields != null && !u.numericRangeFields.isEmpty()) d.numericRangeFields = u.numericRangeFields;
        if (u.enumLikeFields != null && !u.enumLikeFields.isEmpty()) d.enumLikeFields = u.enumLikeFields;
        if (u.rangeValidationAnnotations != null && !u.rangeValidationAnnotations.isEmpty()) d.rangeValidationAnnotations = u.rangeValidationAnnotations;
        if (u.enumValidationAnnotations != null && !u.enumValidationAnnotations.isEmpty()) d.enumValidationAnnotations = u.enumValidationAnnotations;
        if (u.excludedDtoNames != null && !u.excludedDtoNames.isEmpty()) d.excludedDtoNames = u.excludedDtoNames;
        if (u.excludedDtoSuffixes != null && !u.excludedDtoSuffixes.isEmpty()) d.excludedDtoSuffixes = u.excludedDtoSuffixes;
        if (u.excludedDtoContains != null && !u.excludedDtoContains.isEmpty()) d.excludedDtoContains = u.excludedDtoContains;
        if (u.customValidationAnnotations != null && !u.customValidationAnnotations.isEmpty()) d.customValidationAnnotations = u.customValidationAnnotations;
        if (u.globalExceptionAdviceAnnotations != null && !u.globalExceptionAdviceAnnotations.isEmpty()) d.globalExceptionAdviceAnnotations = u.globalExceptionAdviceAnnotations;
        if (u.exceptionHandlerAnnotations != null && !u.exceptionHandlerAnnotations.isEmpty()) d.exceptionHandlerAnnotations = u.exceptionHandlerAnnotations;
        if (u.unifiedReturnTypes != null && !u.unifiedReturnTypes.isEmpty()) d.unifiedReturnTypes = u.unifiedReturnTypes;
        if (u.pageNumberParamNames != null && !u.pageNumberParamNames.isEmpty()) d.pageNumberParamNames = u.pageNumberParamNames;
        if (u.pageSizeParamNames != null && !u.pageSizeParamNames.isEmpty()) d.pageSizeParamNames = u.pageSizeParamNames;
        if (u.requireGlobalExceptionHandler != null) d.requireGlobalExceptionHandler = u.requireGlobalExceptionHandler;
        if (u.requireExceptionHandlerUnifiedReturn != null) d.requireExceptionHandlerUnifiedReturn = u.requireExceptionHandlerUnifiedReturn;
        if (u.forbidPrintStackTraceInExceptionHandler != null) d.forbidPrintStackTraceInExceptionHandler = u.forbidPrintStackTraceInExceptionHandler;
        if (u.requireUnifiedReturnType != null) d.requireUnifiedReturnType = u.requireUnifiedReturnType;
        if (u.requirePageParamsForListApi != null) d.requirePageParamsForListApi = u.requirePageParamsForListApi;
        return d;
    }
}
