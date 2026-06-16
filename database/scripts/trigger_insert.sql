DROP TRIGGER IF EXISTS AfterUserRegister;

DELIMITER //
CREATE TRIGGER AfterUserRegister
AFTER INSERT ON User
FOR EACH ROW
BEGIN
    INSERT INTO UserProfile (user_id, role) 
    VALUES (NEW.user_id, '访客');
    
    INSERT INTO UserPreference (user_id, category, weight) 
    VALUES (NEW.user_id, '新闻', 1.0);
    
    INSERT INTO UserPreference (user_id, category, weight) 
    VALUES (NEW.user_id, '综合', 1.0);
END //
DELIMITER ;