package com.example.governance.parser;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

/**
 * Java 源码索引。
 * 作用：
 * 1. 找出项目下所有 Java 文件；
 * 2. 使用 JavaParser 解析成 AST；
 * 3. 建立“简单类名 -> 源文件/AST”的索引，后续根据 Controller 入参类型定位 DTO/Entity。
 */
public class JavaSourceIndex {
    private final Path sourceRoot;
    private final JavaParser parser;
    private final List<Path> javaFiles = new ArrayList<>();
    private final Map<Path, CompilationUnit> compilationUnits = new LinkedHashMap<>();
    private final Map<String, List<Path>> simpleNameToFiles = new HashMap<>();

    public JavaSourceIndex(Path sourceRoot) {
        this.sourceRoot = sourceRoot;
        ParserConfiguration configuration = new ParserConfiguration();
        configuration.setLanguageLevel(ParserConfiguration.LanguageLevel.BLEEDING_EDGE);
        this.parser = new JavaParser(configuration);
    }

    public void build() throws IOException {
        Files.walk(sourceRoot)
                .filter(path -> path.toString().endsWith(".java"))
                .filter(this::isNormalSourceFile)
                .forEach(this::parseFileSafely);
    }

    public Path getSourceRoot() {
        return sourceRoot;
    }

    public List<Path> getJavaFiles() {
        return javaFiles;
    }

    public Map<Path, CompilationUnit> getCompilationUnits() {
        return compilationUnits;
    }

    public Optional<CompilationUnit> getCompilationUnit(Path path) {
        return Optional.ofNullable(compilationUnits.get(path));
    }

    public List<Path> findFilesBySimpleClassName(String simpleName) {
        return simpleNameToFiles.getOrDefault(simpleName, Collections.emptyList());
    }

    /**
     * 默认排除构建目录和测试目录，避免扫描 target、build、test fixture 里的代码。
     */
    private boolean isNormalSourceFile(Path path) {
        String normalized = path.toString().replace('\\', '/').toLowerCase(Locale.ROOT);
        return !normalized.contains("/target/")
                && !normalized.contains("/build/")
                && !normalized.contains("/out/")
                && !normalized.contains("/test/")
                && !normalized.contains("/tests/");
    }

    private void parseFileSafely(Path path) {
        try {
            Optional<CompilationUnit> optional = parser.parse(path).getResult();
            if (!optional.isPresent()) {
                return;
            }
            CompilationUnit cu = optional.get();
            javaFiles.add(path);
            compilationUnits.put(path, cu);
            indexClassNames(path, cu);
        } catch (Exception ignored) {
            // 单个文件解析失败不能影响整个项目扫描。真实项目中可能存在生成代码或不完整源码。
        }
    }

    private void indexClassNames(Path path, CompilationUnit cu) {
        cu.findAll(ClassOrInterfaceDeclaration.class).forEach(clazz -> {
            simpleNameToFiles.computeIfAbsent(clazz.getNameAsString(), key -> new ArrayList<>()).add(path);
        });
    }
}
