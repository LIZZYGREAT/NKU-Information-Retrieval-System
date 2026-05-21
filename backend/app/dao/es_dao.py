# backend/app/dao/es_dao.py
from elasticsearch import Elasticsearch
from typing import Dict, Any

class EsDAO:
    def __init__(self, es_client: Elasticsearch, index_name: str):
        self.es = es_client
        self.index_name = index_name

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

    def apply_function_score(self, base_query: Dict[str, Any], weight_factor: float, 
                         preferred_domain: str = None, sibling_domains: list = None) -> Dict[str, Any]:
    
        functions = [
            {
                "field_value_factor": {
                    "field": "pagerank",
                    "factor": 1.2,
                    "modifier": "log1p",
                    "missing": 0.001
                }
            },
            {
                "gauss": {
                    "crawl_time": { 
                        "origin": "now", 
                        "scale": "180d", 
                        "offset": "15d", 
                        "decay": 0.5 
                    }
                }
            }
        ]

        # 第一级漏斗（广度关联）：如果用户是理工科，所有理工医学类学院子站的基础分集体拉升
        if sibling_domains:
            should_clauses = [{"prefix": {"url": f"https://{dom}"}} for dom in sibling_domains]
            functions.append({
                "filter": {
                    "bool": { "should": should_clauses }
                },
                "weight": 2.0  
            })

        # 第二级漏斗（深度关联）
        if preferred_domain:
            functions.append({
                "filter": {
                    "prefix": {"url": f"https://{preferred_domain}"}
                },
                "weight": 4.5
            })

        return {
            "function_score": {
                "query": base_query,
                "functions": functions,
                "score_mode": "multiply",   
                "boost_mode": "multiply"    
            }
        }


    def execute_search(self, final_query: Dict[str, Any], page: int, size: int = 10) -> Dict[str, Any]:
        """
        执行检索并启用标题字段折叠去重，同时附加 content 的高亮截断配置
        """
        body = {
            "query": final_query, 
            "from": (page - 1) * size,
            "size": size,
            "collapse": {
                "field": "title.keyword" 
            },
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
    
    def fetch_all_pageranks(self) -> Dict[str, float]:
        """
        从 Elasticsearch 索引中批量获取所有文档的 PageRank 静态权威度数值
        """
        body = {
            "query": {"match_all": {}},
            "size": 5000,  
            "_source": ["pagerank"]
        }
        res = self.es.search(index=self.index_name, body=body)
        return {hit["_id"]: hit["_source"].get("pagerank", 0.001) for hit in res["hits"]["hits"]}