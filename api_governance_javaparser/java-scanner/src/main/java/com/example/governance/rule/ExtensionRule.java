package com.example.governance.rule;

import com.example.governance.config.RuleConfig;
import com.example.governance.model.ControllerMethodInfo;
import com.example.governance.model.Issue;
import com.example.governance.parser.JavaSourceIndex;
import com.example.governance.util.AnnotationUtils;
import com.example.governance.util.PathUtils;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * 扩展规则。
 *
 * 这里放“不是单个字段校验，但很多项目会要求统一”的规则。
 * 本版只纳入适合静态扫描、误报相对可控的内容：
 * 1. 全局异常处理是否存在；
 * 2. 异常处理方法是否返回统一结构、是否直接 printStackTrace；
 * 3. Controller 接口返回值是否统一。
 *
 * 不在这里做性能、数据库设计、依赖冲突等检查，因为这些更适合 Sonar/P3C/Maven 或人工设计评审。
 */
public class ExtensionRule {
    private final RuleConfig config;

    public ExtensionRule(RuleConfig config) {
        this.config = config;
    }

    public List<Issue> check(String projectName, Path root, JavaSourceIndex index, List<ControllerMethodInfo> methods) {
        List<Issue> issues = new ArrayList<>();
        if (Boolean.TRUE.equals(config.requireGlobalExceptionHandler)) {
            checkGlobalExceptionHandler(projectName, root, index, issues);
        }
        if (Boolean.TRUE.equals(config.requireUnifiedReturnType)) {
            checkUnifiedReturnType(projectName, root, index, methods, issues);
        }
        if (Boolean.TRUE.equals(config.requirePageParamsForListApi)) {
            checkPageParams(projectName, root, methods, issues);
        }
        return issues;
    }

    /**
     * 检查项目是否存在 @ControllerAdvice/@RestControllerAdvice + @ExceptionHandler。
     * 同时检查异常处理方法是否返回统一结构，以及是否直接 printStackTrace。
     */
    private void checkGlobalExceptionHandler(String projectName, Path root, JavaSourceIndex index, List<Issue> issues) {
        boolean hasAdvice = false;
        boolean hasHandler = false;
        Path firstAdviceFile = null;

        for (Map.Entry<Path, CompilationUnit> entry : index.getCompilationUnits().entrySet()) {
            Path file = entry.getKey();
            CompilationUnit cu = entry.getValue();
            for (ClassOrInterfaceDeclaration clazz : cu.findAll(ClassOrInterfaceDeclaration.class)) {
                if (!AnnotationUtils.hasAny(clazz.getAnnotations(), config.globalExceptionAdviceAnnotations)) {
                    continue;
                }
                hasAdvice = true;
                if (firstAdviceFile == null) {
                    firstAdviceFile = file;
                }

                for (MethodDeclaration method : clazz.findAll(MethodDeclaration.class)) {
                    if (!AnnotationUtils.hasAny(method.getAnnotations(), config.exceptionHandlerAnnotations)) {
                        continue;
                    }
                    hasHandler = true;
                    if (Boolean.TRUE.equals(config.requireExceptionHandlerUnifiedReturn)) {
                        checkExceptionHandlerReturnType(projectName, root, file, method, issues);
                    }
                    if (Boolean.TRUE.equals(config.forbidPrintStackTraceInExceptionHandler)) {
                        checkPrintStackTrace(projectName, root, file, method, issues);
                    }
                }
            }
        }

        if (!hasAdvice || !hasHandler) {
            Issue issue = new Issue();
            issue.projectName = projectName;
            issue.ruleId = "project-global-exception-handler";
            issue.riskLevel = "中风险";
            issue.confidence = "中";
            issue.issueType = "项目可能缺少统一错误处理";
            issue.description = "未识别到统一处理接口错误的代码。";
            issue.suggestion = "建议统一处理接口错误，并返回固定格式的错误信息；如果项目已有自己的处理方式，可在配置中补充或关闭该检查。";
            issue.filePath = firstAdviceFile == null ? PathUtils.relative(root, root) : PathUtils.relative(root, firstAdviceFile);
            issue.line = 0;
            issue.scanBasis = "补充检查：错误是否统一处理";
            issues.add(issue);
        }
    }

    /** 检查 @ExceptionHandler 方法返回值是否属于统一返回类型。 */
    private void checkExceptionHandlerReturnType(String projectName, Path root, Path file, MethodDeclaration method, List<Issue> issues) {
        String returnType = normalizeReturnType(method.getType().asString());
        if (returnType.isEmpty() || "void".equals(returnType) || config.unifiedReturnTypes.contains(returnType)) {
            return;
        }
        Issue issue = new Issue();
        issue.projectName = projectName;
        issue.ruleId = "project-exception-handler-return-type";
        issue.riskLevel = "建议项";
        issue.confidence = "中";
        issue.issueType = "错误返回格式可能不统一";
        issue.description = "错误处理方法返回类型为 " + returnType + "，不在配置的统一返回格式列表中。";
        issue.suggestion = "建议错误处理统一返回项目规定的响应对象，避免错误信息格式不一致。";
        issue.filePath = PathUtils.relative(root, file);
        issue.line = method.getBegin().map(pos -> pos.line).orElse(0);
        issue.methodName = method.getNameAsString();
        issue.scanBasis = "补充检查：错误返回格式";
        issues.add(issue);
    }

