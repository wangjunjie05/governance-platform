package com.example.governance.rule;

import com.example.governance.config.RuleConfig;
import com.example.governance.parser.JavaSourceIndex;
import com.example.governance.util.AnnotationUtils;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.FieldDeclaration;
import com.github.javaparser.ast.body.Parameter;

import java.nio.file.Path;
import java.util.Optional;

/**
 * Bean Validation 使用情况分析。
 *
 * 设计原则：
 * - 项目级：用于判断整个项目是否存在 Bean Validation 体系；
 * - 类级：用于判断某个 DTO/Entity 是否已经显式使用 Bean Validation；
 * - 入参缺少 @Valid 这类问题，只有目标类型本身存在字段校验注解时才有明确意义。
 */
public class ValidationUsageAnalyzer {
    private final RuleConfig config;

    public ValidationUsageAnalyzer(RuleConfig config) {
        this.config = config;
    }
    public boolean isBeanValidationUsed(JavaSourceIndex index) {
        return index.getCompilationUnits().values().stream().anyMatch(this::hasBeanValidationInCompilationUnit);
    }

    public boolean hasBeanValidation(JavaSourceIndex index, Path file) {
        Optional<CompilationUnit> optional = index.getCompilationUnit(file);
        return optional.isPresent() && hasBeanValidationInCompilationUnit(optional.get());
    }

    private boolean hasBeanValidationInCompilationUnit(CompilationUnit cu) {
        boolean fieldValidation = cu.findAll(FieldDeclaration.class).stream()
                .anyMatch(field -> AnnotationUtils.hasAny(field.getAnnotations(),
                        "NotNull", "NotBlank", "NotEmpty", "Size", "Length", "Pattern", "Email",
                        "Min", "Max", "DecimalMin", "DecimalMax", "Past", "Future")
                        || AnnotationUtils.hasAny(field.getAnnotations(), config.customValidationAnnotations));
        boolean paramValidation = cu.findAll(Parameter.class).stream()
                .anyMatch(param -> AnnotationUtils.hasAny(param.getAnnotations(), "Valid", "Validated"));
        return fieldValidation || paramValidation;
    }
}
