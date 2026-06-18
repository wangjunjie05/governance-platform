package com.example.governance.util;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

/**
 * Controller 方法用途判断工具。
 *
 * 说明：
 * 不同项目的写法差异很大，不能只依赖方法名或只依赖 HTTP 方法。
 * 这里采用保守策略：
 * 1. 优先根据 HTTP 方法判断写操作；
 * 2. 再结合方法名、路径关键字过滤 list/export/query/check 等查询或辅助接口；
 * 3. 对无法判断的 UNKNOWN 不主动报字段级问题，避免误报。
 */
public final class OperationUtils {
    private static final Set<String> READ_KEYWORDS = new HashSet<>(Arrays.asList(
            "list", "page", "query", "search", "select", "tree", "treeselect", "info",
            "detail", "get", "view", "export", "download", "check", "validate", "count",
            "profile", "avatar", "configkey"
    ));

    private static final Set<String> WRITE_KEYWORDS = new HashSet<>(Arrays.asList(
            "add", "save", "create", "insert", "edit", "update", "modify", "change",
            "delete", "remove", "clean", "clear", "reset", "register", "login", "logout",
            "submit", "import", "upload", "start", "stop", "run", "pause", "resume"
    ));

    private OperationUtils() {
    }

    /**
     * 判断是否值得按“写接口”处理。
     * 返回 true 不代表一定违规，只代表该接口可能修改业务数据。
     */
    public static boolean isBusinessWriteOperation(String httpMethod, String methodName, String mappingPath) {
        String method = normalize(methodName);
        String path = normalize(mappingPath);

        // 明确查询/导出/校验类接口，不做字段级风险扫描。
        if (containsAny(method, READ_KEYWORDS) || containsAny(path, READ_KEYWORDS)) {
            // login/register/reset 这类虽然可能包含 get 字样较少，写关键字优先兜底。
            if (!(containsAny(method, WRITE_KEYWORDS) || containsAny(path, WRITE_KEYWORDS))) {
                return false;
            }
        }

        if ("POST".equals(httpMethod) || "PUT".equals(httpMethod) || "PATCH".equals(httpMethod) || "DELETE".equals(httpMethod)) {
            return true;
        }
        return containsAny(method, WRITE_KEYWORDS) || containsAny(path, WRITE_KEYWORDS);
    }

    public static boolean isReadLikeOperation(String methodName, String mappingPath) {
        String method = normalize(methodName);
        String path = normalize(mappingPath);
        return containsAny(method, READ_KEYWORDS) || containsAny(path, READ_KEYWORDS);
    }

    private static boolean containsAny(String text, Set<String> keywords) {
        for (String keyword : keywords) {
            if (text.contains(keyword)) {
                return true;
            }
        }
        return false;
    }

    private static String normalize(String value) {
        return value == null ? "" : value.toLowerCase(Locale.ROOT).replace("_", "").replace("-", "");
    }
}
