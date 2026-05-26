from typing import Any, Dict

ADMIN_VIEWS: Dict[str, Dict[str, Any]] = {
    "View_UserSearchActivity": {
        "label": "用户搜索活跃度",
        "description": "用户注册、累计检索次数、最近检索时间与最近一次检索词（数据库视图）",
        "from_sql": "View_UserSearchActivity",
        "pk": "user_id",
        "columns": [
            "user_id", "username", "register_time",
            "total_searches", "last_search_time", "last_query_text",
        ],
        "searchable": ["username", "last_query_text"],
        "order_by": "total_searches DESC",
    },
    "Analytics_SearchByType": {
        "label": "检索类型分布",
        "description": "按站内/短语/通配/文档等类型统计检索次数",
        "from_sql": (
            "(SELECT search_type, COUNT(*) AS search_count, "
            "MAX(search_time) AS last_search_time FROM SearchLog GROUP BY search_type) t"
        ),
        "pk": "search_type",
        "columns": ["search_type", "search_count", "last_search_time"],
        "searchable": ["search_type"],
        "order_by": "search_count DESC",
    },
    "Analytics_TopQueries": {
        "label": "热门检索词",
        "description": "检索词出现次数排行（Top 200）",
        "from_sql": (
            "(SELECT query_text, COUNT(*) AS search_count, "
            "COUNT(DISTINCT user_id) AS user_count, MAX(search_time) AS last_search_time "
            "FROM SearchLog GROUP BY query_text ORDER BY search_count DESC LIMIT 200) t"
        ),
        "pk": "query_text",
        "columns": ["query_text", "search_count", "user_count", "last_search_time"],
        "searchable": ["query_text"],
        "order_by": "search_count DESC",
    },
    "Analytics_UserByRole": {
        "label": "用户画像分布",
        "description": "按本科生/研究生/教职工/访客统计用户数",
        "from_sql": (
            "(SELECT role, COUNT(*) AS user_count FROM UserProfile GROUP BY role) t"
        ),
        "pk": "role",
        "columns": ["role", "user_count"],
        "searchable": ["role"],
        "order_by": "user_count DESC",
    },
    "Analytics_CollegeUsers": {
        "label": "学院用户分布",
        "description": "各学院关联的用户画像数量",
        "from_sql": (
            "(SELECT c.college_name, COUNT(p.profile_id) AS user_count "
            "FROM CollegeDomain c "
            "LEFT JOIN UserProfile p ON c.college_id = p.college_id "
            "GROUP BY c.college_id, c.college_name) t"
        ),
        "pk": "college_name",
        "columns": ["college_name", "user_count"],
        "searchable": ["college_name"],
        "order_by": "user_count DESC",
    },
    "Analytics_RecentSearches": {
        "label": "最近检索记录",
        "description": "最近 500 条搜索日志明细",
        "from_sql": (
            "(SELECT s.log_id, s.user_id, u.username, s.query_text, s.search_type, s.search_time "
            "FROM SearchLog s LEFT JOIN User u ON s.user_id = u.user_id "
            "ORDER BY s.search_time DESC LIMIT 500) t"
        ),
        "pk": "log_id",
        "columns": ["log_id", "user_id", "username", "query_text", "search_type", "search_time"],
        "searchable": ["username", "query_text"],
        "order_by": "search_time DESC",
    },
}


def get_view(name: str) -> Dict[str, Any]:
    if name not in ADMIN_VIEWS:
        raise ValueError(f"不允许访问视图: {name}")
    cfg = dict(ADMIN_VIEWS[name])
    if "filterable" not in cfg:
        cfg["filterable"] = list(cfg["columns"])
    return cfg
