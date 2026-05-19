-- backend/database/scripts/procedure_update.sql

DROP PROCEDURE IF EXISTS UpdateUserPreference;

DELIMITER //

CREATE PROCEDURE UpdateUserPreference(
    IN p_user_id INT,
    IN p_category VARCHAR(50)
)
BEGIN
    -- 1. 参数合法性校验拦截
    IF p_category IS NULL OR TRIM(p_category) = '' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Error: Category name cannot be empty or NULL.';
    ELSE
        -- 2. 执行更新或插入：若存在记录则权重加0.1，若不存在则新建记录并设权重为1.10
        INSERT INTO UserPreference (user_id, category, weight)
        VALUES (p_user_id, p_category, 1.10)
        ON DUPLICATE KEY UPDATE weight = weight + 0.10;
    END IF;
END //

DELIMITER ;