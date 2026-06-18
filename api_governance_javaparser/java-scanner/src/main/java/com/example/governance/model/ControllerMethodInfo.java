package com.example.governance.model;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/**
 * Controller 方法信息。
 */
public class ControllerMethodInfo {
    public String controllerClass;
    public String methodName;
    public String httpMethod;
    public String mappingPath;
    /** 是否是 REST 接口。@RestController 或方法上有 @ResponseBody 时为 true。
     * 统一返回结构检查只对 REST 接口生效，避免前后端不分离项目的页面跳转 Controller 大量误报。 */
    public boolean restApi;
    public boolean writeOperation;
    public boolean validationSensitiveOperation;
    public Path sourceFile;
    public List<ParamInfo> params = new ArrayList<>();
}
