DROP PROCEDURE IF EXISTS UpdateUserPreference;

DELIMITER //

CREATE PROCEDURE UpdateUserPreference(
    IN p_user_id INT
)
BEGIN
    DECLARE v_category VARCHAR(50) DEFAULT '综合';

    IF NOT EXISTS (SELECT 1 FROM `User` WHERE user_id = p_user_id) THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Error: User not found.';
    END IF;

    SELECT category INTO v_category
    FROM (
        SELECT
            CASE
                WHEN query_text REGEXP '新闻|校庆|通知' THEN '新闻'
                WHEN query_text REGEXP '教务|选课|成绩|招生|规章' THEN '教务'
                WHEN query_text REGEXP '科研|论文|研究生|学术' THEN '学术'
                ELSE '综合'
            END AS category,
            COUNT(*) AS cnt,
            MAX(search_time) AS last_time
        FROM SearchLog
        WHERE user_id = p_user_id
        GROUP BY category
        ORDER BY cnt DESC, last_time DESC
        LIMIT 1
    ) AS stats;

    IF v_category IS NULL OR TRIM(v_category) = '' THEN
        SET v_category = '综合';
    END IF;

    IF v_category != '综合' THEN
        INSERT INTO UserPreference (user_id, category, weight)
        VALUES (p_user_id, v_category, 1.05)
        ON DUPLICATE KEY UPDATE 
        weight = weight + 0.1 * (2.0 - weight);
    END IF;
    
END //

DELIMITER ;
