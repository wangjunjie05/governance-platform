package com.example.governance.parser;

import com.example.governance.config.RuleConfig;
import com.example.governance.model.ControllerMethodInfo;
import com.example.governance.model.DtoUsageInfo;
import com.example.governance.model.Issue;
import com.example.governance.model.ParamInfo;
import com.example.governance.model.ScanResult;
import com.example.governance.rule.ExtensionRule;
import com.example.governance.rule.FieldValidationRule;
import com.example.governance.rule.ParameterValidationRule;
import com.example.governance.rule.ValidationUsageAnalyzer;

import java.nio.file.Path;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * 项目扫描入口。
 *
 * 平衡模式核心思路：
 * 1. JavaParser 负责解析 Java AST，避免靠文本正则猜 Controller 和参数；
 * 2. 只从 Controller 真实请求参数反向定位 DTO/Entity，不全项目扫描普通类；
 * 3. 字段规则结合 Controller 使用场景判断风险，避免脱离接口语义乱报；
 * 4. 认证类字段重点检查，写接口关键业务字段作为中风险/建议项补充；
 * 5. 目标是在“低误报”和“有参考价值”之间取得平衡。
 */
public class ProjectScanner {
    private final RuleConfig config;
    private final Path configPath;

    public ProjectScanner(RuleConfig config, Path configPath) {
        this.config = config;
        this.configPath = configPath;
    }

    public ScanResult scan(String projectName, Path sourcePath) throws Exception {
        JavaSourceIndex index = new JavaSourceIndex(sourcePath);
        index.build();

        ControllerParser controllerParser = new ControllerParser(config);
        List<ControllerMethodInfo> controllerMethods = controllerParser.parse(index);

        ValidationUsageAnalyzer validationUsageAnalyzer = new ValidationUsageAnalyzer(config);
        boolean beanValidationUsed = validationUsageAnalyzer.isBeanValidationUsed(index);

        DtoResolver dtoResolver = new DtoResolver(config);
        Map<String, Path> fieldScanDtoFiles = dtoResolver.resolveFieldScanDtos(index, controllerMethods, validationUsageAnalyzer);

        Set<String> validatedDtoTypes = new HashSet<>();
        for (Map.Entry<String, Path> entry : fieldScanDtoFiles.entrySet()) {
            if (validationUsageAnalyzer.hasBeanValidation(index, entry.getValue())) {
                validatedDtoTypes.add(entry.getKey());
            }
        }

        ScanResult result = new ScanResult();
        result.projectName = projectName;
        result.sourcePath = sourcePath.toAbsolutePath().normalize().toString();
        result.javaFileCount = index.getJavaFiles().size();
        result.controllerCount = (int) controllerMethods.stream().map(m -> m.controllerClass).distinct().count();
        result.requestParamCount = controllerMethods.stream().mapToInt(m -> m.params.size()).sum();
        result.dtoFieldScanClassCount = fieldScanDtoFiles.size();
        result.beanValidationUsed = beanValidationUsed;
        result.ruleConfigPath = configPath == null ? "内置默认配置" : configPath.toString();
        if (Boolean.TRUE.equals(config.requireGlobalExceptionHandler)) result.enabledProjectRules.add("是否有统一错误处理");
        if (Boolean.TRUE.equals(config.requireExceptionHandlerUnifiedReturn)) result.enabledProjectRules.add("错误返回格式是否统一");
        if (Boolean.TRUE.equals(config.forbidPrintStackTraceInExceptionHandler)) result.enabledProjectRules.add("是否直接打印错误信息");
        if (Boolean.TRUE.equals(config.requireUnifiedReturnType)) result.enabledProjectRules.add("接口返回格式是否统一");
        if (Boolean.TRUE.equals(config.requirePageParamsForListApi)) result.enabledProjectRules.add("分页参数是否完整");
        result.scannedDtoClasses.addAll(fieldScanDtoFiles.keySet());

        ParameterValidationRule parameterRule = new ParameterValidationRule(config);
        for (ControllerMethodInfo method : controllerMethods) {
            List<Issue> issues = parameterRule.check(projectName, sourcePath, method, validatedDtoTypes);
            result.issues.addAll(issues);
        }

        FieldValidationRule fieldRule = new FieldValidationRule(config);
        Map<String, DtoUsageInfo> dtoUsageInfoMap = buildDtoUsageInfo(controllerMethods, fieldScanDtoFiles);
        result.issues.addAll(fieldRule.check(projectName, index, fieldScanDtoFiles, dtoUsageInfoMap, beanValidationUsed));

        ExtensionRule extensionRule = new ExtensionRule(config);
        result.issues.addAll(extensionRule.check(projectName, sourcePath, index, controllerMethods));
        return result;
    }

    /**
     * 汇总每个入参类型在 Controller 中的使用场景。
     *
     * 字段规则不能只看字段名，否则不同项目会误报很多。
     * 例如 phone/email 在普通资料维护里通常只适合作为建议项，
     * 但 username/password/code 在登录注册接口中就更值得重点关注。
     */
    private Map<String, DtoUsageInfo> buildDtoUsageInfo(List<ControllerMethodInfo> controllerMethods,
                                                        Map<String, Path> fieldScanDtoFiles) {
        Map<String, DtoUsageInfo> usageMap = new LinkedHashMap<>();
        for (ControllerMethodInfo method : controllerMethods) {
            for (ParamInfo param : method.params) {
                if (!fieldScanDtoFiles.containsKey(param.simpleType)) {
                    continue;
                }
                DtoUsageInfo usage = usageMap.computeIfAbsent(param.simpleType, key -> {
                    DtoUsageInfo info = new DtoUsageInfo();
                    info.dtoType = key;
                    return info;
                });
                usage.usedByRequestBody = usage.usedByRequestBody || param.requestBody;
                usage.usedByWriteOperation = usage.usedByWriteOperation || method.writeOperation;
                usage.usedByValidationSensitiveOperation = usage.usedByValidationSensitiveOperation || method.validationSensitiveOperation;
                usage.usedByAuthOperation = usage.usedByAuthOperation || isAuthRelated(method, param.simpleType);
            }
        }
        return usageMap;
    }

    private boolean isAuthRelated(ControllerMethodInfo method, String dtoType) {
        String text = ((method.methodName == null ? "" : method.methodName) + " "
                + (method.mappingPath == null ? "" : method.mappingPath) + " "
                + (dtoType == null ? "" : dtoType)).toLowerCase(Locale.ROOT);
        return text.contains("login")
                || text.contains("register")
                || text.contains("auth")
                || text.contains("password")
                || text.contains("pwd")
                || text.contains("account");
    }
}
