"""
管理员数据访问层，封装管理员后台的数据操作

主要功能：
1. 用户管理（查询、计数）
2. 通用表操作（增删改查）
3. 视图查询支持
4. 统计分析数据获取

调用链：
AdminService -> AdminDAO -> MySQLDao -> MySQL
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.admin.registry import ADMIN_TABLES, FILTER_OPS, get_table
from app.admin.views_registry import get_view

# 字段名合法性校验正则：仅允许字母、数字和下划线，且以字母或下划线开头
_COL_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class AdminDAO:
    """
    管理员后台数据访问对象
    
    提供管理员专用的数据操作接口，支持：
    - 用户查询与权限验证
    - 通用表CRUD操作
    - 视图查询
    - 统计数据获取
    """

    def __init__(self, mysql_dao):
        """
        初始化管理员DAO
        
        :param mysql_dao: MySQLDao实例，用于底层数据库操作
        """
        self._dao = mysql_dao

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """
        根据用户ID查询用户信息
        
        :param user_id: 用户ID
        :return: 用户记录字典（包含 user_id, username, email, role, created_at）
        
        用途：管理员身份验证、用户详情查看
        """
        sql = "SELECT user_id, username, email, role, created_at FROM User WHERE user_id = %s"
        with self._dao.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (user_id,))
                return cursor.fetchone()

    def count_admins(self) -> int:
        """
        统计管理员数量
        
        :return: 管理员用户总数
        
        用途：防止删除最后一个管理员时的保护检查
        """
        with self._dao.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS c FROM User WHERE role = 'admin'")
                return int(cursor.fetchone()["c"])

    def _filter_expr(self, field: str, op: str, value: Any, json_cols: set) -> Tuple[str, List[Any]]:
        """
        根据运算符生成SQL筛选表达式
        
        :param field: 字段名
        :param op: 运算符（eq/ne/contains/starts_with/ends_with/gt/gte/lt/lte/is_null/is_not_null）
        :param value: 筛选值
        :param json_cols: JSON类型字段集合（需要CAST转换）
        :return: (SQL表达式, 参数列表)
        
        支持的运算符：
        - eq: 等于
        - ne: 不等于
        - contains: 包含（LIKE %value%）
        - starts_with: 开头是（LIKE value%）
        - ends_with: 结尾是（LIKE %value）
        - gt/gte/lt/lte: 比较运算
        - is_null/is_not_null: 空值检查
        """
        col = f"`{field}`"
        # JSON字段需要转换为字符串进行比较
        if field in json_cols:
            col = f"CAST({col} AS CHAR)"
        
        # 根据运算符生成对应的SQL表达式
        if op == "is_null":
            return f"{col} IS NULL", []
        if op == "is_not_null":
            return f"{col} IS NOT NULL", []
        if op == "eq":
            return f"{col} = %s", [value]
        if op == "ne":
            return f"{col} != %s", [value]
        if op == "contains":
            return f"{col} LIKE %s", [f"%{value}%"]
        if op == "starts_with":
            return f"{col} LIKE %s", [f"{value}%"]
        if op == "ends_with":
            return f"{col} LIKE %s", [f"%{value}"]
        if op == "gt":
            return f"{col} > %s", [value]
        if op == "gte":
            return f"{col} >= %s", [value]
        if op == "lt":
            return f"{col} < %s", [value]
        if op == "lte":
            return f"{col} <= %s", [value]
        raise ValueError(f"不支持的筛选运算符: {op}")

    @staticmethod
    def _from_clause(cfg: Dict[str, Any]) -> str:
        """
        构建FROM子句
        
        :param cfg: 表/视图配置字典
        :return: FROM子句字符串
        
        处理逻辑：
        - 如果from_sql以"("开头，说明是子查询，直接返回
        - 否则添加反引号作为表名
        """
        fs = cfg["from_sql"]
        if fs.startswith("("):
            return fs
        return f"`{fs}`"

    def _build_where_cfg(
        self,
        cfg: Dict[str, Any],
        keyword: str,
        filters: List[Dict[str, Any]],
    ) -> Tuple[str, List[Any]]:
        """
        根据配置构建WHERE子句
        
        :param cfg: 表/视图配置字典
        :param keyword: 全局搜索关键词
        :param filters: 筛选条件列表
        :return: (WHERE子句, 参数列表)
        
        构建逻辑：
        1. 如果有全局搜索关键词，在searchable字段上构建OR条件
        2. 遍历筛选条件列表，调用_filter_expr生成表达式
        3. 所有条件用AND连接
        4. 如果没有任何条件，返回空字符串和空参数列表
        """
        filterable = set(cfg.get("filterable", cfg["columns"]))
        json_cols = set(cfg.get("json_columns", {}))
        clauses: List[str] = []
        params: List[Any] = []

        # 全局关键词搜索：在searchable字段上进行模糊匹配
        if keyword and cfg.get("searchable"):
            parts = [f"`{c}` LIKE %s" for c in cfg["searchable"]]
            like = f"%{keyword}%"
            clauses.append("(" + " OR ".join(parts) + ")")
            params.extend([like] * len(cfg["searchable"]))

        # 处理每个筛选条件
        for item in filters:
            field = item.get("field", "")
            op = item.get("op", "eq")
            # 校验字段合法性
            if field not in filterable or not _COL_RE.match(field):
                raise ValueError(f"不允许筛选字段: {field}")
            if op not in FILTER_OPS:
                raise ValueError(f"不支持的运算符: {op}")
            expr, p = self._filter_expr(field, op, item.get("value"), json_cols)
            clauses.append(expr)
            params.extend(p)

        if not clauses:
            return "", []
        return " WHERE " + " AND ".join(clauses), params

    def _build_where(
        self,
        table: str,
        keyword: str,
        filters: List[Dict[str, Any]],
    ) -> Tuple[str, List[Any]]:
        """
        构建表的WHERE子句（简化版）
        
        :param table: 表名
        :param keyword: 全局搜索关键词
        :param filters: 筛选条件列表
        :return: (WHERE子句, 参数列表)
        
        内部调用_build_where_cfg，通过get_table获取表配置
        """
        return self._build_where_cfg(get_table(table), keyword, filters)

    def list_rows(
        self,
        table: str,
        page: int,
        page_size: int,
        keyword: str = "",
        filters: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[List[Dict], int]:
        """
        分页查询表数据
        
        :param table: 表名
        :param page: 页码（从1开始）
        :param page_size: 每页数量
        :param keyword: 全局搜索关键词
        :param filters: 筛选条件列表
        :return: (数据行列表, 总记录数)
        
        查询逻辑：
        1. 获取表配置，确定查询字段
        2. 如果包含JSON类型的tags字段，需要额外查询
        3. 构建WHERE子句
        4. 先执行COUNT查询获取总数
        5. 执行分页数据查询
        6. 处理tags字段的JSON序列化
        """
        cfg = get_table(table)
        cols = cfg["columns"]
        # JSON类型的tags字段需要特殊处理
        if "tags" in cfg.get("json_columns", {}):
            cols = cols + ["tags"]
        col_sql = ", ".join(f"`{c}`" for c in cols)
        where, params = self._build_where(table, keyword, filters or [])

        # 构建COUNT和数据查询SQL
        count_sql = f"SELECT COUNT(*) AS c FROM `{table}`{where}"
        data_sql = f"SELECT {col_sql} FROM `{table}`{where} ORDER BY `{cfg['pk']}` DESC LIMIT %s OFFSET %s"
        offset = (page - 1) * page_size
        params_data = params + [page_size, offset]

        with self._dao.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(count_sql, params)
                total = int(cursor.fetchone()["c"])
                cursor.execute(data_sql, params_data)
                rows = cursor.fetchall()
        
        # 将JSON类型的tags字段序列化为字符串
        for row in rows:
            if "tags" in row and row["tags"] is not None and not isinstance(row["tags"], str):
                row["tags"] = json.dumps(row["tags"], ensure_ascii=False)
        return rows, total

    def get_row(self, table: str, pk_value: Any) -> Optional[Dict]:
        """
        根据主键查询单条记录
        
        :param table: 表名
        :param pk_value: 主键值
        :return: 记录字典，如果不存在返回None
        
        用途：查看单条记录详情
        """
        cfg = get_table(table)
        cols = list(cfg["columns"])
        if "tags" in cfg.get("json_columns", {}):
            cols.append("tags")
        col_sql = ", ".join(f"`{c}`" for c in cols)
        sql = f"SELECT {col_sql} FROM `{table}` WHERE `{cfg['pk']}` = %s"
        with self._dao.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (pk_value,))
                row = cursor.fetchone()
        # 处理JSON类型的tags字段
        if row and "tags" in row and row["tags"] is not None and not isinstance(row["tags"], str):
            row["tags"] = json.dumps(row["tags"], ensure_ascii=False)
        return row

    def insert_row(self, table: str, data: Dict[str, Any]) -> Any:
        """
        插入新记录
        
        :param table: 表名
        :param data: 字段-值字典
        :return: 新插入记录的主键值
        
        插入逻辑：
        1. 根据表配置过滤允许插入的字段
        2. User表特殊处理：允许password_hash字段
        3. WebPageCache表特殊处理：解析tags字段的JSON字符串
        4. 构建INSERT语句并执行
        """
        cfg = get_table(table)
        allowed = set(cfg.get("insertable", {}))
        # User表允许password_hash字段
        extra = {"password_hash"} if table == "User" else set()
        payload = {k: v for k, v in data.items() if k in allowed or k in extra}
        if not payload:
            raise ValueError("无有效字段可插入")
        # WebPageCache的tags字段需要解析为JSON对象
        if "tags" in payload and table == "WebPageCache":
            payload["tags"] = json.loads(payload["tags"]) if isinstance(payload["tags"], str) else payload["tags"]
        cols = list(payload.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        col_names = ", ".join(f"`{c}`" for c in cols)
        sql = f"INSERT INTO `{table}` ({col_names}) VALUES ({placeholders})"
        with self._dao.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, [payload[c] for c in cols])
                conn.commit()
                return cursor.lastrowid

    def update_row(self, table: str, pk_value: Any, data: Dict[str, Any]) -> bool:
        """
        更新记录
        
        :param table: 表名
        :param pk_value: 主键值
        :param data: 字段-值字典
        :return: 是否更新成功（影响行数>0）
        
        更新逻辑：
        1. 根据表配置过滤允许更新的字段
        2. User表特殊处理：允许password_hash字段
        3. WebPageCache表特殊处理：解析tags字段的JSON字符串
        4. 构建UPDATE语句并执行
        """
        cfg = get_table(table)
        allowed = set(cfg.get("editable", {}))
        extra = {"password_hash"} if table == "User" else set()
        payload = {k: v for k, v in data.items() if k in allowed or k in extra}
        if not payload:
            raise ValueError("无有效字段可更新")
        if "tags" in payload and table == "WebPageCache":
            payload["tags"] = json.loads(payload["tags"]) if isinstance(payload["tags"], str) else payload["tags"]
        sets = ", ".join(f"`{k}` = %s" for k in payload)
        sql = f"UPDATE `{table}` SET {sets} WHERE `{cfg['pk']}` = %s"
        vals = list(payload.values()) + [pk_value]
        with self._dao.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, vals)
                conn.commit()
                return cursor.rowcount > 0

    def delete_row(self, table: str, pk_value: Any) -> bool:
        """
        删除记录
        
        :param table: 表名
        :param pk_value: 主键值
        :return: 是否删除成功（影响行数>0）
        """
        cfg = get_table(table)
        sql = f"DELETE FROM `{table}` WHERE `{cfg['pk']}` = %s"
        with self._dao.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (pk_value,))
                conn.commit()
                return cursor.rowcount > 0

    def stats(self) -> Dict[str, int]:
        """
        获取所有管理表的记录数统计
        
        :return: 表名到记录数的映射字典
        
        用途：管理员后台仪表盘数据展示
        """
        counts = {}
        for name in ADMIN_TABLES:
            with self._dao.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(f"SELECT COUNT(*) AS c FROM `{name}`")
                    counts[name] = int(cursor.fetchone()["c"])
        return counts

    def list_view_rows(
        self,
        view_name: str,
        page: int,
        page_size: int,
        keyword: str = "",
        filters: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[List[Dict], int]:
        """
        分页查询视图数据
        
        :param view_name: 视图名称
        :param page: 页码（从1开始）
        :param page_size: 每页数量
        :param keyword: 全局搜索关键词
        :param filters: 筛选条件列表
        :return: (数据行列表, 总记录数)
        
        与list_rows的区别：
        - 支持视图配置中的from_sql（可能是子查询）
        - 使用视图配置中的order_by
        """
        cfg = get_view(view_name)
        from_clause = self._from_clause(cfg)
        col_sql = ", ".join(f"`{c}`" for c in cfg["columns"])
        where, params = self._build_where_cfg(cfg, keyword, filters or [])
        order = cfg.get("order_by", f"`{cfg['pk']}` DESC")

        count_sql = f"SELECT COUNT(*) AS c FROM {from_clause}{where}"
        data_sql = f"SELECT {col_sql} FROM {from_clause}{where} ORDER BY {order} LIMIT %s OFFSET %s"
        offset = (page - 1) * page_size
        params_data = params + [page_size, offset]

        with self._dao.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(count_sql, params)
                total = int(cursor.fetchone()["c"])
                cursor.execute(data_sql, params_data)
                rows = cursor.fetchall()
        return rows, total

    def analytics_overview(self) -> Dict[str, Any]:
        """
        获取分析概览数据
        
        :return: 包含各项统计指标的字典
        
        返回数据：
        - total_users: 总用户数
        - total_searches: 总搜索次数
        - total_pages: 总网页数
        - searches_7d: 近7天搜索次数
        - active_users_7d: 近7天活跃用户数
        - top_query: 最热门搜索词
        - top_query_count: 最热门搜索词的搜索次数
        """
        queries = {
            "total_users": "SELECT COUNT(*) AS c FROM User",
            "total_searches": "SELECT COUNT(*) AS c FROM SearchLog",
            "total_pages": "SELECT COUNT(*) AS c FROM WebPageCache",
            "searches_7d": (
                "SELECT COUNT(*) AS c FROM SearchLog "
                "WHERE search_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)"
            ),
            "active_users_7d": (
                "SELECT COUNT(DISTINCT user_id) AS c FROM SearchLog "
                "WHERE search_time >= DATE_SUB(NOW(), INTERVAL 7 DAY)"
            ),
        }
        out: Dict[str, Any] = {}
        with self._dao.get_connection() as conn:
            with conn.cursor() as cursor:
                for key, sql in queries.items():
                    cursor.execute(sql)
                    out[key] = int(cursor.fetchone()["c"])
                # 获取最热门的搜索词
                cursor.execute(
                    "SELECT query_text, COUNT(*) AS c FROM SearchLog "
                    "GROUP BY query_text ORDER BY c DESC LIMIT 1"
                )
                top = cursor.fetchone()
                out["top_query"] = top["query_text"] if top else None
                out["top_query_count"] = int(top["c"]) if top else 0
        return out
