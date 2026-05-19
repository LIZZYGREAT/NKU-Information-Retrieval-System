# backend/app/dao/es_dao.py
from elasticsearch import Elasticsearch
from typing import Dict, Any

class EsDAO:
    def __init__(self, es_client: Elasticsearch):
        self.es = es_client
        self.index_name = "nku_web_index"

    def build_base_query(self, query_text: str, search_type: str) -> Dict[str, Any]:
        """
        根据 search_type 映射底层 Elasticsearch 检索机制
        """
        if search_type == "phrase":
            # 短语查询：分词词项必须在原文中保持严格顺序
            return {"match_phrase": {"content": query_text}}
        
        elif search_type == "wildcard":
            # 通配查询：处理正则匹配逻辑
            return {"wildcard": {"content": {"value": query_text}}}
        
        elif search_type == "document":
            # 文档查询：全文检索的同时，必须满足 attachments 字段非空
            return {
                "bool": {
                    "must": [{"multi_match": {"query": query_text, "fields": ["title^2", "content"]}}],
                    "filter": [{"exists": {"field": "attachments"}}]
                }
            }
        
        else: 
            # 站内查询 (site)：默认的基于 IK 分词的全文检索，标题权重翻倍
            return {"multi_match": {"query": query_text, "fields": ["title^2", "content"]}}

    def apply_function_score(self, base_query: Dict[str, Any], weight_factor: float) -> Dict[str, Any]:
        """
        注入个性化权重算分逻辑
        """
        if weight_factor <= 1.0:
            return base_query
            
        return {
            "function_score": {
                "query": base_query,
                "boost": weight_factor,
                "boost_mode": "multiply" # 将权重与原始 _score 直接相乘
            }
        }

    def execute_search(self, final_query: Dict[str, Any], page: int, size: int = 10) -> Dict[str, Any]:
        """
        执行检索并强制附加 content 的高亮截断配置
        """
        body = {
            "query": final_query,
            "from": (page - 1) * size,
            "size": size,
            "highlight": {
                "fields": {
                    "content": {
                        "pre_tags": ["<em>"],
                        "post_tags": ["</em>"],
                        "fragment_size": 150
                    }
                }
            }
        }
        return self.es.search(index=self.index_name, body=body)