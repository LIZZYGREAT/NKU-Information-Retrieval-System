-- backend/database/scripts/view_query.sql

DROP VIEW IF EXISTS View_UserSearchActivity;

CREATE VIEW View_UserSearchActivity AS
SELECT 
    u.user_id,
    u.username,
    u.created_at AS register_time,
    COUNT(s.log_id) AS total_searches,
    MAX(s.search_time) AS last_search_time,
    -- 使用标量子查询获取该用户最新的一条具体检索词
    (SELECT query_text 
     FROM SearchLog 
     WHERE user_id = u.user_id 
     ORDER BY search_time DESC 
     LIMIT 1) AS last_query_text
FROM 
    User u
LEFT JOIN 
    SearchLog s ON u.user_id = s.user_id
GROUP BY 
    u.user_id, u.username, u.created_at;