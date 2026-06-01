# backend/app/services/user_service.py
"""
用户服务层，负责处理用户认证、注册、注销和个性化配置相关业务逻辑

调用链：
user_router -> UserService -> MySQLDao
"""

from werkzeug.security import generate_password_hash, check_password_hash
from typing import Dict, Any, List
import logging

# 导入底层 DAO
from app.dao.mysql_dao import MySQLDao


class UserService:
    """
    用户服务类，封装用户相关的业务逻辑
    
    主要功能：
    1. 用户注册与登录验证
    2. 用户注销（事务性删除）
    3. 用户冷启动（角色、学院、兴趣配置）
    4. 用户画像查询
    """

    def __init__(self, mysql_dao):
        """
        初始化用户服务
        
        :param mysql_dao: MySQL数据访问对象
        """
        self.mysql_dao = mysql_dao

    def register_user(self, username: str, email: str, password_plain: str) -> Dict[str, Any]:
        """
        用户注册业务逻辑
        
        :param username: 用户名
        :param email: 邮箱地址
        :param password_plain: 明文密码
        :return: 注册成功的用户信息
        :raises ValueError: 输入参数无效或用户名/邮箱已存在
        
        处理流程：
        1. 参数校验
        2. 检查邮箱是否已注册
        3. 检查用户名是否已占用
        4. 密码哈希处理（使用 Werkzeug 的安全哈希算法）
        5. 调用 DAO 插入用户记录（会触发触发器）
        """
        if not username or not password_plain or not email:
            raise ValueError("Missing required registration fields")
            
        if self.mysql_dao.get_user_by_email(email):
            raise ValueError("该邮箱已被注册")
        if self.mysql_dao.get_user_by_username(username):
            raise ValueError("该用户名已被占用")

        # 使用 PBKDF2 算法对密码进行哈希处理
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
        """
        用户登录验证
        
        :param email: 用户邮箱
        :param password_plain: 明文密码
        :return: 用户信息（包含 user_id, username, email, role）
        :raises PermissionError: 邮箱或密码错误
        
        验证流程：
        1. 根据邮箱查询用户记录
        2. 使用 check_password_hash 验证密码正确性
        3. 返回用户信息供后续 JWT 生成使用
        """
        user_record = self.mysql_dao.get_user_by_email(email)
        if not user_record:
            raise PermissionError("Invalid email or password")

        # 使用 Werkzeug 验证哈希密码
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
        用户注销（事务性删除）
        
        :param user_id: 用户ID
        :return: 删除是否成功
        
        删除流程（通过数据库事务保证原子性）：
        1. 删除 UserPreference 表中的用户偏好记录
        2. 删除 SearchLog 表中的用户搜索日志
        3. 删除 User 表中的用户记录
        
        任何一步失败都会回滚所有操作
        """
        return self.mysql_dao.delete_user_transactionally(user_id)

    def get_search_suggestions(self, user_id: int) -> List[str]:
        """
        获取用户的搜索联想词（最近搜索记录）
        
        :param user_id: 用户ID
        :return: 搜索历史关键词列表
        
        用途：前端搜索框的联想提示功能
        """
        if not user_id:
            return []
        return self.mysql_dao.get_recent_search_logs(user_id)
    
    def process_onboarding(self, user_id: int, role: str, college_id: int = None, interests: list = None) -> bool:
        """
        处理用户冷启动配置
        
        :param user_id: 用户ID
        :param role: 用户角色（本科生/研究生/教职工/访客）
        :param college_id: 学院ID（访客角色时为None）
        :param interests: 用户兴趣分类列表
        :return: 配置是否成功
        
        业务规则：
        1. 角色只能是指定的四种之一，否则默认设为访客
        2. 访客角色不允许设置学院
        3. 兴趣分类进行交集过滤，只保留系统支持的分类
        """
        # 角色校验与修正
        if role not in ["本科生", "研究生", "教职工", "访客"]:
            role = "访客"
            college_id = None
        
        # 访客角色强制无学院归属
        if role == "访客":
            college_id = None
            
        return self.mysql_dao.save_onboarding_data(user_id, role, college_id, interests or [])

    def get_user_profile(self, user_id: int) -> Dict[str, Any]:
        """
        获取用户完整画像
        
        :param user_id: 用户ID
        :return: 用户画像字典，包含角色、学院ID和兴趣列表
        """
        return self.mysql_dao.get_user_profile(user_id)

    def list_colleges(self) -> List[Dict]:
        """
        获取学院列表
        
        :return: 学院信息列表，包含学院ID、名称、分类等
        """
        return self.mysql_dao.list_colleges()