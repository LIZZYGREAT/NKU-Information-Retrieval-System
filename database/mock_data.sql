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