package com.example.governance.model;

/**
 * 单条扫描问题。
 * 这里全部使用字符串字段，方便 Gson 直接输出 JSON，也方便 Python 生成报告。
 */
public class Issue {
    public String projectName;
    public String ruleId;
    public String riskLevel;
    public String confidence;
    public String issueType;
    public String description;
    public String suggestion;
    public String filePath;
    public int line;
    public String controllerClass;
    public String methodName;
    public String httpMethod;
    public String parameterName;
    public String parameterType;
    public String fieldName;
    public String scanBasis;

    public Issue() {
    }
}
