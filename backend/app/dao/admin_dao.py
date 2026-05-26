import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.admin.registry import ADMIN_TABLES, FILTER_OPS, get_table
from app.admin.views_registry import get_view

_COL_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class AdminDAO:
    def __init__(self, mysql_dao):
        self._dao = mysql_dao

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        sql = "SELECT user_id, username, email, role, created_at FROM User WHERE user_id = %s"
        with self._dao.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (user_id,))
                return cursor.fetchone()

    def count_admins(self) -> int:
        with self._dao.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS c FROM User WHERE role = 'admin'")
                return int(cursor.fetchone()["c"])

    def _filter_expr(self, field: str, op: str, value: Any, json_cols: set) -> Tuple[str, List[Any]]:
        col = f"`{field}`"
        if field in json_cols:
            col = f"CAST({col} AS CHAR)"
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
        filterable = set(cfg.get("filterable", cfg["columns"]))
        json_cols = set(cfg.get("json_columns", {}))
        clauses: List[str] = []
        params: List[Any] = []

        if keyword and cfg.get("searchable"):
            parts = [f"`{c}` LIKE %s" for c in cfg["searchable"]]
            like = f"%{keyword}%"
            clauses.append("(" + " OR ".join(parts) + ")")
            params.extend([like] * len(cfg["searchable"]))

        for item in filters:
            field = item.get("field", "")
            op = item.get("op", "eq")
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
        return self._build_where_cfg(get_table(table), keyword, filters)

    def list_rows(
        self,
        table: str,
        page: int,
        page_size: int,
        keyword: str = "",
        filters: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[List[Dict], int]:
        cfg = get_table(table)
        cols = cfg["columns"]
        if "tags" in cfg.get("json_columns", {}):
            cols = cols + ["tags"]
        col_sql = ", ".join(f"`{c}`" for c in cols)
        where, params = self._build_where(table, keyword, filters or [])

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
        for row in rows:
            if "tags" in row and row["tags"] is not None and not isinstance(row["tags"], str):
                row["tags"] = json.dumps(row["tags"], ensure_ascii=False)
        return rows, total

    def get_row(self, table: str, pk_value: Any) -> Optional[Dict]:
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
        if row and "tags" in row and row["tags"] is not None and not isinstance(row["tags"], str):
            row["tags"] = json.dumps(row["tags"], ensure_ascii=False)
        return row

    def insert_row(self, table: str, data: Dict[str, Any]) -> Any:
        cfg = get_table(table)
        allowed = set(cfg.get("insertable", {}))
        extra = {"password_hash"} if table == "User" else set()
        payload = {k: v for k, v in data.items() if k in allowed or k in extra}
        if not payload:
            raise ValueError("无有效字段可插入")
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
        cfg = get_table(table)
        sql = f"DELETE FROM `{table}` WHERE `{cfg['pk']}` = %s"
        with self._dao.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (pk_value,))
                conn.commit()
                return cursor.rowcount > 0

    def stats(self) -> Dict[str, int]:
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
                cursor.execute(
                    "SELECT query_text, COUNT(*) AS c FROM SearchLog "
                    "GROUP BY query_text ORDER BY c DESC LIMIT 1"
                )
                top = cursor.fetchone()
                out["top_query"] = top["query_text"] if top else None
                out["top_query_count"] = int(top["c"]) if top else 0
        return out
