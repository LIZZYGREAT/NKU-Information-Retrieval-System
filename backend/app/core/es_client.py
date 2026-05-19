# backend/app/core/es_client.py
from elasticsearch import Elasticsearch
from app.core.config import settings
from app.dao.es_dao import EsDAO

# 全局单例，内部维护 HTTP 连接池
es_client = Elasticsearch(settings.ES_HOST)

# 依赖注入函数：每次请求时获取 EsDAO 实例
def get_es_dao() -> EsDAO:
    return EsDAO(es_client)