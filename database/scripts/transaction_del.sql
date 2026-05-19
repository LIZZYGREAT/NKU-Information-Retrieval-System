-- backend/database/scripts/transaction_del.sql

DROP PROCEDURE IF EXISTS DeleteUserTransactionally;

DELIMITER //

CREATE PROCEDURE DeleteUserTransactionally(IN p_user_id INT)
BEGIN
    -- 声明异常处理：遇到任何 SQL 异常时自动触发回滚
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        -- 实际业务中可视需求记录错误日志到单独的表，此处返回状态提示
        SELECT 'Error: Transaction failed and rolled back.' AS status;
    END;

    -- 开启事务
    START TRANSACTION;

    -- 1. 删除依赖表 UserPreference 的记录
    DELETE FROM UserPreference WHERE user_id = p_user_id;

    -- 2. 删除依赖表 SearchLog 的记录
    DELETE FROM SearchLog WHERE user_id = p_user_id;

    -- 3. 删除被参照的主表 User 的记录
    DELETE FROM User WHERE user_id = p_user_id;

    -- 若所有 DELETE 操作均未触发异常，则提交事务
    COMMIT;
    
    SELECT 'Success: User and related records deleted transactionally.' AS status;
END //

DELIMITER ;