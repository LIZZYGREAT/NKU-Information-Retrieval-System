from elasticsearch import Elasticsearch
from typing import Dict, Any, List, Optional


class EsDAO:
    TOP_K = 100

    def __init__(self, es_client: Elasticsearch, index_name: str):
        self.es = es_client
        self.index_name = index_name

    def build_base_query(self, query_text: str, search_type: str) -> Dict[str, Any]:
        if search_type == "phrase":
            return {"match_phrase": {"content": query_text}}
        if search_type == "wildcard":
            return {"wildcard": {"content": {"value": query_text}}}
        if search_type == "document":
            return {
                "bool": {
                    "must": [{"multi_match": {"query": query_text, "fields": ["title^2", "content"]}}],
                    "filter": [{"exists": {"field": "attachments"}}],
                }
            }
        return {"multi_match": {"query": query_text, "fields": ["title^2", "content"]}}

    def build_stage1_query(self, base_query: Dict[str, Any], query_text: str) -> Dict[str, Any]:
        q = (query_text or "").strip()
        should: List[Dict[str, Any]] = []
        if len(q) >= 2:
            should.extend([
                {"match_phrase": {"title": {"query": q, "boost": 12}}},
                {"match": {"title": {"query": q, "boost": 6, "operator": "and"}}},
                {"match_phrase": {"content": {"query": q, "boost": 2}}},
            ])
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
            bool_query["minimum_should_match"] = 0

        return {
            "function_score": {
                "query": {"bool": bool_query},
                "functions": [{
                    "field_value_factor": {
                        "field": "pagerank",
                        "factor": 4.0,
                        "modifier": "log1p",
                        "missing": 0.001,
                    },
                    "weight": 0.35,
                }],
                "score_mode": "sum",
                "boost_mode": "sum",
            }
        }

    def fetch_candidates(
        self,
        base_query: Dict[str, Any],
        query_text: str,
        top_k: int = None,
    ) -> Dict[str, Any]:
        k = top_k or self.TOP_K
        body = {
            "query": self.build_stage1_query(base_query, query_text),
            "size": k,
            "_source": ["url", "title", "content", "pagerank", "tags_kw", "tags_detail", "crawl_time"],
            "highlight": {
                "fields": {
                    "content": {
                        "pre_tags": ["<em>"],
                        "post_tags": ["</em>"],
                        "fragment_size": 150,
                    }
                }
            },
        }
        return self.es.search(index=self.index_name, body=body)

    def fetch_frequent_titles(self, size: int = 400) -> List[str]:
        body = {
            "size": 0,
            "aggs": {
                "top_titles": {
                    "terms": {
                        "field": "title.keyword",
                        "size": size,
                        "min_doc_count": 1,
                    }
                }
            },
        }
        try:
            res = self.es.search(index=self.index_name, body=body)
            buckets = res.get("aggregations", {}).get("top_titles", {}).get("buckets", [])
            return [b["key"] for b in buckets if b.get("key")]
        except Exception:
            body["aggs"]["top_titles"]["terms"]["field"] = "title"
            try:
                res = self.es.search(index=self.index_name, body=body)
                buckets = res.get("aggregations", {}).get("top_titles", {}).get("buckets", [])
                return [b["key"] for b in buckets if b.get("key")]
            except Exception:
                return []

    def fetch_all_pageranks(self) -> Dict[str, float]:
        body = {"query": {"match_all": {}}, "size": 5000, "_source": ["pagerank"]}
        res = self.es.search(index=self.index_name, body=body)
        return {hit["_id"]: hit["_source"].get("pagerank", 0.001) for hit in res["hits"]["hits"]}
