import json
from typing import Any, Dict, List, Optional

from werkzeug.security import generate_password_hash

from app.admin.registry import (
    ADMIN_TABLES,
    FILTER_OPS,
    PROFILE_ROLES,
    SEARCH_TYPES,
    USER_ROLES,
    get_table,
)
from app.admin.views_registry import ADMIN_VIEWS, get_view
from app.dao.admin_dao import AdminDAO

FILTER_OPS_META = [
    {"op": "eq", "label": "等于"},
    {"op": "ne", "label": "不等于"},
    {"op": "contains", "label": "包含"},
    {"op": "starts_with", "label": "开头是"},
    {"op": "ends_with", "label": "结尾是"},
    {"op": "gt", "label": "大于"},
    {"op": "gte", "label": "大于等于"},
    {"op": "lt", "label": "小于"},
    {"op": "lte", "label": "小于等于"},
    {"op": "is_null", "label": "为空"},
    {"op": "is_not_null", "label": "不为空"},
]


class AdminService:
    def __init__(self, mysql_dao):
        self.admin_dao = AdminDAO(mysql_dao)
        self.mysql_dao = mysql_dao

    def verify_admin(self, admin_user_id: int) -> Dict:
        user = self.admin_dao.get_user_by_id(admin_user_id)
        if not user:
            raise PermissionError("管理员不存在")
        if user.get("role") != "admin":
            raise PermissionError("无管理员权限")
        return user

    def login(self, account: str, password: str) -> Dict:
        account = (account or "").strip()
        user = self.mysql_dao.get_user_by_email(account) if "@" in account else self.mysql_dao.get_user_by_username(account)
        if not user:
            raise PermissionError("账号或密码错误")
        from werkzeug.security import check_password_hash

        if not check_password_hash(user["password_hash"], password):
            raise PermissionError("账号或密码错误")
        if user.get("role") != "admin":
            raise PermissionError("该账号不是管理员")
        return {
            "user_id": user["user_id"],
            "username": user["username"],
            "email": user.get("email"),
            "role": user["role"],
            "is_admin": True,
        }

    def list_tables(self) -> List[Dict]:
        return [
            {"name": k, "label": v["label"], "pk": v["pk"]}
            for k, v in ADMIN_TABLES.items()
        ]

    def _load_filters_raw(self, raw: Any) -> List:
        if not raw:
            return []
        if isinstance(raw, str):
            raw = raw.strip()
            if not raw:
                return []
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raise ValueError("filters 必须是合法 JSON 数组")
        if not isinstance(raw, list):
            raise ValueError("filters 必须是数组")
        if len(raw) > 10:
            raise ValueError("最多 10 条筛选条件")
        return raw

    def parse_filters_cfg(self, cfg: Dict[str, Any], raw: Any) -> List[Dict[str, Any]]:
        raw = self._load_filters_raw(raw)
        filterable = set(cfg.get("filterable", cfg["columns"]))
        out = []
        for i, item in enumerate(raw):
            if not isinstance(item, dict):
                raise ValueError(f"第 {i + 1} 条筛选格式无效")
            field = str(item.get("field", "")).strip()
            op = str(item.get("op", "eq")).strip()
            if field not in filterable:
                raise ValueError(f"不允许筛选字段: {field}")
            if op not in FILTER_OPS:
                raise ValueError(f"不支持的运算符: {op}")
            if op in ("is_null", "is_not_null"):
                out.append({"field": field, "op": op})
            else:
                val = item.get("value")
                if val is None or (isinstance(val, str) and not val.strip()):
                    raise ValueError(f"字段 {field} 需要提供筛选值")
                out.append({"field": field, "op": op, "value": val.strip() if isinstance(val, str) else val})
        return out

    def parse_filters(self, table: str, raw: Any) -> List[Dict[str, Any]]:
        return self.parse_filters_cfg(get_table(table), raw)

    def list_views(self) -> List[Dict]:
        return [
            {
                "name": k,
                "label": v["label"],
                "description": v.get("description", ""),
                "pk": v["pk"],
            }
            for k, v in ADMIN_VIEWS.items()
        ]

    def list_view_data(
        self,
        admin_id: int,
        view_name: str,
        page: int,
        page_size: int,
        keyword: str = "",
        filters: Any = None,
    ) -> Dict:
        self.verify_admin(admin_id)
        cfg = get_view(view_name)
        page_size = min(max(1, page_size), 100)
        page = max(1, page)
        parsed_filters = self.parse_filters_cfg(cfg, filters)
        rows, total = self.admin_dao.list_view_rows(
            view_name, page, page_size, keyword, parsed_filters
        )
        return {
            "view": view_name,
            "label": cfg["label"],
            "description": cfg.get("description", ""),
            "columns": cfg["columns"],
            "filterable": list(cfg.get("filterable", cfg["columns"])),
            "filter_ops": FILTER_OPS_META,
            "pk": cfg["pk"],
            "rows": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "active_filters": parsed_filters,
        }

    def get_analytics_overview(self, admin_id: int) -> Dict:
        self.verify_admin(admin_id)
        return self.admin_dao.analytics_overview()

    def list_data(
        self,
        admin_id: int,
        table: str,
        page: int,
        page_size: int,
        keyword: str = "",
        filters: Any = None,
    ) -> Dict:
        self.verify_admin(admin_id)
        cfg = get_table(table)
        max_ps = cfg.get("max_page_size", 100)
        page_size = min(max(1, page_size), max_ps)
        page = max(1, page)
        parsed_filters = self.parse_filters(table, filters)
        rows, total = self.admin_dao.list_rows(table, page, page_size, keyword, parsed_filters)
        return {
            "table": table,
            "columns": cfg["columns"],
            "filterable": list(cfg.get("filterable", cfg["columns"])),
            "filter_ops": FILTER_OPS_META,
            "editable": list(cfg.get("editable", [])),
            "insertable": list(cfg.get("insertable", {})),
            "pk": cfg["pk"],
            "rows": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "active_filters": parsed_filters,
        }

    def create_row(self, admin_id: int, table: str, data: Dict[str, Any]) -> Dict:
        self.verify_admin(admin_id)
        self._validate_payload(table, data, for_insert=True)
        if table == "User" and data.get("password"):
            data = dict(data)
            data["password_hash"] = generate_password_hash(data.pop("password"))
        new_id = self.admin_dao.insert_row(table, data)
        return {"id": new_id}

    def update_row(self, admin_id: int, table: str, pk_value: Any, data: Dict[str, Any]) -> Dict:
        self.verify_admin(admin_id)
        self._validate_payload(table, data, for_insert=False)
        if table == "User" and data.get("password"):
            data = dict(data)
            data["password_hash"] = generate_password_hash(data.pop("password"))
        if table == "User":
            target = self.admin_dao.get_user_by_id(int(pk_value))
            if target and target.get("role") == "admin" and data.get("role") == "user":
                if self.admin_dao.count_admins() <= 1:
                    raise ValueError("不能移除唯一的管理员账号")
            if int(pk_value) == admin_id and data.get("role") == "user":
                raise ValueError("不能降低自己的管理员权限")
        ok = self.admin_dao.update_row(table, pk_value, data)
        if not ok:
            raise ValueError("更新失败或记录不存在")
        return {"updated": True}

    def delete_row(self, admin_id: int, table: str, pk_value: Any) -> Dict:
        self.verify_admin(admin_id)
        if table == "User":
            uid = int(pk_value)
            target = self.admin_dao.get_user_by_id(uid)
            if not target:
                raise ValueError("用户不存在")
            if target.get("role") == "admin":
                if self.admin_dao.count_admins() <= 1:
                    raise ValueError("不能删除唯一的管理员")
                if uid == admin_id:
                    raise ValueError("不能删除当前登录的管理员账号")
            self.mysql_dao.delete_user_transactionally(uid)
            return {"deleted": True}
        ok = self.admin_dao.delete_row(table, pk_value)
        if not ok:
            raise ValueError("删除失败或记录不存在")
        return {"deleted": True}

    def dashboard_stats(self, admin_id: int) -> Dict:
        self.verify_admin(admin_id)
        return self.admin_dao.stats()

    def _validate_payload(self, table: str, data: Dict[str, Any], for_insert: bool) -> None:
        cfg = get_table(table)
        allowed = set(cfg.get("insertable", {}) if for_insert else cfg.get("editable", {}))
        for key in data:
            if key not in allowed and key != "password":
                raise ValueError(f"不允许修改字段: {key}")
        if table == "User":
            if "role" in data and data["role"] not in USER_ROLES:
                raise ValueError("role 只能是 admin 或 user")
            if for_insert and not data.get("password") and "password_hash" not in data:
                raise ValueError("新建用户必须提供 password")
        if table == "UserProfile" and "role" in data and data["role"] not in PROFILE_ROLES:
            raise ValueError("画像 role 无效")
        if table == "SearchLog" and "search_type" in data and data["search_type"] not in SEARCH_TYPES:
            raise ValueError("search_type 无效")
        if table == "WebPageCache" and "tags" in data and data["tags"]:
            try:
                if isinstance(data["tags"], str):
                    json.loads(data["tags"])
            except json.JSONDecodeError:
                raise ValueError("tags 必须是合法 JSON")
