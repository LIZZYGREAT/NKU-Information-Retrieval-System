# backend/app/dao/mysql_dao.py
import pymysql
import logging
from typing import List, Dict, Optional

class MySQLDao:
    def __init__(self, db_config: Dict):
        self.config = db_config

    def get_connection(self):
        return pymysql.connect(
            host=self.config.get('host'),
            user=self.config.get('user'),
            password=self.config.get('password'),
            database=self.config.get('database'),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

    # ================= 认证与用户数据操作 =================

    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """根据用户名获取用户信息及密码摘要"""
        sql = "SELECT user_id, username, password_hash, role FROM User WHERE username = %s"
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (username,))
                return cursor.fetchone()

    def create_user(self, username: str, email: str, password_hash: str) -> int:
        """
        插入新用户。
        注意：此处执行 INSERT 时，将触发数据库中定义的 AFTER INSERT 触发器，
        用于自动化校验邮箱格式或向 UserPreference 表插入初始记录。
        """
        sql = "INSERT INTO User (username, email, password_hash) VALUES (%s, %s, %s)"
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (username, email, password_hash))
                conn.commit()
                return cursor.lastrowid

    def delete_user_transactionally(self, user_id: int) -> bool:
        """
        逻辑：显式开启事务，联合删除 UserPreference, SearchLog 以及 User 表记录。
        """
        conn = self.get_connection()
        try:
            # 1. 显式开启事务
            conn.begin()
            
            with conn.cursor() as cursor:
                # 2. 删除外键依赖表 1：UserPreference
                cursor.execute("DELETE FROM UserPreference WHERE user_id = %s", (user_id,))
                
                # 3. 删除外键依赖表 2：SearchLog
                cursor.execute("DELETE FROM SearchLog WHERE user_id = %s", (user_id,))
                
                # 4. 删除主表：User
                cursor.execute("DELETE FROM User WHERE user_id = %s", (user_id,))
            
            # 5. 若上述无异常，提交事务
            conn.commit()
            return True
            
        except Exception as e:
            # 6. 捕获任何SQL执行异常，立即回滚，保证原子性
            conn.rollback()
            logging.error(f"Transaction failed for user_id {user_id}. Rolled back. Error: {e}")
            raise RuntimeError("Database transaction failed during user deletion")
        finally:
            conn.close()

    # ================= 检索与行为日志支撑 =================

    _CATEGORY_KEYWORDS = (
        ('新闻', ('新闻', '校庆', '通知')),
        ('教务', ('教务', '选课', '成绩', '招生', '规章')),
        ('学术', ('科研', '论文', '研究生', '学术')),
    )

    def _infer_category_from_query(self, query_text: str) -> str:
        text = (query_text or '').strip()
        for category, keywords in self._CATEGORY_KEYWORDS:
            if any(kw in text for kw in keywords):
                return category
        return '综合'

    def get_user_preference_weight(self, user_id: int, query_text: str) -> float:
        category = self._infer_category_from_query(query_text)
        sql = "SELECT weight FROM UserPreference WHERE user_id = %s AND category = %s"
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (user_id, category))
                row = cursor.fetchone()
                if row:
                    return float(row['weight'])
                cursor.execute(
                    "SELECT weight FROM UserPreference WHERE user_id = %s AND category = '综合'",
                    (user_id,),
                )
                fallback = cursor.fetchone()
                return float(fallback['weight']) if fallback else 1.0

    def _drain_cursor(self, cursor) -> None:
        while True:
            cursor.fetchall()
            if not cursor.nextset():
                break

    def refresh_user_preference(self, user_id: int) -> None:
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.callproc('UpdateUserPreference', (user_id,))
                self._drain_cursor(cursor)
            conn.commit()

    def insert_search_log_async(self, user_id: int, query_text: str, search_type: str = 'site'):
        sql = "INSERT INTO SearchLog (user_id, query_text, search_type) VALUES (%s, %s, %s)"
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, (int(user_id), query_text, search_type))
                try:
                    cursor.callproc('UpdateUserPreference', (int(user_id),))
                    self._drain_cursor(cursor)
                except Exception as e:
                    logging.warning(f"UpdateUserPreference failed for user {user_id}: {e}")
            conn.commit()
        finally:
            conn.close()

    def get_recent_search_logs(self, user_id: int, limit: int = 10) -> List[str]:
        """获取最近的历史搜索记录，用于前端搜索联想词"""
        sql = """
            SELECT query_text 
            FROM SearchLog 
            WHERE user_id = %s 
            ORDER BY search_time DESC 
            LIMIT %s
        """
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (user_id, limit))
                results = cursor.fetchall()
                # 提取单列结果组装为字符串列表
                return [row['query_text'] for row in results]


    def get_snapshot_path_by_url(self, url: str) -> Optional[str]:
        """根据 URL 从缓存表中读取物理快照路径"""
        sql = "SELECT snapshot_path FROM WebPageCache WHERE url = %s"
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (url,))
                result = cursor.fetchone()
                return result['snapshot_path'] if result else None

    # ================= 管理员拓扑图数据支撑 =================

    def get_all_topology_edges(self) -> List[Dict]:
        """查询 PageLinks 表，获取爬虫抓取到的全量超链接有向边"""
        sql = "SELECT source_url, target_url FROM PageLinks"
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                return cursor.fetchall()

    def get_url_to_title_map(self) -> Dict[str, str]:
        """查询 WebPageCache 表，建立 URL 到网页标题的映射字典，用于可视化节点标签展示"""
        sql = "SELECT url, title FROM WebPageCache"
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()
                # 组装为哈希表结构加速业务层读取
                return {row['url']: row['title'] for row in rows}