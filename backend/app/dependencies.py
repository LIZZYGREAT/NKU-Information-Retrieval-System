# backend/app/dependencies.py
from fastapi import Depends
from elasticsearch import Elasticsearch
from app.core.config import settings 
from app.dao.mysql_dao import MySQLDao
from app.dao.es_dao import EsDAO
from app.services.search_service import SearchService
from app.services.user_service import UserService

# 1. 实例化 ES 全局客户端 
es_client_instance = Elasticsearch(settings.ES_HOST)

# 2. 实例化 MySQLDao
def get_mysql_dao() -> MySQLDao:
    db_config = {
        "host": settings.MYSQL_HOST,
        "user": settings.MYSQL_USER,
        "password": settings.MYSQL_PASSWORD,
        "database": settings.MYSQL_DATABASE
    }
    return MySQLDao(db_config=db_config)

# 3. 实例化 ElasticSearchDao
def get_es_dao() -> EsDAO:
    return EsDAO(es_client=es_client_instance, index_name=settings.ES_INDEX_NAME)

# 4. 组装 SearchService
def get_search_service(
    mysql_dao: MySQLDao = Depends(get_mysql_dao),
    es_dao: EsDAO = Depends(get_es_dao)
) -> SearchService:
    return SearchService(es_dao=es_dao, mysql_dao=mysql_dao)

# 5. 组装 UserService
def get_user_service(
    mysql_dao: MySQLDao = Depends(get_mysql_dao)
) -> UserService:
    return UserService(mysql_dao=mysql_dao)