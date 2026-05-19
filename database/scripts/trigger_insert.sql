-- backend/database/scripts/trigger_insert.sql

DROP TRIGGER IF EXISTS AfterUserRegister;

DELIMITER //

CREATE TRIGGER AfterUserRegister
AFTER INSERT ON User
FOR EACH ROW
BEGIN
    -- 当新用户注册成功后，自动插入一条默认的'综合'类偏好记录，初始权重为1.00
    INSERT INTO UserPreference (user_id, category, weight)
    VALUES (NEW.user_id, '综合', 1.00);
END //

DELIMITER ;