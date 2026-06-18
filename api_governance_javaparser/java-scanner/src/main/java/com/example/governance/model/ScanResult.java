package com.example.governance.model;

import java.util.ArrayList;
import java.util.List;

/**
 * 扫描结果汇总对象。
 * Java 侧只负责输出结构化 JSON，XLSX 和文本报告由 Python 侧生成。
 */
public class ScanResult {
    public String projectName;
    public String sourcePath;
    public int javaFileCount;
    public int controllerCount;
    public int requestParamCount;
    public int dtoFieldScanClassCount;
    public boolean beanValidationUsed;
    public String ruleConfigPath;
    public List<String> enabledProjectRules = new ArrayList<>();
    public List<String> scannedDtoClasses = new ArrayList<>();
    public List<Issue> issues = new ArrayList<>();
}
