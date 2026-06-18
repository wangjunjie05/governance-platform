package com.example.governance.util;

import com.example.governance.config.RuleConfig;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

/**
 * 类型判断工具。
 *
 * 这里负责区分“可以进入 DTO 字段扫描的业务入参类型”和“明显不适合扫描的类型”。
 * 例如 String、Long、Map、MultipartFile、HttpServletRequest 都不应该当作 DTO 扫字段；
 * BaseEntity、VO、Response、Log 这类类型默认也不参与字段扫描，避免报告噪音过大。
 */
public final class TypeUtils {
    private static final Set<String> SIMPLE_TYPES = new HashSet<>(Arrays.asList(
            "String", "Integer", "Long", "Short", "Byte", "Boolean", "Double", "Float", "BigDecimal", "BigInteger",
            "Date", "LocalDate", "LocalDateTime", "LocalTime", "Timestamp",
            "MultipartFile", "HttpServletRequest", "HttpServletResponse", "ServletRequest", "ServletResponse",
            "Model", "ModelMap", "BindingResult", "Principal", "Authentication", "HttpSession",
            "int", "long", "short", "byte", "boolean", "double", "float", "char"
    ));

    private static final Set<String> COLLECTION_TYPES = new HashSet<>(Arrays.asList(
            "List", "Set", "Collection", "Map", "HashMap", "LinkedHashMap", "JSONArray", "JSONObject", "JsonObject", "JsonArray"
    ));

    private TypeUtils() {
    }

    /** 去除泛型、数组、包名前缀，拿到简单类型名。 */
    public static String removeGeneric(String rawType) {
        String text = rawType == null ? "" : rawType.trim();
        int genericStart = text.indexOf('<');
        if (genericStart >= 0) {
            text = text.substring(0, genericStart);
        }
        while (text.endsWith("[]")) {
            text = text.substring(0, text.length() - 2);
        }
        int dot = text.lastIndexOf('.');
        return dot >= 0 ? text.substring(dot + 1) : text;
    }

    public static boolean isSimpleType(String rawType) {
        return SIMPLE_TYPES.contains(removeGeneric(rawType));
    }

    public static boolean isCollectionOrMap(String rawType) {
        return COLLECTION_TYPES.contains(removeGeneric(rawType));
    }

    /**
     * 判断一个类型是否像 DTO/Entity 入参。
     * 配置化后，排除名单优先来自 RuleConfig。
     */
    public static boolean isLikelyDtoType(String rawType, RuleConfig config) {
        String simpleName = removeGeneric(rawType);
        return !isSimpleType(rawType) && !isCollectionOrMap(rawType) && !isExcludedDtoName(simpleName, config);
    }

    /** 兼容旧调用：没有配置时使用默认配置。 */
    public static boolean isLikelyDtoType(String rawType) {
        return isLikelyDtoType(rawType, RuleConfig.defaultConfig());
    }

    public static boolean isStringType(String rawType) {
        return "string".equals(removeGeneric(rawType).toLowerCase(Locale.ROOT));
    }

    /** 判断字段类型是否属于常见数值类型，用于范围校验检查。 */
    public static boolean isNumericType(String rawType) {
        String type = removeGeneric(rawType).toLowerCase(Locale.ROOT);
        return "int".equals(type) || "integer".equals(type)
                || "long".equals(type) || "short".equals(type) || "byte".equals(type)
                || "double".equals(type) || "float".equals(type)
                || "bigdecimal".equals(type) || "biginteger".equals(type);
    }

    /**
     * 粗略判断字段类型是否像枚举类型。
     * JavaParser 当前没有启用符号解析，这里只按类型名称做保守判断：
     * - 直接声明为 XxxEnum / XxxTypeEnum，一般说明代码层已经限制了取值；
     * - 普通 String/Integer 的 status/type 仍需要依赖注解或字典校验。
     */
    public static boolean looksLikeEnumType(String rawType) {
        String type = removeGeneric(rawType).toLowerCase(Locale.ROOT);
        return type.endsWith("enum");
    }

    /**
     * 默认排除低价值类型，避免日志、基类、返回对象进入字段扫描。
     *
     * 配置项说明：
     * - excludedDtoNames：精确类名排除，例如 BaseEntity；
     * - excludedDtoSuffixes：按后缀排除，例如 VO、Response；
     * - excludedDtoContains：按包含关键词排除，例如 OperLog。
     */
    public static boolean isExcludedDtoName(String simpleName, RuleConfig config) {
        if (simpleName == null || simpleName.isEmpty()) {
            return true;
        }
        if (config.excludedDtoNames.contains(simpleName)) {
            return true;
        }
        String lower = simpleName.toLowerCase(Locale.ROOT);
        for (String suffix : config.excludedDtoSuffixes) {
            if (lower.endsWith(suffix.toLowerCase(Locale.ROOT))) {
                return true;
            }
        }
        for (String part : config.excludedDtoContains) {
            if (lower.contains(part.toLowerCase(Locale.ROOT))) {
                return true;
            }
        }
        return false;
    }

    public static boolean isExcludedDtoName(String simpleName) {
        return isExcludedDtoName(simpleName, RuleConfig.defaultConfig());
    }
}
