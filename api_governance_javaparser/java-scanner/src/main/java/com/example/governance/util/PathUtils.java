package com.example.governance.util;

import java.nio.file.Path;

/**
 * 路径工具。
 * 报告里默认使用相对路径，避免输出本机绝对路径，方便在不同机器上阅读。
 */
public final class PathUtils {
    private PathUtils() {
    }

    public static String relative(Path root, Path file) {
        try {
            return root.toAbsolutePath().normalize()
                    .relativize(file.toAbsolutePath().normalize())
                    .toString()
                    .replace('\\', '/');
        } catch (Exception e) {
            return file.toString().replace('\\', '/');
        }
    }
}
