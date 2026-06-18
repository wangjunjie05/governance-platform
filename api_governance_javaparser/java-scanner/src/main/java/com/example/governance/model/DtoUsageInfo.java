package com.example.governance.model;

/**
 * DTO/Entity 作为 Controller 入参时的使用场景。
 *
 * 这个对象只服务字段规则降噪：
 * - 同一个类型可能被多个接口使用，任意一次用于写接口，就认为它具备写入场景；
 * - 认证相关场景单独标记，用于账号、密码、验证码等高价值字段检查；
 * - 不在这里做违规判断，只记录上下文，避免字段规则脱离接口场景乱报。
 */
public class DtoUsageInfo {
    public String dtoType;
    public boolean usedByRequestBody;
    public boolean usedByWriteOperation;
    public boolean usedByValidationSensitiveOperation;
    public boolean usedByAuthOperation;
}