    /** 检查异常处理方法里是否直接调用 printStackTrace。 */
    private void checkPrintStackTrace(String projectName, Path root, Path file, MethodDeclaration method, List<Issue> issues) {
        String methodText = method.toString();
        if (!methodText.contains("printStackTrace(")) {
            return;
        }
        Issue issue = new Issue();
        issue.projectName = projectName;
        issue.ruleId = "project-exception-print-stacktrace";
        issue.riskLevel = "中风险";
        issue.confidence = "中";
        issue.issueType = "错误处理里直接打印错误信息";
        issue.description = "错误处理代码中直接打印了错误信息，可能导致日志和返回处理不统一。";
        issue.suggestion = "建议改为统一记录日志，并统一返回错误信息，不要直接打印错误。";
        issue.filePath = PathUtils.relative(root, file);
        issue.line = method.getBegin().map(pos -> pos.line).orElse(0);
        issue.methodName = method.getNameAsString();
        issue.scanBasis = "补充检查：错误处理方式";
        issues.add(issue);
    }

    /** 检查 Controller 返回值是否属于配置中的统一返回类型。 */
    private void checkUnifiedReturnType(String projectName, Path root, JavaSourceIndex index, List<ControllerMethodInfo> methods, List<Issue> issues) {
        for (ControllerMethodInfo method : methods) {
            if (!method.restApi) {
                continue;
            }
            // 返回格式检查采用保守策略：默认只检查写入类接口。
            // 查询、校验、下拉树、导出等接口经常会返回 List/boolean/String，直接报问题容易误报。
            if (!method.writeOperation) {
                continue;
            }
            String returnType = findReturnType(index, method);
            if (returnType.isEmpty() || config.unifiedReturnTypes.contains(returnType) || "void".equals(returnType)) {
                continue;
            }
            Issue issue = new Issue();
            issue.projectName = projectName;
            issue.ruleId = "project-unified-return-type";
            issue.riskLevel = "建议项";
            issue.confidence = "中";
            issue.issueType = "接口返回格式可能不统一";
            issue.description = "该接口返回类型为 " + returnType + "，不在配置的统一返回格式列表中。";
            issue.suggestion = "如项目要求统一返回格式，可改为统一返回对象；如当前返回类型合理，可在配置中增加 unifiedReturnTypes。";
            issue.filePath = PathUtils.relative(root, method.sourceFile);
            issue.line = 0;
            issue.controllerClass = method.controllerClass;
            issue.methodName = method.methodName;
            issue.httpMethod = method.httpMethod;
            issue.scanBasis = "补充检查：接口返回格式";
            issues.add(issue);
        }
    }

    /** 检查 list/page/query 这类分页接口是否出现页码和每页数量参数。默认关闭。 */
    private void checkPageParams(String projectName, Path root, List<ControllerMethodInfo> methods, List<Issue> issues) {
        for (ControllerMethodInfo method : methods) {
            String name = normalize(method.methodName + " " + method.mappingPath);
            if (!(name.contains("list") || name.contains("page") || name.contains("query"))) {
                continue;
            }
            boolean hasPageNum = false;
            boolean hasPageSize = false;
            for (com.example.governance.model.ParamInfo p : method.params) {
                String paramName = p.parameterName == null ? "" : p.parameterName;
                if (containsIgnoreCase(config.pageNumberParamNames, paramName)) hasPageNum = true;
                if (containsIgnoreCase(config.pageSizeParamNames, paramName)) hasPageSize = true;
            }
            if (!hasPageNum || !hasPageSize) {
                Issue issue = new Issue();
                issue.projectName = projectName;
                issue.ruleId = "project-page-params";
                issue.riskLevel = "建议项";
                issue.confidence = "低";
                issue.issueType = "分页接口可能缺少分页参数";
                issue.description = "该接口名称或路径像分页/列表查询，但没有识别到配置中的分页参数。";
                issue.suggestion = "如果项目使用统一分页封装，可关闭该规则；否则建议确认是否包含 pageNum/pageSize 等分页参数。";
                issue.filePath = PathUtils.relative(root, method.sourceFile);
                issue.line = 0;
                issue.controllerClass = method.controllerClass;
                issue.methodName = method.methodName;
                issue.httpMethod = method.httpMethod;
                issue.scanBasis = "补充检查：分页参数";
                issues.add(issue);
            }
        }
    }

    private String findReturnType(JavaSourceIndex index, ControllerMethodInfo methodInfo) {
        return index.getCompilationUnit(methodInfo.sourceFile)
                .flatMap(cu -> cu.findAll(MethodDeclaration.class).stream()
                        .filter(m -> m.getNameAsString().equals(methodInfo.methodName))
                        .findFirst())
                .map(m -> normalizeReturnType(m.getType().asString()))
                .orElse("");
    }

    private String normalizeReturnType(String type) {
        if (type == null) {
            return "";
        }
        String text = type.trim();
        int generic = text.indexOf('<');
        if (generic >= 0) text = text.substring(0, generic);
        int dot = text.lastIndexOf('.');
        return dot >= 0 ? text.substring(dot + 1) : text;
    }

    private boolean containsIgnoreCase(List<String> values, String target) {
        for (String value : values) {
            if (value.equalsIgnoreCase(target)) return true;
        }
        return false;
    }

    private String normalize(String text) {
        return text == null ? "" : text.toLowerCase(Locale.ROOT);
    }
}
