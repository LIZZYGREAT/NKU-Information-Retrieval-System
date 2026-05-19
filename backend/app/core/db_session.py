# backend/app/core/db_session.py
from fastapi import Depends
from app.core.config import settings
from app.dao.mysql_dao import MySQLDao
from app.services.search_service import SearchService
from app.services.user_service import UserService
from app.core.es_client import get_es_dao

# 全局数据库配置字典
db_config = {
    "host": settings.MYSQL_HOST,
    "user": settings.MYSQL_USER,
    "password": settings.MYSQL_PASSWORD,
    "database": settings.MYSQL_DATABASE
}

# 全局单例 DAO
mysql_dao_instance = MySQLDao(db_config)

def get_mysql_dao() -> MySQLDao:
    return mysql_dao_instance

# 依赖注入：组装 SearchService
def get_search_service(
    es_dao=Depends(get_es_dao), 
    mysql_dao=Depends(get_mysql_dao)
) -> SearchService:
    return SearchService(es_dao, mysql_dao)

# 依赖注入：组装 UserService
def get_user_service(
    mysql_dao=Depends(get_mysql_dao)
) -> UserService:
    return UserService(mysql_dao)