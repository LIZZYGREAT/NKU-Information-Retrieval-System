from typing import Dict, Set, Any

ADMIN_TABLES: Dict[str, Dict[str, Any]] = {
    "User": {
        "label": "用户账户",
        "pk": "user_id",
        "columns": ["user_id", "username", "email", "role", "created_at"],
        "editable": {"username", "email", "role", "password"},
        "insertable": {"username", "email", "role", "password"},
        "searchable": ["username", "email"],
    },
    "UserProfile": {
        "label": "用户画像",
        "pk": "profile_id",
        "columns": ["profile_id", "user_id", "role", "college_id"],
        "editable": {"user_id", "role", "college_id"},
        "insertable": {"user_id", "role", "college_id"},
        "searchable": [],
    },
    "UserPreference": {
        "label": "用户偏好",
        "pk": "pref_id",
        "columns": ["pref_id", "user_id", "category", "weight", "updated_at"],
        "editable": {"user_id", "category", "weight"},
        "insertable": {"user_id", "category", "weight"},
        "searchable": ["category"],
    },
    "SearchLog": {
        "label": "搜索日志",
        "pk": "log_id",
        "columns": ["log_id", "user_id", "query_text", "search_type", "search_time"],
        "editable": {"query_text", "search_type"},
        "insertable": {},
        "searchable": ["query_text"],
    },
    "WebPageCache": {
        "label": "网页缓存",
        "pk": "page_id",
        "columns": ["page_id", "url", "title", "snapshot_path", "crawl_time"],
        "editable": {"url", "title", "snapshot_path", "tags"},
        "insertable": {"url", "title", "snapshot_path", "tags"},
        "searchable": ["url", "title"],
        "json_columns": {"tags"},
    },
    "CollegeDomain": {
        "label": "学院字典",
        "pk": "college_id",
        "columns": ["college_id", "college_name", "domain_url", "category", "sub_category"],
        "editable": {"college_name", "domain_url", "category", "sub_category"},
        "insertable": {"college_name", "domain_url", "category", "sub_category"},
        "searchable": ["college_name", "domain_url"],
    },
    "PageLinks": {
        "label": "页面链接",
        "pk": "link_id",
        "columns": ["link_id", "source_url", "target_url"],
        "editable": {"source_url", "target_url"},
        "insertable": {"source_url", "target_url"},
        "searchable": ["source_url", "target_url"],
        "max_page_size": 50,
    },
}

USER_ROLES = frozenset({"admin", "user"})
PROFILE_ROLES = frozenset({"本科生", "研究生", "教职工", "访客"})
SEARCH_TYPES = frozenset({"site", "document", "phrase", "wildcard"})
FILTER_OPS = frozenset({
    "eq", "ne", "contains", "starts_with", "ends_with",
    "gt", "gte", "lt", "lte", "is_null", "is_not_null",
})


def get_table(name: str) -> Dict[str, Any]:
    if name not in ADMIN_TABLES:
        raise ValueError(f"不允许访问表: {name}")
    cfg = dict(ADMIN_TABLES[name])
    if "filterable" not in cfg:
        cols = list(cfg["columns"])
        if "tags" in cfg.get("json_columns", {}):
            cols.append("tags")
        cfg["filterable"] = cols
    return cfg
