import os
import logging
import threading
from typing import Dict, Any
from urllib.parse import urlparse
from collections import defaultdict


class SearchService:
    def __init__(self, es_dao, mysql_dao):
        self.es_dao = es_dao
        self.mysql_dao = mysql_dao
        self.snapshot_base_dir = "../backend/snapshots"

    def process_search(self, query_text: str, search_type: str, user_id: int = None, page: int = 1) -> Dict[str, Any]:
        if not query_text or not query_text.strip():
            raise ValueError("Query text cannot be empty")

        context = None
        if user_id:
            context = self.mysql_dao.get_personalization_context(user_id, query_text)

        base_query = self.es_dao.build_base_query(query_text, search_type)
        first_stage_query, rescore_query = self.es_dao.build_two_stage_query(base_query, context)
        
        raw_response = self.es_dao.execute_search(first_stage_query, rescore_query, page)
        
        parsed_results = []
        hits = raw_response.get("hits", {}).get("hits", [])
        for hit in hits:
            source = hit.get("_source", {})
            highlight_list = hit.get("highlight", {}).get("content", [])
            highlight_text = highlight_list[0] if highlight_list else source.get("content", "")[:150]
            
            total_score = hit.get("_score", 0.0)
            
            parsed_results.append({
                "url": hit.get("_id"),
                "title": source.get("title", ""),
                "highlight": highlight_text,
                "score": round(total_score, 4) 
            })

        if user_id:
            threading.Thread(
                target=self._write_search_log_safe,
                args=(user_id, query_text, search_type),
                daemon=True,
            ).start()

        return {
            "total_hits": raw_response.get("hits", {}).get("total", {}).get("value", 0),
            "current_page": page,
            "results": parsed_results
        }

    def _write_search_log_safe(self, user_id: int, query_text: str, search_type: str) -> None:
        try:
            self.mysql_dao.insert_search_log_async(user_id, query_text, search_type)
        except Exception as e:
            logging.warning(f"Search log write failed for user {user_id}: {e}")

    def get_snapshot(self, url: str) -> str:
        """
        网页快照独立获取逻辑：解耦检索与 I/O 读取
        """
        # 利用 url 作为主键，向 WebPageCache 请求快照地址
        snapshot_path = self.mysql_dao.get_snapshot_path_by_url(url)
        if not snapshot_path:
            raise FileNotFoundError("Snapshot mapping not found in DB")
        
        # 提取文件名并与基础路径拼接，防止存储路径变更导致的非法路径访问
        file_name = os.path.basename(snapshot_path)
        full_path = os.path.join(self.snapshot_base_dir, file_name)
        
        if not os.path.exists(full_path):
            raise FileNotFoundError("Physical snapshot HTML file is missing")

        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()


    def get_macro_topology(self) -> Dict[str, Any]:
        """
        构建域级宏观拓扑：合并同一二级域名下的 PR 值与跨域边
        """
        raw_edges = self.mysql_dao.get_all_topology_edges()
        try:
            pr_map = self.es_dao.fetch_all_pageranks()
        except Exception:
            pr_map = {}

        domain_pr = defaultdict(float)
        domain_edges = defaultdict(int)
        unique_domains = set()

        # 1. 遍历并合并跨域连线
        for edge in raw_edges:
            src_domain = urlparse(edge['source_url']).netloc
            tgt_domain = urlparse(edge['target_url']).netloc
            
            unique_domains.add(src_domain)
            unique_domains.add(tgt_domain)
            
            if src_domain != tgt_domain:
                # 记录跨域指向权重（如 cc.nankai 指向 jwc.nankai 的总次数）
                domain_edges[(src_domain, tgt_domain)] += 1

        # 2. 累加计算域的整体 PR 权重
        for url, pr in pr_map.items():
            domain = urlparse(url).netloc
            domain_pr[domain] += pr

        nodes = [{"id": dom, "name": dom, "pagerank": domain_pr[dom], "type": "domain"} for dom in unique_domains]
        links = [{"source": src, "target": tgt, "weight": weight} for (src, tgt), weight in domain_edges.items()]

        return {"nodes": nodes, "links": links}

    def get_micro_topology(self, target_domain: str) -> Dict[str, Any]:
        """
        按需下钻微观拓扑：提取指定域名内部的 1 度网页节点与连线
        """
        raw_edges = self.mysql_dao.get_all_topology_edges()
        title_map = self.mysql_dao.get_url_to_title_map()
        try:
            pr_map = self.es_dao.fetch_all_pageranks()
        except Exception:
            pr_map = {}

        unique_urls = set()
        links = []

        for edge in raw_edges:
            src = edge['source_url']
            tgt = edge['target_url']
            src_dom = urlparse(src).netloc
            tgt_dom = urlparse(tgt).netloc

            # 过滤提取域内自闭环拓扑边
            if src_dom == target_domain and tgt_dom == target_domain:
                unique_urls.add(src)
                unique_urls.add(tgt)
                links.append({"source": src, "target": tgt})

        nodes = []
        for url in unique_urls:
            name = title_map.get(url, url.replace("https://", "").replace("http://", "")[:25])
            nodes.append({"id": url, "name": name, "pagerank": pr_map.get(url, 0.001), "type": "page"})

        return {"nodes": nodes, "links": links}