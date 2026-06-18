package com.example.governance.model;

/**
 * Controller 方法中的入参信息。
 */
public class ParamInfo {
    public String parameterName;
    public String rawType;
    public String simpleType;
    public boolean requestBody;
    public boolean hasValid;
    public boolean simpleTypeFlag;
    public boolean collectionOrMap;
    public int line;
}
