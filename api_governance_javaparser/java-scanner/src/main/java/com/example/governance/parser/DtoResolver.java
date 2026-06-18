package com.example.governance.parser;

import com.example.governance.config.RuleConfig;
import com.example.governance.model.ControllerMethodInfo;
import com.example.governance.model.ParamInfo;
import com.example.governance.rule.ValidationUsageAnalyzer;
import com.example.governance.util.TypeUtils;

import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Controller 入参类型解析器。
 *
 * 设计目标：
 * 1. 只从 Controller 真实方法参数反向定位入参类型，不全项目扫“看起来像 DTO”的类；
 * 2. 接口请求参数 对象入参天然属于请求体，默认允许进入字段级高置信度检查；
 * 3. 前后端不分离的普通对象绑定入参，只在写接口/敏感接口中进入字段级检查；
 * 4. 明显的日志、返回对象、配置对象、基类等默认排除，避免无意义误报；
 * 5. 字段级检查不再强依赖 DTO 已经存在 Bean Validation 注解，否则老项目会被过滤到没有结果。
 */
public class DtoResolver {
    private final RuleConfig config;

    public DtoResolver(RuleConfig config) {
        this.config = config;
    }
    public Map<String, Path> resolveAllRequestDtoFiles(JavaSourceIndex index, List<ControllerMethodInfo> controllerMethods) {
        Map<String, Path> dtoTypeToFile = new LinkedHashMap<>();
        for (ControllerMethodInfo method : controllerMethods) {
            for (ParamInfo param : method.params) {
                if (!TypeUtils.isLikelyDtoType(param.rawType, config) || shouldExcludeType(param.simpleType)) {
                    continue;
                }
                List<Path> files = index.findFilesBySimpleClassName(param.simpleType);
                if (files.size() == 1) {
                    dtoTypeToFile.put(param.simpleType, files.get(0));
                }
                // 多模块同名类不强行猜，避免扫错模块。
            }
        }
        return dtoTypeToFile;
    }

    public Map<String, Path> resolveFieldScanDtos(JavaSourceIndex index,
                                                  List<ControllerMethodInfo> controllerMethods,
                                                  ValidationUsageAnalyzer validationUsageAnalyzer) {
        Map<String, Path> dtoTypeToFile = new LinkedHashMap<>();
        for (ControllerMethodInfo method : controllerMethods) {
            for (ParamInfo param : method.params) {
                if (!shouldConsiderFieldScan(method, param)) {
                    continue;
                }
                List<Path> files = index.findFilesBySimpleClassName(param.simpleType);
                if (files.size() != 1) {
                    continue;
                }
                dtoTypeToFile.put(param.simpleType, files.get(0));
            }
        }
        return dtoTypeToFile;
    }

    private boolean shouldConsiderFieldScan(ControllerMethodInfo method, ParamInfo param) {
        if (!TypeUtils.isLikelyDtoType(param.rawType, config) || shouldExcludeType(param.simpleType)) {
            return false;
        }
        if (param.requestBody) {
            return true;
        }
        // 前后端不分离对象绑定：只处理写接口/敏感接口，过滤 list/query/export/check 等查询对象。
        return method.writeOperation && method.validationSensitiveOperation;
    }

    private boolean shouldExcludeType(String simpleType) {
        return TypeUtils.isExcludedDtoName(simpleType, config);
    }
}
