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


SELECT * FROM WebPageCache WHERE url = 'https://news.nankai.edu.cn/index.shtml';

TRUNCATE TABLE WebPageCache;

SELECT * FROM UserProfile;


TRUNCATE TABLE CollegeDomain;

INSERT INTO CollegeDomain (college_name, domain_url, category, sub_category) VALUES
-- 人文社科类
('文学院', 'wxy.nankai.edu.cn', '人文社科类', '人文学科群'),
('历史学院', 'history.nankai.edu.cn', '人文社科类', '人文学科群'),
('哲学院', 'phil.nankai.edu.cn', '人文社科类', '人文学科群'),
('外国语学院', 'fsc.nankai.edu.cn', '人文社科类', '人文学科群'),
('汉语言文化学院', 'hyxy.nankai.edu.cn', '人文社科类', '人文学科群'),
('法学院', 'law.nankai.edu.cn', '人文社科类', '社会科学群'),
('周恩来政府管理学院', 'zf.nankai.edu.cn', '人文社科类', '社会科学群'),
('马克思主义学院', 'my.nankai.edu.cn', '人文社科类', '社会科学群'),
('社会学院', 'shxy.nankai.edu.cn', '人文社科类', '社会科学群'),
('新闻与传播学院', 'jc.nankai.edu.cn', '人文社科类', '社会科学群'),
('经济学院', 'eco.nankai.edu.cn', '人文社科类', '经济管理群'),
('金融学院', 'finance.nankai.edu.cn', '人文社科类', '经济管理群'),
('商学院', 'bs.nankai.edu.cn', '人文社科类', '经济管理群'),
('旅游与服务学院', 'tas.nankai.edu.cn', '人文社科类', '经济管理群'),
('国际教育学院', 'sie.nankai.edu.cn', '人文社科类', '直属与交叉群'),

-- 理工医学类
('数学科学学院', 'math.nankai.edu.cn', '理工医学类', '数学群'),
('统计与数据科学学院', 'stat.nankai.edu.cn', '理工医学类', '数学群'),
('物理科学学院', 'physics.nankai.edu.cn', '理工医学类', '物理光电群'),
('电子信息与光学工程学院', 'ceo.nankai.edu.cn', '理工医学类', '物理光电群'),
('化学学院', 'chem.nankai.edu.cn', '理工医学类', '化材群'),
('材料科学与工程学院', 'mse.nankai.edu.cn', '理工医学类', '化材群'),
('生命科学学院', 'sky.nankai.edu.cn', '理工医学类', '生医环群'),
('环境科学与工程学院', 'env.nankai.edu.cn', '理工医学类', '生医环群'),
('医学院', 'medical.nankai.edu.cn', '理工医学类', '生医环群'),
('药学院', 'pharmacy.nankai.edu.cn', '理工医学类', '生医环群'),
('计算机学院', 'cc.nankai.edu.cn', '理工医学类', '信息科学群'),
('软件学院', 'cs.nankai.edu.cn', '理工医学类', '信息科学群'),
('密码与网络空间安全学院', 'cs.nankai.edu.cn', '理工医学类', '信息科学群'),
('人工智能学院', 'ai.nankai.edu.cn', '理工医学类', '信息科学群');