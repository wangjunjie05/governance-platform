package com.example.governance.parser;

import com.example.governance.config.RuleConfig;
import com.example.governance.model.ControllerMethodInfo;
import com.example.governance.model.ParamInfo;
import com.example.governance.util.AnnotationUtils;
import com.example.governance.util.TypeUtils;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.Parameter;
import com.github.javaparser.ast.expr.AnnotationExpr;

import java.nio.file.Path;
import java.util.*;

/**
 * Controller 解析器。
 *
 * 只做结构识别，不做业务判断：
 * - 识别 Spring MVC Controller；
 * - 识别请求方法和请求路径；
 * - 识别参数类型、接口请求参数、@Valid/@Validated；
 * - 给出一个保守的 validationSensitiveOperation 标记，供后续规则降噪。
 */
public class ControllerParser {
    private final RuleConfig config;

    public ControllerParser(RuleConfig config) {
        this.config = config;
    }

    private static final Set<String> CONTROLLER_ANNOTATIONS = new HashSet<>(Arrays.asList("RestController", "Controller"));
    private static final Set<String> MAPPING_ANNOTATIONS = new HashSet<>(Arrays.asList(
            "RequestMapping", "GetMapping", "PostMapping", "PutMapping", "PatchMapping", "DeleteMapping"
    ));

    public List<ControllerMethodInfo> parse(JavaSourceIndex index) {
        List<ControllerMethodInfo> methods = new ArrayList<>();
        for (Map.Entry<Path, CompilationUnit> entry : index.getCompilationUnits().entrySet()) {
            Path file = entry.getKey();
            CompilationUnit cu = entry.getValue();
            cu.findAll(ClassOrInterfaceDeclaration.class).forEach(clazz -> {
                if (!isController(clazz) || shouldExcludeController(file, clazz)) {
                    return;
                }
                clazz.getMethods().forEach(method -> parseMethod(file, clazz, method).ifPresent(methods::add));
            });
        }
        return methods;
    }

    private Optional<ControllerMethodInfo> parseMethod(Path file, ClassOrInterfaceDeclaration clazz, MethodDeclaration method) {
        MappingInfo mappingInfo = resolveMappingInfo(method);
        if (mappingInfo.httpMethod.isEmpty()) {
            return Optional.empty();
        }

        ControllerMethodInfo info = new ControllerMethodInfo();
        info.controllerClass = clazz.getNameAsString();
        info.methodName = method.getNameAsString();
        info.httpMethod = mappingInfo.httpMethod;
        info.mappingPath = mappingInfo.path;
        info.restApi = isRestApi(clazz, method);
        info.writeOperation = isWriteHttpMethod(mappingInfo.httpMethod);
        info.validationSensitiveOperation = isValidationSensitive(info);
        info.sourceFile = file;

        for (Parameter parameter : method.getParameters()) {
            ParamInfo paramInfo = new ParamInfo();
            paramInfo.parameterName = parameter.getNameAsString();
            paramInfo.rawType = parameter.getType().asString();
            paramInfo.simpleType = TypeUtils.removeGeneric(paramInfo.rawType);
            paramInfo.requestBody = AnnotationUtils.hasAny(parameter.getAnnotations(), "RequestBody");
            paramInfo.hasValid = AnnotationUtils.hasAny(parameter.getAnnotations(), "Valid", "Validated");
            paramInfo.simpleTypeFlag = TypeUtils.isSimpleType(paramInfo.rawType);
            paramInfo.collectionOrMap = TypeUtils.isCollectionOrMap(paramInfo.rawType);
            paramInfo.line = parameter.getBegin().map(pos -> pos.line).orElse(0);
            info.params.add(paramInfo);
        }
        return Optional.of(info);
    }

    private boolean isController(ClassOrInterfaceDeclaration clazz) {
        for (AnnotationExpr annotation : clazz.getAnnotations()) {
            if (CONTROLLER_ANNOTATIONS.contains(AnnotationUtils.simpleAnnotationName(annotation.getNameAsString()))) {
                return true;
            }
        }
        return false;
    }

