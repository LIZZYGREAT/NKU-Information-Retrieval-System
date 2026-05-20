from elasticsearch import Elasticsearch
from app.core.config import settings
from app.dao.es_dao import EsDAO

es_client = Elasticsearch(settings.ES_HOST)

def get_es_dao() -> EsDAO:
    return EsDAO(es_client=es_client, index_name=settings.ES_INDEX_NAME)
