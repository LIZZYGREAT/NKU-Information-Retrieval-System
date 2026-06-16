"""
Elasticsearch数据访问层，封装所有与Elasticsearch的交互操作

主要功能模块：
1. 查询构建与执行
2. 候选结果获取
3. 聚合查询（标题、PageRank）

调用链：
Service层 -> EsDAO -> Elasticsearch
"""

from elasticsearch import Elasticsearch
from typing import Dict, Any, List, Optional


class EsDAO:
    """
    Elasticsearch数据访问对象，封装所有ES操作
    
    使用Elasticsearch客户端进行全文检索、聚合分析等操作
    """

    TOP_K = 100  # 默认候选结果数量

    def __init__(self, es_client: Elasticsearch, index_name: str):
        """
        初始化ES DAO
        
        :param es_client: Elasticsearch客户端实例
        :param index_name: 索引名称
        """
        self.es = es_client
        self.index_name = index_name

    def build_base_query(self, query_text: str, search_type: str) -> Dict[str, Any]:
        """
        根据搜索类型构建基础查询
        
        :param query_text: 查询文本
        :param search_type: 搜索类型（site/phrase/wildcard/document）
        :return: ES查询字典
        
        搜索类型说明：
        - site: 站内全文搜索（默认），使用multi_match匹配标题和内容
        - phrase: 短语搜索，保持查询词的顺序和邻近关系
        - wildcard: 通配符搜索，支持模糊匹配
        - document: 文档搜索，仅返回包含附件的页面
        """
        if search_type == "phrase":
            return {"match_phrase": {"content": query_text}}
        if search_type == "wildcard":
            return {"wildcard": {"content": {"value": query_text}}}
        if search_type == "document":
            return {
                "bool": {
                    "must": [{"multi_match": {"query": query_text, "fields": ["title^2", "content", "attachment_names^1.5"]}}],
                    "filter": [{"exists": {"field": "attachments"}}],
                }
            }
        # 默认：站内全文搜索，标题权重为内容的2倍
        return {"multi_match": {"query": query_text, "fields": ["title^2", "content"]}}

    def build_stage1_query(self, base_query: Dict[str, Any], query_text: str) -> Dict[str, Any]:
        """
        构建第一阶段查询（候选结果获取）
        
        :param base_query: 基础查询（由build_base_query生成）
        :param query_text: 查询文本
        :return: 完整的ES查询体（包含function_score）
        
        查询结构：
        1. bool查询包含must（基础查询）和should（增强匹配）
        2. function_score引入PageRank作为重要性因子
        3. 对"南开大学"等特殊查询进行域名加权
        
        should子句增强：
        - 标题短语匹配（权重12）
        - 标题分词匹配（权重6）
        - 内容短语匹配（权重2）
        - 南开大学官方域名特殊加权（权重8）
        """
        q = (query_text or "").strip()
        should: List[Dict[str, Any]] = []
        
        # 仅当查询长度>=2时添加增强匹配
        if len(q) >= 2:
            should.extend([
                {"match_phrase": {"title": {"query": q, "boost": 12}}},
                {"match": {"title": {"query": q, "boost": 6, "operator": "and"}}},
                {"match_phrase": {"content": {"query": q, "boost": 2}}},
            ])
            # 南开大学相关查询特殊处理
            if q in ("南开大学", "南开"):
                should.append({
                    "bool": {
                        "should": [
                            {"prefix": {"url": "https://www.nankai.edu.cn"}},
                            {"prefix": {"url": "http://www.nankai.edu.cn"}},
                        ],
                        "boost": 8,
                    }
                })

        bool_query: Dict[str, Any] = {"must": [base_query]}
        if should:
            bool_query["should"] = should
            bool_query["minimum_should_match"] = 0  # should子句可选

        # 使用function_score融合PageRank因子
        return {
            "function_score": {
                "query": {"bool": bool_query},
                "functions": [{
                    "field_value_factor": {
                        "field": "pagerank",
                        "factor": 4.0,
                        "modifier": "log1p",  # 使用log(1+x)压缩PageRank值
                        "missing": 0.001,     # 默认值
                    },
                    "weight": 0.35,  # PageRank因子权重
                }],
                "score_mode": "sum",   # 函数得分相加
                "boost_mode": "sum",   # 与查询得分相加
            }
        }

    def fetch_candidates(
        self,
        base_query: Dict[str, Any],
        query_text: str,
        top_k: int = None,
    ) -> Dict[str, Any]:
        """
        获取候选搜索结果
        
        :param base_query: 基础查询
        :param query_text: 查询文本
        :param top_k: 返回数量限制（默认使用TOP_K=100）
        :return: ES搜索响应
        
        查询配置：
        - 返回字段：url, title, content, pagerank, tags_kw, tags_detail, crawl_time
        - 高亮配置：content字段，使用<em>标签，片段长度150
        """
        k = top_k or self.TOP_K
        body = {
            "query": self.build_stage1_query(base_query, query_text),
            "size": k,
            "_source": ["url", "title", "content", "pagerank", "tags_kw", "tags_detail", "crawl_time", "attachments", "attachment_names"],
            "highlight": {
                "fields": {
                    "content": {
                        "pre_tags": ["<em>"],
                        "post_tags": ["</em>"],
                        "fragment_size": 150,  # 高亮片段长度
                    }
                }
            },
        }
        return self.es.search(index=self.index_name, body=body)

    def fetch_frequent_titles(self, size: int = 400) -> List[str]:
        """
        获取高频出现的标题（用于搜索联想词）
        
        :param size: 返回数量限制
        :return: 标题列表
        
        使用terms聚合获取出现次数最多的标题
        兼容两种字段类型：keyword和text
        """
        body = {
            "size": 0,  # 不返回原始文档
            "aggs": {
                "top_titles": {
                    "terms": {
                        "field": "title.keyword",
                        "size": size,
                        "min_doc_count": 1,  # 至少出现1次
                    }
                }
            },
        }
        try:
            res = self.es.search(index=self.index_name, body=body)
            buckets = res.get("aggregations", {}).get("top_titles", {}).get("buckets", [])
            return [b["key"] for b in buckets if b.get("key")]
        except Exception:
            # 降级：如果keyword字段不存在，尝试普通text字段
            body["aggs"]["top_titles"]["terms"]["field"] = "title"
            try:
                res = self.es.search(index=self.index_name, body=body)
                buckets = res.get("aggregations", {}).get("top_titles", {}).get("buckets", [])
                return [b["key"] for b in buckets if b.get("key")]
            except Exception:
                return []

    def fetch_all_pageranks(self) -> Dict[str, float]:
        """
        获取所有文档的PageRank值
        
        :return: URL到PageRank值的映射字典
        
        用途：拓扑图节点大小展示、搜索结果重排序
        """
        body = {"query": {"match_all": {}}, "size": 5000, "_source": ["pagerank"]}
        res = self.es.search(index=self.index_name, body=body)
        return {hit["_id"]: hit["_source"].get("pagerank", 0.001) for hit in res["hits"]["hits"]}