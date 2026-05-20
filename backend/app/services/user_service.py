# backend/app/services/user_service.py
from werkzeug.security import generate_password_hash, check_password_hash
from typing import Dict, Any, List
import logging
from fastapi import Depends

# 导入底层 DAO
from app.dao.mysql_dao import MySQLDao

class UserService:
    def __init__(self, mysql_dao):
        self.mysql_dao = mysql_dao

    def register_user(self, username: str, email: str, password_plain: str) -> Dict[str, Any]:
        if not username or not password_plain or not email:
            raise ValueError("Missing required registration fields")
            
        if self.mysql_dao.get_user_by_email(email):
            raise ValueError("该邮箱已被注册")
        if self.mysql_dao.get_user_by_username(username):
            raise ValueError("该用户名已被占用")

        password_hash = generate_password_hash(password_plain)
        
        try:
            user_id = self.mysql_dao.create_user(username, email, password_hash)
            return {"user_id": user_id, "username": username, "email": email, "status": "registered"}
        except Exception as e:
            logging.error(f"Registration DB error: {e}")
            err = str(e).lower()
            if 'email' in err or 'duplicate' in err and 'email' in err:
                raise ValueError("该邮箱已被注册")
            if 'username' in err:
                raise ValueError("该用户名已被占用")
            raise ValueError("注册失败，请检查填写信息")

    def login_user(self, email: str, password_plain: str) -> Dict[str, Any]:
        """处理登录验证，验证目标从 username 切换为 email"""
        user_record = self.mysql_dao.get_user_by_email(email)
        if not user_record:
            raise PermissionError("Invalid email or password")

        is_valid = check_password_hash(user_record['password_hash'], password_plain)
        if not is_valid:
            raise PermissionError("Invalid email or password")

        return {
            "user_id": user_record["user_id"],
            "username": user_record["username"],
            "email": user_record["email"],
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
    
    def process_onboarding(self, user_id: int, role: str, college_id: int = None, interests: list = None) -> bool:
        """处理冷启动业务逻辑校验与入库"""
        if role not in ["本科生", "研究生", "教职工", "访客"]:
            role = "访客"
            college_id = None
        
        # 强制访客无学院归属
        if role == "访客":
            college_id = None
            
        return self.mysql_dao.save_onboarding_data(user_id, role, college_id, interests or [])


    def get_user_profile(self, user_id: int) -> Dict[str, Any]:
        return self.mysql_dao.get_user_profile(user_id)