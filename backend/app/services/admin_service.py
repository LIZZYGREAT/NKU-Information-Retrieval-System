"""
管理员服务层，封装管理员后台的业务逻辑

主要功能：
1. 管理员登录验证
2. 权限验证
3. 通用表数据管理（增删改查）
4. 视图数据查询
5. 统计分析数据获取

调用链：
admin_router -> AdminService -> AdminDAO -> MySQLDao -> MySQL
"""

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

# 筛选运算符元数据，用于前端展示
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
    """
    管理员服务类，封装管理员后台的业务逻辑
    
    主要职责：
    1. 管理员身份验证与登录
    2. 权限校验
    3. 通用表CRUD操作（含业务规则校验）
    4. 视图数据查询
    5. 统计分析数据获取
    """

    def __init__(self, mysql_dao):
        """
        初始化管理员服务
        
        :param mysql_dao: MySQLDao实例
        """
        self.admin_dao = AdminDAO(mysql_dao)
        self.mysql_dao = mysql_dao

    def verify_admin(self, admin_user_id: int) -> Dict:
        """
        验证管理员身份
        
        :param admin_user_id: 管理员用户ID
        :return: 管理员用户信息
        :raises PermissionError: 管理员不存在或无权限
        
        用途：在执行管理员操作前验证身份
        """
        user = self.admin_dao.get_user_by_id(admin_user_id)
        if not user:
            raise PermissionError("管理员不存在")
        if user.get("role") != "admin":
            raise PermissionError("无管理员权限")
        return user

    def login(self, account: str, password: str) -> Dict:
        """
        管理员登录验证
        
        :param account: 账号（邮箱或用户名）
        :param password: 密码
        :return: 登录成功的用户信息
        :raises PermissionError: 账号密码错误或非管理员
        
        验证逻辑：
        1. 判断账号类型（邮箱包含@，否则为用户名）
        2. 查询用户记录
        3. 验证密码哈希
        4. 验证管理员角色
        """
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
        """
        获取可管理的表列表
        
        :return: 表配置列表（包含name、label、pk）
        
        用途：前端展示可管理的数据表列表
        """
        return [
            {"name": k, "label": v["label"], "pk": v["pk"]}
            for k, v in ADMIN_TABLES.items()
        ]

    def _load_filters_raw(self, raw: Any) -> List:
        """
        加载原始筛选条件并进行初步校验
        
        :param raw: 原始筛选条件（可能是字符串或列表）
        :return: 解析后的筛选条件列表
        :raises ValueError: 格式无效时抛出异常
        
        校验规则：
        1. 空值返回空列表
        2. 字符串尝试解析为JSON数组
        3. 必须是列表类型
        4. 最多10条筛选条件
        """
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
        """
        根据配置解析筛选条件
        
        :param cfg: 表/视图配置字典
        :param raw: 原始筛选条件
        :return: 解析后的筛选条件列表
        
        校验逻辑：
        1. 调用_load_filters_raw加载原始数据
        2. 校验每个字段是否在可筛选字段列表中
        3. 校验运算符是否支持
        4. 非空值运算符需要提供值
        """
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
        """
        解析表的筛选条件（简化版）
        
        :param table: 表名
        :param raw: 原始筛选条件
        :return: 解析后的筛选条件列表
        
        内部调用parse_filters_cfg，通过get_table获取表配置
        """
        return self.parse_filters_cfg(get_table(table), raw)

    def list_views(self) -> List[Dict]:
        """
        获取可查询的视图列表
        
        :return: 视图配置列表（包含name、label、description、pk）
        
        用途：前端展示可查询的数据视图列表
        """
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
        """
        分页查询视图数据
        
        :param admin_id: 管理员用户ID
        :param view_name: 视图名称
        :param page: 页码（从1开始）
        :param page_size: 每页数量
        :param keyword: 全局搜索关键词
        :param filters: 筛选条件
        :return: 包含数据和元信息的字典
        
        返回数据结构：
        - view: 视图名称
        - label: 视图显示名称
        - description: 视图描述
        - columns: 列名列表
        - filterable: 可筛选字段列表
        - filter_ops: 支持的筛选运算符
        - pk: 主键字段名
        - rows: 数据行列表
        - total: 总记录数
        - page/page_size: 分页参数
        - active_filters: 当前激活的筛选条件
        """
        self.verify_admin(admin_id)
        cfg = get_view(view_name)
        # 限制每页数量在1-100之间
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
        """
        获取分析概览数据
        
        :param admin_id: 管理员用户ID
        :return: 分析概览数据字典
        
        用途：管理员后台仪表盘展示
        """
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
        """
        分页查询表数据
        
        :param admin_id: 管理员用户ID
        :param table: 表名
        :param page: 页码（从1开始）
        :param page_size: 每页数量
        :param keyword: 全局搜索关键词
        :param filters: 筛选条件
        :return: 包含数据和元信息的字典
        
        返回数据结构：
        - table: 表名
        - columns: 列名列表
        - filterable: 可筛选字段列表
        - filter_ops: 支持的筛选运算符
        - editable: 可编辑字段列表
        - insertable: 可插入字段列表
        - pk: 主键字段名
        - rows: 数据行列表
        - total: 总记录数
        - page/page_size: 分页参数
        - active_filters: 当前激活的筛选条件
        """
        self.verify_admin(admin_id)
        cfg = get_table(table)
        # 获取表配置的最大分页大小，默认为100
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
        """
        创建新记录
        
        :param admin_id: 管理员用户ID
        :param table: 表名
        :param data: 要插入的数据
        :return: 包含新记录ID的字典
        :raises ValueError: 数据验证失败时抛出异常
        
        特殊处理：
        - User表：密码会被自动哈希处理
        """
        self.verify_admin(admin_id)
        self._validate_payload(table, data, for_insert=True)
        # 处理密码字段：将明文密码转换为哈希值
        if table == "User" and data.get("password"):
            data = dict(data)
            data["password_hash"] = generate_password_hash(data.pop("password"))
        new_id = self.admin_dao.insert_row(table, data)
        return {"id": new_id}

    def update_row(self, admin_id: int, table: str, pk_value: Any, data: Dict[str, Any]) -> Dict:
        """
        更新记录
        
        :param admin_id: 管理员用户ID
        :param table: 表名
        :param pk_value: 主键值
        :param data: 要更新的数据
        :return: 更新成功的字典
        :raises ValueError: 数据验证失败或业务规则违反时抛出异常
        
        User表特殊业务规则：
        1. 不能将唯一的管理员账号降级为普通用户
        2. 不能降低自己的管理员权限
        """
        self.verify_admin(admin_id)
        self._validate_payload(table, data, for_insert=False)
        # 处理密码字段：将明文密码转换为哈希值
        if table == "User" and data.get("password"):
            data = dict(data)
            data["password_hash"] = generate_password_hash(data.pop("password"))
        # User表的业务规则校验
        if table == "User":
            target = self.admin_dao.get_user_by_id(int(pk_value))
            # 检查是否试图将唯一管理员降级
            if target and target.get("role") == "admin" and data.get("role") == "user":
                if self.admin_dao.count_admins() <= 1:
                    raise ValueError("不能移除唯一的管理员账号")
            # 检查是否试图降低自己的权限
            if int(pk_value) == admin_id and data.get("role") == "user":
                raise ValueError("不能降低自己的管理员权限")
        ok = self.admin_dao.update_row(table, pk_value, data)
        if not ok:
            raise ValueError("更新失败或记录不存在")
        return {"updated": True}

    def delete_row(self, admin_id: int, table: str, pk_value: Any) -> Dict:
        """
        删除记录
        
        :param admin_id: 管理员用户ID
        :param table: 表名
        :param pk_value: 主键值
        :return: 删除成功的字典
        :raises ValueError: 删除失败或业务规则违反时抛出异常
        
        User表特殊业务规则：
        1. 不能删除唯一的管理员账号
        2. 不能删除当前登录的管理员账号
        3. 删除用户时使用事务确保关联数据也被删除
        """
        self.verify_admin(admin_id)
        if table == "User":
            uid = int(pk_value)
            target = self.admin_dao.get_user_by_id(uid)
            if not target:
                raise ValueError("用户不存在")
            if target.get("role") == "admin":
                # 检查是否为唯一管理员
                if self.admin_dao.count_admins() <= 1:
                    raise ValueError("不能删除唯一的管理员")
                # 检查是否为当前登录管理员
                if uid == admin_id:
                    raise ValueError("不能删除当前登录的管理员账号")
            # 使用事务删除用户及其关联数据
            self.mysql_dao.delete_user_transactionally(uid)
            return {"deleted": True}
        ok = self.admin_dao.delete_row(table, pk_value)
        if not ok:
            raise ValueError("删除失败或记录不存在")
        return {"deleted": True}

    def dashboard_stats(self, admin_id: int) -> Dict:
        """
        获取仪表盘统计数据
        
        :param admin_id: 管理员用户ID
        :return: 统计数据字典
        
        用途：管理员后台首页仪表盘展示
        """
        self.verify_admin(admin_id)
        return self.admin_dao.stats()

    def _validate_payload(self, table: str, data: Dict[str, Any], for_insert: bool) -> None:
        """
        验证请求数据的合法性
        
        :param table: 表名
        :param data: 待验证的数据
        :param for_insert: 是否为插入操作
        :raises ValueError: 验证失败时抛出异常
        
        验证规则：
        1. 检查字段是否在允许的列表中（insertable/editable）
        2. User表：校验role字段值，插入时必须提供密码
        3. UserProfile表：校验role字段值
        4. SearchLog表：校验search_type字段值
        5. WebPageCache表：校验tags字段是否为合法JSON
        """
        cfg = get_table(table)
        allowed = set(cfg.get("insertable", {}) if for_insert else cfg.get("editable", {}))
        for key in data:
            if key not in allowed and key != "password":
                raise ValueError(f"不允许修改字段: {key}")
        # User表特殊校验
        if table == "User":
            if "role" in data and data["role"] not in USER_ROLES:
                raise ValueError("role 只能是 admin 或 user")
            if for_insert and not data.get("password") and "password_hash" not in data:
                raise ValueError("新建用户必须提供 password")
        # UserProfile表角色校验
        if table == "UserProfile" and "role" in data and data["role"] not in PROFILE_ROLES:
            raise ValueError("画像 role 无效")
        # SearchLog表搜索类型校验
        if table == "SearchLog" and "search_type" in data and data["search_type"] not in SEARCH_TYPES:
            raise ValueError("search_type 无效")
        # WebPageCache表标签JSON校验
        if table == "WebPageCache" and "tags" in data and data["tags"]:
            try:
                if isinstance(data["tags"], str):
                    json.loads(data["tags"])
            except json.JSONDecodeError:
                raise ValueError("tags 必须是合法 JSON")
