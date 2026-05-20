# backend/app/dependencies.py
import os
from fastapi import Depends
from app.dao.mysql_dao import MySQLDao
from app.dao.es_dao import EsDAO
from app.services.search_service import SearchService
from app.services.user_service import UserService

# 1. 实例化 MySQLDao (注入环境变量配置)
def get_mysql_dao() -> MySQLDao:
    db_config = {
        "host": os.environ.get("MYSQL_HOST", "127.0.0.1"),
        "user": os.environ.get("MYSQL_USER", "root"),
        "password": os.environ.get("MYSQL_PASSWORD", "123456"), # 替换成你本地的 MySQL 密码
        "database": os.environ.get("MYSQL_DATABASE", "nku_search_dev")
    }
    return MySQLDao(db_config=db_config)

# 2. 实例化 ElasticSearchDao
def get_es_dao() -> EsDAO:

    return EsDAO()

# 3. 组装 SearchService
def get_search_service(
    mysql_dao: MySQLDao = Depends(get_mysql_dao),
    es_dao: EsDAO = Depends(get_es_dao)
) -> SearchService:
    return SearchService(es_dao=es_dao, mysql_dao=mysql_dao)

# 4. 组装 UserService
def get_user_service(
    mysql_dao: MySQLDao = Depends(get_mysql_dao)
) -> UserService:
    return UserService(mysql_dao=mysql_dao)