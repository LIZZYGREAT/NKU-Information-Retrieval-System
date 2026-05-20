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

    def apply_function_score(self, base_query: Dict[str, Any], weight_factor: float) -> Dict[str, Any]:
        """
        组合文本相关性（BM25）、PageRank静态权威度、时效性高斯衰减以及核心主域特权加权
        """
        functions = [
            # 因子 1: PageRank 静态权威度加权
            {
                "field_value_factor": {
                    "field": "pagerank",
                    "factor": 1.2,
                    "modifier": "log1p",     # 使用 log1p (ln(1+x)) 算分平滑极值带来的长尾效应
                    "missing": 0.001
                }
            },
            # 因子 2: 时效性高斯衰减 (Gauss Decay)
            {
                "gauss": {
                    "crawl_time": {
                        "origin": "now",     # 以当前执行查询的时间为时间原点
                        "scale": "180d",     # 衰减周期设为180天
                        "offset": "15d",     # 15天内发布的一手信息完全不衰减权重
                        "decay": 0.5         # 超过 offset + scale (即195天) 后，时效性权重降为 0.5
                    }
                }
            },
            # 因子 3: 核心主域特权加权 (Domain Boosting)
            {
                "filter": {
                    "bool": {
                        "should": [
                            {"prefix": {"url": "https://www.nankai.edu.cn/"}},   # 南开大学主站门户
                            {"prefix": {"url": "http://jwc.nankai.edu.cn/"}},     # 教务处一手规章
                            {"prefix": {"url": "https://graduate.nankai.edu.cn/"}} # 研究生院官方通知
                        ]
                    }
                },
                "weight": 1.4 
            }
        ]

        return {
            "function_score": {
                "query": base_query,
                "functions": functions,
                "score_mode": "multiply",   # functions 列表内部各项因子之间采用乘法结合
                "boost_mode": "multiply",   # 经过 functions 计算后的综合分与原始 BM25 相关性得分相乘
                "boost": weight_factor      # 承接外层由 MySQL 查出的用户个性化分类偏好系数值
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
                "field": "title.keyword"  # 基于标题的 keyword 属性执行折叠
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
            "size": 5000,  # 满足南开主站及核心学院站点的文档规模
            "_source": ["pagerank"]
        }
        res = self.es.search(index=self.index_name, body=body)
        # 转化为字典结构：{ url: pagerank_score }
        return {hit["_id"]: hit["_source"].get("pagerank", 0.001) for hit in res["hits"]["hits"]}