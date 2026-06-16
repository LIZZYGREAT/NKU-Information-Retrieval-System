# backend/app/dao/mysql_dao.py
"""
MySQL数据访问层，封装所有与MySQL数据库的交互操作

主要功能模块：
1. 用户认证与管理（注册、登录、注销）
2. 搜索日志记录与查询
3. 用户个性化画像管理
4. 拓扑图数据支撑
5. 学院信息管理

调用链：
Service层 -> MySQLDao -> MySQL数据库
"""

import pymysql
import logging
from typing import List, Dict, Optional, Any
from urllib.parse import urlparse


class MySQLDao:
    """
    MySQL数据访问对象，封装所有MySQL数据库操作
    
    使用连接池模式，每次操作获取独立连接，确保线程安全
    """

    def __init__(self, db_config: Dict):
        """
        初始化MySQL DAO
        
        :param db_config: 数据库连接配置字典，包含 host, user, password, database
        """
        self.config = db_config

    @staticmethod
    def _normalize_domain(domain_url: str) -> str:
        """
        规范化域名格式，去除协议和路径部分
        
        :param domain_url: 完整的URL或域名
        :return: 规范化后的域名（如 www.nankai.edu.cn）
        """
        if not domain_url:
            return ""
        d = domain_url.strip()
        if "://" not in d:
            return d.split("/")[0]
        return urlparse(d).netloc or d

    def get_connection(self):
        """
        获取数据库连接
        
        :return: pymysql连接对象
        
        每次调用返回新连接，使用完毕后由调用方负责关闭
        """
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
        """
        根据用户名查询用户信息
        
        :param username: 用户名
        :return: 用户记录字典（包含 user_id, username, email, password_hash, role）
        
        用途：注册时检查用户名是否已存在
        """
        sql = "SELECT user_id, username, email, password_hash, role FROM User WHERE username = %s"
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (username,))    #默认返回元组，所以需要用(username,)
                return cursor.fetchone()            #会进行转义处理，解决SQL注入


    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """
        根据邮箱查询用户信息
        
        :param email: 邮箱地址
        :return: 用户记录字典（包含 user_id, username, email, password_hash, role）
        
        用途：登录验证时使用
        """
        sql = "SELECT user_id, username, email, password_hash, role FROM User WHERE email = %s"
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (email,))
                return cursor.fetchone()


    def create_user(self, username: str, email: str, password_hash: str) -> int:
        """
        创建新用户
        
        :param username: 用户名
        :param email: 邮箱地址
        :param password_hash: 密码哈希值
        :return: 新创建用户的 user_id
        
        注意：INSERT操作会触发数据库中定义的 AFTER INSERT 触发器，
        自动向 UserPreference 表插入初始偏好记录
        """
        sql = "INSERT INTO User (username, email, password_hash) VALUES (%s, %s, %s)"
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (username, email, password_hash))   #该插入操作只在内存上执行
                conn.commit()             #落盘到磁盘内
                return cursor.lastrowid   #用于获取自增后的uid

    def delete_user_transactionally(self, user_id: int) -> bool:
        """
        事务性删除用户（级联删除相关记录）
        
        :param user_id: 用户ID
        :return: 删除是否成功
        
        事务流程：
        1. 显式开启事务
        2. 删除 UserPreference 表中的用户偏好
        3. 删除 SearchLog 表中的搜索日志
        4. 删除 UserProfile 表中的用户画像
        5. 删除 User 表中的用户记录（主表）
        6. 提交事务
        
        任何步骤失败都会触发回滚，保证数据一致性
        
        注意：虽然数据库外键已配置 ON DELETE CASCADE，
        但此处显式删除以提高代码可读性和健壮性
        """
        conn = self.get_connection()
        try:
            conn.begin()    #此处可以不显示删除UserPreference,Searchlog,UserProfile，设置了级联。
            with conn.cursor() as cursor:
                # 2. 删除用户偏好表
                cursor.execute("DELETE FROM UserPreference WHERE user_id = %s", (user_id,))
                # 3. 删除搜索日志表
                cursor.execute("DELETE FROM SearchLog WHERE user_id = %s", (user_id,))
                # 4. 删除用户画像表
                cursor.execute("DELETE FROM UserProfile WHERE user_id = %s", (user_id,))
                # 5. 删除主表：User
                cursor.execute("DELETE FROM User WHERE user_id = %s", (user_id,))
            
            conn.commit()
            return True
            
        except Exception as e:
            conn.rollback()
            logging.error(f"Transaction failed for user_id {user_id}. Rolled back. Error: {e}")
            raise RuntimeError("Database transaction failed during user deletion")
        finally:
            conn.close()

    # 查询分类关键词映射表，用于推断查询所属类别
    _CATEGORY_KEYWORDS = (
        ('新闻', ('新闻', '校庆', '通知')),
        ('教务', ('教务', '选课', '成绩', '招生', '规章')),
        ('学术', ('科研', '论文', '研究生', '学术')),
    )

    def _infer_category_from_query(self, query_text: str) -> str:
        """
        根据查询文本实现简单的推断所属分类
        
        :param query_text: 查询文本
        :return: 分类名称（新闻/教务/学术/综合）
        
        匹配逻辑：遍历关键词映射表，找到第一个匹配的分类
        """
        text = (query_text or '').strip()
        for category, keywords in self._CATEGORY_KEYWORDS:
            if any(kw in text for kw in keywords):
                return category
        return '综合'

    def get_user_preference_weight(self, user_id: int, query_text: str) -> float:
        """
        获取用户对当前查询的偏好权重
        
        :param user_id: 用户ID
        :param query_text: 查询文本
        :return: 偏好权重值
        
        查找逻辑：
        1. 先根据查询分类查找对应权重
        2. 若未找到，使用"综合"分类的权重作为兜底
        """
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
        """
        清空游标中的所有结果集（用于存储过程调用后清理）
        
        :param cursor: pymysql游标对象
        """
        while True:
            cursor.fetchall()
            if not cursor.nextset():
                break

    def _update_user_preference_fallback(self, cursor, user_id: int) -> None:
        """
        存储过程不可用时的降级方案：手动更新用户偏好
        
        :param cursor: 数据库游标
        :param user_id: 用户ID
        
        逻辑：
        1. 统计用户最近搜索记录的分类分布
        2. 将最活跃的分类权重增加
        """
        sql = """
            SELECT category FROM (
                SELECT
                    CASE
                        WHEN query_text REGEXP '新闻|校庆|通知' THEN '新闻'
                        WHEN query_text REGEXP '教务|选课|成绩|招生|规章' THEN '教务'
                        WHEN query_text REGEXP '科研|论文|研究生|学术' THEN '学术'
                        ELSE '综合'
                    END AS category,
                    COUNT(*) AS cnt,
                    MAX(search_time) AS last_time
                FROM SearchLog
                WHERE user_id = %s
                GROUP BY category
                ORDER BY cnt DESC, last_time DESC
                LIMIT 1
            ) AS stats
        """
        cursor.execute(sql, (user_id,))
        row = cursor.fetchone()
        category = (row["category"] if row else None) or "综合"
        if category != "综合":
            cursor.execute(
                """
                INSERT INTO UserPreference (user_id, category, weight)
                VALUES (%s, %s, 1.05)
                ON DUPLICATE KEY UPDATE weight = weight + 0.1 * (2.0 - weight)
                """,
                (user_id, category),
            )    #不存在即插入，存在即更新

    def _call_update_user_preference(self, cursor, user_id: int) -> None:
        """
        调用存储过程更新用户偏好
        
        :param cursor: 数据库游标
        :param user_id: 用户ID
        
        若存储过程不存在，则调用降级方案
        """
        try:
            cursor.callproc("UpdateUserPreference", (int(user_id),))  #调用数据库过程
            self._drain_cursor(cursor)
        except Exception as e:
            if getattr(e, "args", (None,))[0] == 1305:
                self._update_user_preference_fallback(cursor, user_id)
            else:
                raise

    def refresh_user_preference(self, user_id: int) -> None:
        """
        刷新用户偏好（根据搜索历史）
        
        :param user_id: 用户ID
        
        用途：定期更新用户兴趣偏好，用于个性化推荐
        """
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                self._call_update_user_preference(cursor, user_id)
            conn.commit()

    def insert_search_log_async(self, user_id: int, query_text: str, search_type: str = 'site'):
        """
        插入搜索日志并更新用户偏好
        
        :param user_id: 用户ID
        :param query_text: 查询文本
        :param search_type: 搜索类型（site/phrase/wildcard/document）
        
        流程：
        1. 插入搜索日志记录
        2. 尝试更新用户偏好（失败仅记录警告，不影响日志插入）
        """
        sql = "INSERT INTO SearchLog (user_id, query_text, search_type) VALUES (%s, %s, %s)"
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, (int(user_id), query_text, search_type))
                try:
                    self._call_update_user_preference(cursor, int(user_id))
                except Exception as e:
                    logging.warning(f"UpdateUserPreference failed for user {user_id}: {e}")
            conn.commit()
        finally:
            conn.close()

    def get_popular_search_queries(self, limit: int = 300) -> List[Dict]:
        """
        获取热门搜索词
        
        :param limit: 返回数量限制
        :return: 热门搜索词列表，包含 query_text 和 cnt（搜索次数）
        """
        sql = """
            SELECT query_text, COUNT(*) AS cnt
            FROM SearchLog
            GROUP BY query_text
            ORDER BY cnt DESC
            LIMIT %s
        """     #COUNT(*)进行统计每组的记录数
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (limit,))
                return cursor.fetchall()

    def get_college_names(self) -> List[str]:
        """
        获取所有学院名称
        
        :return: 学院名称列表
        """
        sql = "SELECT college_name FROM CollegeDomain ORDER BY college_id"
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                return [r["college_name"] for r in cursor.fetchall() if r.get("college_name")]

    def get_distinct_titles(self, limit: int = 500) -> List[str]:
        """
        获取去重后的网页标题
        
        :param limit: 返回数量限制
        :return: 网页标题列表
        """
        sql = "SELECT DISTINCT title FROM WebPageCache WHERE title IS NOT NULL AND title != '' LIMIT %s"
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (limit,))
                return [r["title"] for r in cursor.fetchall() if r.get("title")]

    def get_recent_search_logs(self, user_id: int, limit: int = 10) -> List[str]:
        """
        获取用户最近的搜索历史
        
        :param user_id: 用户ID
        :param limit: 返回数量限制
        :return: 搜索历史关键词列表
        
        用途：前端搜索框的联想提示功能
        """
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
        """
        根据URL获取网页快照路径
        
        :param url: 网页URL
        :return: 快照文件路径（相对路径）
        
        用途：搜索结果中展示网页快照
        """
        sql = "SELECT snapshot_path FROM WebPageCache WHERE url = %s"
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (url,))
                result = cursor.fetchone()
                return result['snapshot_path'] if result else None

    # ================= 管理员拓扑图数据支撑 =================

    def get_all_topology_edges(self) -> List[Dict]:
        """
        获取所有页面链接边
        
        :return: 链接边列表，包含 source_url 和 target_url
        
        用途：管理员后台展示网站拓扑图
        """
        sql = "SELECT source_url, target_url FROM PageLinks"
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                return cursor.fetchall()

    def get_url_to_title_map(self) -> Dict[str, str]:
        """
        获取URL到标题的映射
        
        :return: URL为键，标题为值的字典
        
        用途：拓扑图节点标签展示
        """
        sql = "SELECT url, title FROM WebPageCache"
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()
                # 组装为哈希表结构加速业务层读取
                return {row['url']: row['title'] for row in rows}

    # ================= 个性化与静态画像操作 =================

    # 系统支持的兴趣分类
    _INTEREST_CATEGORIES = ("新闻", "教务", "学术", "综合", "教育")

    def save_onboarding_data(self, user_id: int, role: str, college_id: Optional[int], interests: List[str]) -> bool:
        """
        保存用户冷启动数据
        
        :param user_id: 用户ID
        :param role: 用户角色
        :param college_id: 学院ID
        :param interests: 兴趣分类列表
        :return: 保存是否成功
        
        事务流程：
        1. 插入/更新 UserProfile 记录
        2. 为每个支持的分类初始化/更新 UserPreference 记录
        """
        conn = self.get_connection()
        try:
            conn.begin()
            with conn.cursor() as cursor:
                # 插入/更新用户画像   此处的VALUES函数是为了更新新值
                cursor.execute(
                    """
                    INSERT INTO UserProfile (user_id, role, college_id)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE role=VALUES(role), college_id=VALUES(college_id)
                    """,
                    (user_id, role, college_id),
                )
                # 过滤出系统支持的兴趣分类
                selected = set(interests or []) & set(self._INTEREST_CATEGORIES)
                if not selected:
                    selected = {"综合"}
                # 批量插入/更新用户偏好
                sql_pref = """
                    INSERT INTO UserPreference (user_id, category, weight)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE weight = VALUES(weight)
                """
                for cat in self._INTEREST_CATEGORIES:
                    w = 1.25 if cat in selected else 0.95
                    cursor.execute(sql_pref, (user_id, cat, w))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logging.error(f"Onboarding failed for user_id {user_id}. Error: {e}")
            raise RuntimeError(f"Database transaction failed during onboarding: {str(e)}")
        finally:
            conn.close()

    def list_colleges(self) -> List[Dict]:
        """
        获取学院列表（带分类信息）
        
        :return: 学院信息列表
        
        优先从数据库读取，失败时使用静态配置作为降级方案
        """
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parents[3]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from config.page_tagger import colleges_as_dicts

        try:
            sql = """
                SELECT college_id, college_name, category, sub_category
                FROM CollegeDomain ORDER BY category, college_id
            """
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql)
                    rows = cursor.fetchall()
                    if rows:
                        return rows
        except Exception as e:
            logging.warning(f"CollegeDomain query failed, use static list: {e}")
        return colleges_as_dicts()

    def get_personalization_context(self, user_id: int, query_text: str, query_intent: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        获取用户个性化上下文（用于搜索重排序）
        
        :param user_id: 用户ID
        :param query_text: 查询文本
        :return: 个性化上下文字典
        
        上下文包含：
        - weight: 当前查询的偏好权重
        - query_category: 查询分类
        - role: 用户角色
        - college_name: 学院名称
        - preferred_domain: 偏好域名
        - sibling_colleges_t1/t2: 兄弟学院（同二级/一级分类）
        - sibling_domains_t1/t2: 兄弟域名
        - active_interests: 活跃兴趣分类
        - recent_keywords: 最近搜索关键词
        - tag_weights: 标签权重字典
        """
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parents[3]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from config.page_tagger import build_user_tag_weights

        if query_intent:
            category = query_intent.get("category", "综合")
        else:
            from config.page_tagger import infer_query_category
            category = infer_query_category(query_text)
        context: Dict[str, Any] = {
            "weight": 1.0,
            "query_category": category,
            "query_text": query_text,
            "role": "访客",
            "college_name": None,
            "preferred_domain": None,
            "macro_category": None,
            "sub_category": None,
            "sibling_colleges_t1": [],
            "sibling_colleges_t2": [],
            "sibling_domains_t1": [],
            "sibling_domains_t2": [],
            "active_interests": [],
            "recent_keywords": [],
            "tag_weights": {},
            "query_tag_profile": [],
        }

        sql_profile = """
            SELECT p.role, c.college_name, c.domain_url, c.category, c.sub_category
            FROM UserProfile p
            LEFT JOIN CollegeDomain c ON p.college_id = c.college_id
            WHERE p.user_id = %s
        """
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # 获取当前查询分类的权重
                cursor.execute(
                    "SELECT weight FROM UserPreference WHERE user_id = %s AND category = %s",
                    (user_id, category),
                )
                row_w = cursor.fetchone()
                if row_w:
                    context["weight"] = float(row_w["weight"])
                else:
                    # 兜底使用"综合"分类的权重
                    cursor.execute(
                        "SELECT weight FROM UserPreference WHERE user_id = %s AND category = '综合'",
                        (user_id,),
                    )
                    fb = cursor.fetchone()
                    context["weight"] = float(fb["weight"]) if fb else 1.0

                # 获取用户画像信息
                cursor.execute(sql_profile, (user_id,))
                row_p = cursor.fetchone()
                if row_p:
                    context["role"] = row_p["role"]
                    context["college_name"] = row_p["college_name"]
                    context["macro_category"] = row_p["category"]
                    context["sub_category"] = row_p["sub_category"]
                    if row_p["domain_url"]:
                        context["preferred_domain"] = self._normalize_domain(row_p["domain_url"])
                    # 查询兄弟学院（同二级分类）
                    if row_p["college_name"] and row_p["domain_url"]:
                        cursor.execute(
                            """
                            SELECT college_name, domain_url FROM CollegeDomain
                            WHERE sub_category = %s AND domain_url != %s
                            """,
                            (row_p["sub_category"], row_p["domain_url"]),
                        )
                        for r in cursor.fetchall():
                            context["sibling_colleges_t1"].append(r["college_name"])
                            context["sibling_domains_t1"].append(
                                self._normalize_domain(r["domain_url"])
                            )
                        # 查询兄弟学院（同一级分类但不同二级分类）
                        cursor.execute(
                            """
                            SELECT college_name, domain_url FROM CollegeDomain
                            WHERE category = %s AND sub_category != %s
                            """,
                            (row_p["category"], row_p["sub_category"]),
                        )
                        for r in cursor.fetchall():
                            context["sibling_colleges_t2"].append(r["college_name"])
                            context["sibling_domains_t2"].append(
                                self._normalize_domain(r["domain_url"])
                            )

                # 获取活跃兴趣分类（权重>=1.05）
                cursor.execute(
                    "SELECT category FROM UserPreference WHERE user_id = %s AND weight >= %s",
                    (user_id, 1.15),
                )
                context["active_interests"] = [r["category"] for r in cursor.fetchall()]

                # 获取最近搜索关键词
                cursor.execute(
                    """
                    SELECT query_text FROM SearchLog
                    WHERE user_id = %s ORDER BY search_time DESC LIMIT 5
                    """,
                    (user_id,),
                )
                context["recent_keywords"] = [r["query_text"] for r in cursor.fetchall()]

        # 构建标签权重字典
        context["tag_weights"] = build_user_tag_weights(context)
        if query_intent:
            context["query_tag_profile"] = query_intent["tags"]
            context["query_intent"] = query_intent
        else:
            from config.page_tagger import infer_query_tag_profile
            context["query_tag_profile"] = infer_query_tag_profile(query_text)
        return context


    def get_user_profile(self, user_id: int) -> Dict[str, Any]:
        """
        获取用户完整画像
        
        :param user_id: 用户ID
        :return: 用户画像字典
        
        包含：
        - role: 用户角色
        - college_id: 学院ID
        - interests: 兴趣分类列表（权重大于1.0的分类）
        """
        profile = {"role": "访客", "college_id": None, "interests": []}
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # 1. 提取身份与学院
                cursor.execute("SELECT role, college_id FROM UserProfile WHERE user_id = %s", (user_id,))
                row = cursor.fetchone()
                if row:
                    profile["role"] = row["role"]
                    profile["college_id"] = row["college_id"]
                
                # 2. 提取目前所有权重大于 1.0 的分类作为"已选兴趣"
                cursor.execute(
                    "SELECT category, weight FROM UserPreference WHERE user_id = %s AND weight >= %s",
                    (user_id, 1.15),
                )
                rows = cursor.fetchall()
                if rows:
                    profile["interests"] = [r["category"] for r in rows]
                    
        return profile