    /**
     * 判断是否是 REST 风格接口。
     * @Controller 既可能是接口，也可能是页面跳转；统一返回检查只适合 REST 接口。
     */
    private boolean isRestApi(ClassOrInterfaceDeclaration clazz, MethodDeclaration method) {
        return AnnotationUtils.hasAny(clazz.getAnnotations(), "RestController", "ResponseBody")
                || AnnotationUtils.hasAny(method.getAnnotations(), "ResponseBody");
    }
    private boolean shouldExcludeController(Path file, ClassOrInterfaceDeclaration clazz) {
        String className = clazz.getNameAsString().toLowerCase(Locale.ROOT);
        for (String keyword : config.excludedControllerKeywords) {
            if (className.contains(keyword)) {
                return true;
            }
        }

        String normalizedPath = file == null ? "" : file.toString().replace('\\', '/').toLowerCase(Locale.ROOT);
        for (String keyword : config.excludedPathKeywords) {
            if (normalizedPath.contains(keyword)) {
                return true;
            }
        }
        return false;
    }


    private MappingInfo resolveMappingInfo(MethodDeclaration method) {
        for (AnnotationExpr annotation : method.getAnnotations()) {
            String name = AnnotationUtils.simpleAnnotationName(annotation.getNameAsString());
            if (!MAPPING_ANNOTATIONS.contains(name)) {
                continue;
            }
            MappingInfo info = new MappingInfo();
            switch (name) {
                case "GetMapping":
                    info.httpMethod = "GET";
                    break;
                case "PostMapping":
                    info.httpMethod = "POST";
                    break;
                case "PutMapping":
                    info.httpMethod = "PUT";
                    break;
                case "PatchMapping":
                    info.httpMethod = "PATCH";
                    break;
                case "DeleteMapping":
                    info.httpMethod = "DELETE";
                    break;
                case "RequestMapping":
                    info.httpMethod = resolveRequestMappingMethod(annotation.toString());
                    break;
                default:
                    info.httpMethod = "UNKNOWN";
            }
            info.path = extractPath(annotation.toString());
            return info;
        }
        return new MappingInfo();
    }

    private String resolveRequestMappingMethod(String annotationText) {
        String upper = annotationText.toUpperCase(Locale.ROOT);
        if (upper.contains("REQUESTMETHOD.POST")) return "POST";
        if (upper.contains("REQUESTMETHOD.PUT")) return "PUT";
        if (upper.contains("REQUESTMETHOD.PATCH")) return "PATCH";
        if (upper.contains("REQUESTMETHOD.DELETE")) return "DELETE";
        if (upper.contains("REQUESTMETHOD.GET")) return "GET";
        return "UNKNOWN";
    }

    /**
     * 简单提取注解中的路径文本，用于辅助判断 list/export/check 等查询类接口。
     * 这里不追求完整解析 Spring 注解属性，只作为降噪辅助，不影响核心 AST 识别。
     */
    private String extractPath(String annotationText) {
        String text = annotationText == null ? "" : annotationText;
        int quoteStart = text.indexOf('"');
        int quoteEnd = quoteStart >= 0 ? text.indexOf('"', quoteStart + 1) : -1;
        if (quoteStart >= 0 && quoteEnd > quoteStart) {
            return text.substring(quoteStart + 1, quoteEnd);
        }
        return "";
    }

    private boolean isWriteHttpMethod(String httpMethod) {
        return "POST".equals(httpMethod) || "PUT".equals(httpMethod)
                || "PATCH".equals(httpMethod) || "DELETE".equals(httpMethod);
    }

    private boolean isValidationSensitive(ControllerMethodInfo info) {
        String methodName = info.methodName == null ? "" : info.methodName.toLowerCase(Locale.ROOT);
        String path = info.mappingPath == null ? "" : info.mappingPath.toLowerCase(Locale.ROOT);

        // 接口请求参数 的接口后续会单独高置信度判断，这里主要服务前后端不分离对象绑定。
        if (!info.writeOperation) {
            return false;
        }
        if (containsAny(methodName, config.readOperationKeywords) || containsAny(path, config.readOperationKeywords)) {
            return false;
        }
        return containsAny(methodName, config.writeOperationKeywords) || containsAny(path, config.writeOperationKeywords)
                || "POST".equals(info.httpMethod) || "PUT".equals(info.httpMethod) || "PATCH".equals(info.httpMethod);
    }

    private boolean containsAny(String text, List<String> keywords) {
        for (String keyword : keywords) {
            if (text.contains(keyword)) {
                return true;
            }
        }
        return false;
    }

    private static class MappingInfo {
        String httpMethod = "";
        String path = "";
    }
}
