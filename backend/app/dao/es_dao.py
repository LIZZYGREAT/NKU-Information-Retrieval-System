# backend/app/dao/es_dao.py
from elasticsearch import Elasticsearch
from typing import Dict, Any

class EsDAO:
    def __init__(self, es_client: Elasticsearch, index_name: str):
        self.es = es_client
        self.index_name = index_name

    def build_base_query(self, query_text: str, search_type: str) -> Dict[str, Any]:
        if search_type == "phrase":
            return {"match_phrase": {"content": query_text}}
        elif search_type == "wildcard":
            return {"wildcard": {"content": {"value": query_text}}}
        elif search_type == "document":
            return {
                "bool": {
                    "must": [{"multi_match": {"query": query_text, "fields": ["title^2", "content"]}}],
                    "filter": [{"exists": {"field": "attachments"}}]
                }
            }
        else: 
            return {"multi_match": {"query": query_text, "fields": ["title^2", "content"]}}

    def build_two_stage_query(self, base_query: Dict[str, Any], context: Dict[str, Any]) -> tuple:
        # 第一阶段：全局召回 (文本相似度 + 静态 PageRank)
        first_stage_query = {
            "function_score": {
                "query": base_query,
                "functions": [
                    {
                        "field_value_factor": {
                            "field": "pagerank",
                            "factor": 1.2,
                            "modifier": "log1p",
                            "missing": 0.001
                        }
                    }
                ],
                "boost_mode": "multiply"
            }
        }

        if not context:
            return first_stage_query, None

        rescore_functions = []

        # 1. 身份映射 (兼容 HTTP/HTTPS)
        role = context.get("role", "访客")
        if role == "本科生":
            rescore_functions.append({"filter": {"bool": {"should": [{"prefix": {"url": "https://jwc.nankai.edu.cn"}}, {"prefix": {"url": "http://jwc.nankai.edu.cn"}}]}}, "weight": 1.5})
        elif role == "研究生":
            rescore_functions.append({"filter": {"bool": {"should": [{"prefix": {"url": "https://graduate.nankai.edu.cn"}}, {"prefix": {"url": "http://graduate.nankai.edu.cn"}}]}}, "weight": 1.5})

        # 2. 学院归属梯次衰减 (T0 / T1 / T2)
        pref_domain = context.get("preferred_domain")
        if pref_domain:
            rescore_functions.append({
                "filter": {"bool": {"should": [
                    {"prefix": {"url": f"https://{pref_domain}"}},
                    {"prefix": {"url": f"http://{pref_domain}"}}
                ]}}, 
                "weight": 3.0
            })

        siblings_t1 = context.get("sibling_domains_t1", [])
        if siblings_t1:
            t1_should = []
            for dom in siblings_t1:
                t1_should.extend([{"prefix": {"url": f"https://{dom}"}}, {"prefix": {"url": f"http://{dom}"}}])
            rescore_functions.append({"filter": {"bool": {"should": t1_should}}, "weight": 2.0})
            
        siblings_t2 = context.get("sibling_domains_t2", [])
        if siblings_t2:
            t2_should = []
            for dom in siblings_t2:
                t2_should.extend([{"prefix": {"url": f"https://{dom}"}}, {"prefix": {"url": f"http://{dom}"}}])
            rescore_functions.append({"filter": {"bool": {"should": t2_should}}, "weight": 1.2})

        # 3. 动态偏好权重
        weight = context.get("weight", 1.0)
        if weight > 1.0:
            rescore_functions.append({"filter": {"match_all": {}}, "weight": weight})

        # 4. 短期兴趣上下文词频匹配
        recent_keywords = context.get("recent_keywords", [])
        if recent_keywords:
            recent_text = " ".join(recent_keywords)
            rescore_functions.append({"filter": {"match": {"content": recent_text}}, "weight": 1.2})

        # 5. 条件时效性衰减
        query_category = context.get("query_category", "综合")
        decay_scale = "7d" if query_category == "新闻" else "365d"
        rescore_functions.append({
            "gauss": {
                "crawl_time": {
                    "origin": "now",
                    "scale": decay_scale,
                    "offset": "1d",
                    "decay": 0.5
                }
            }
        })

        rescore_query = {
            "window_size": 200,
            "query": {
                "rescore_query": {
                    "function_score": {
                        "query": {"match_all": {}},
                        "functions": rescore_functions,
                        "score_mode": "multiply",
                        "boost_mode": "multiply"
                    }
                },
                "query_weight": 1.0,
                "rescore_query_weight": 1.0
            }
        }

        return first_stage_query, rescore_query

    def execute_search(self, first_stage_query: Dict[str, Any], rescore_query: Dict[str, Any], page: int, size: int = 10) -> Dict[str, Any]:
        body = {
            "query": first_stage_query,
            "from": (page - 1) * size,
            "size": size,
            "collapse": {"field": "title.keyword"},
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

        if rescore_query:
            body["rescore"] = rescore_query

        return self.es.search(index=self.index_name, body=body)
    
    def fetch_all_pageranks(self) -> Dict[str, float]:
        body = {
            "query": {"match_all": {}},
            "size": 5000,  
            "_source": ["pagerank"]
        }
        res = self.es.search(index=self.index_name, body=body)
        return {hit["_id"]: hit["_source"].get("pagerank", 0.001) for hit in res["hits"]["hits"]}