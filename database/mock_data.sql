-- backend/database/mock_data.sql
-- 1. 注入网页快照映射元数据
INSERT INTO WebPageCache (url, title, snapshot_path) VALUES 
('https://news.nankai.edu.cn/1.html', '南开大学百年校庆', '../backend/snapshots/mock_1.html'),
('https://cc.nankai.edu.cn/2.html', '计算机学院2026年招生简章.pdf', '../backend/snapshots/mock_2.html');

-- 2. 注入测试用户 (密码均为明文123456的哈希值，此处用伪哈希代替演示)
INSERT INTO User (username, email, password_hash) VALUES 
('test_user', 'test@nankai.edu.cn', 'scrypt:32768:8:1$mockhash...');

-- 3. 注入搜索日志（验证联想词与时间倒序）
INSERT INTO SearchLog (user_id, query_text, search_type) VALUES 
(1, '南开新闻', 'site'),
(1, '计算机学院', 'phrase');


-- 验证用户是否注入
SELECT * FROM User; 
-- 预期输出：存在一行 username='test_user' 的记录

-- 验证网页缓存是否注入
SELECT * FROM WebPageCache;
-- 预期输出：存在 2 条 URL 记录

-- 验证搜索日志是否注入
SELECT * FROM SearchLog;
-- 预期输出：存在 2 条查询记录

INSERT INTO User (username, email, password_hash) VALUES ('trigger_test', 'test@test.com', 'dummy_hash');
-- 之后执行：
SELECT * FROM UserPreference WHERE user_id = LAST_INSERT_ID();


CREATE USER IF NOT EXISTS 'dev_user'@'localhost' IDENTIFIED BY 'Qq142536789..';

GRANT ALL PRIVILEGES ON nku_search_dev.* TO 'dev_user'@'localhost';

FLUSH PRIVILEGES;



-- 统计网页快照表中的总记录数
SELECT COUNT(*) AS total_pages FROM WebPageCache;

-- 如果你想查看每个用户有多少搜索历史
SELECT user_id, COUNT(*) AS search_count 
FROM SearchLog 
GROUP BY user_id;

SELECT 
    table_schema AS "Database", 
    SUM(data_length + index_length) / 1024 / 1024 AS "Size (MB)" 
FROM information_schema.TABLES 
WHERE table_schema = 'nku_search_dev'  
GROUP BY table_schema;