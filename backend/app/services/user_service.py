# backend/app/services/user_service.py
from werkzeug.security import generate_password_hash, check_password_hash
from typing import Dict, Any, List
import logging

class UserService:
    def __init__(self, mysql_dao):
        self.mysql_dao = mysql_dao

    def register_user(self, username: str, email: str, password_plain: str) -> Dict[str, Any]:
        """
        处理注册逻辑。
        执行单向哈希加盐加密后存储。
        """
        if not username or not password_plain or not email:
            raise ValueError("Missing required registration fields")
            
        existing_user = self.mysql_dao.get_user_by_username(username)
        if existing_user:
            raise ValueError("Username already exists")

        # 使用 pbkdf2:sha256 算法生成带有随机盐值的哈希摘要
        password_hash = generate_password_hash(password_plain)
        
        try:
            user_id = self.mysql_dao.create_user(username, email, password_hash)
            return {"user_id": user_id, "username": username, "status": "registered"}
        except Exception as e:
            logging.error(f"Registration DB error: {e}")
            raise ValueError("Email format invalid or DB constraint triggered")

    def login_user(self, username: str, password_plain: str) -> Dict[str, Any]:
        """
        处理登录验证。
        比对数据库中存储的 password_hash 与前端传入明文的计算结果。
        """
        user_record = self.mysql_dao.get_user_by_username(username)
        if not user_record:
            raise PermissionError("Invalid username or password")

        # 校验哈希匹配
        is_valid = check_password_hash(user_record['password_hash'], password_plain)
        if not is_valid:
            raise PermissionError("Invalid username or password")

        return {
            "user_id": user_record["user_id"],
            "username": user_record["username"],
            "role": user_record["role"]
        }

    def delete_account(self, user_id: int) -> bool:
        """
        触发注销流程，调用包含事务的 DAO 方法。
        """
        return self.mysql_dao.delete_user_transactionally(user_id)

    def get_search_suggestions(self, user_id: int) -> List[str]:
        """
        获取用户的搜索联想词
        """
        if not user_id:
            return []
        return self.mysql_dao.get_recent_search_logs(user_id)