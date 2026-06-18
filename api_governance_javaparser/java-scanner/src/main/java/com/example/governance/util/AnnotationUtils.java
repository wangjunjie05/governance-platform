package com.example.governance.util;

import com.github.javaparser.ast.NodeList;
import com.github.javaparser.ast.expr.AnnotationExpr;

import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * 注解工具类。
 * JavaParser 解析到的注解可能是 @Valid，也可能是 @jakarta.validation.Valid，
 * 因此统一按简单名称判断，避免 javax / jakarta 差异影响兼容性。
 */
public final class AnnotationUtils {
    private AnnotationUtils() {
    }

    public static boolean hasAny(NodeList<AnnotationExpr> annotations, String... names) {
        Set<String> target = new HashSet<>(Arrays.asList(names));
        for (AnnotationExpr annotation : annotations) {
            String simpleName = simpleAnnotationName(annotation.getNameAsString());
            if (target.contains(simpleName)) {
                return true;
            }
        }
        return false;
    }

    public static boolean hasAny(NodeList<AnnotationExpr> annotations, List<String> names) {
        Set<String> target = new HashSet<>(names);
        for (AnnotationExpr annotation : annotations) {
            String simpleName = simpleAnnotationName(annotation.getNameAsString());
            if (target.contains(simpleName)) {
                return true;
            }
        }
        return false;
    }

    public static String simpleAnnotationName(String name) {
        int lastDot = name.lastIndexOf('.');
        return lastDot >= 0 ? name.substring(lastDot + 1) : name;
    }
}
