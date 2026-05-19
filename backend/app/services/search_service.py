# backend/app/services/search_service.py
import os
from typing import Dict, Any

class SearchService:
    def __init__(self, es_dao, mysql_dao):
        self.es_dao = es_dao
        self.mysql_dao = mysql_dao
        self.snapshot_base_dir = "../backend/snapshots"

    def process_search(self, query_text: str, search_type: str, user_id: int = None, page: int = 1) -> Dict[str, Any]:
        """
        主搜索流转逻辑
        """
        if not query_text or not query_text.strip():
            raise ValueError("Query text cannot be empty")

        # 1. 查询 MySQL 获取个性化权重 (默认系数为 1.0)
        weight = 1.0
        if user_id:
            weight = self.mysql_dao.get_user_preference_weight(user_id, query_text)

        # 2. 构造 DSL 链路
        base_query = self.es_dao.build_base_query(query_text, search_type)
        final_query = self.es_dao.apply_function_score(base_query, weight)
        
        # 3. 访问 Elasticsearch
        raw_response = self.es_dao.execute_search(final_query, page)
        
        # 4. JSON 结果清洗，抛弃内部元数据，仅向上层提供 url, title 与 高亮 content
        parsed_results = []
        hits = raw_response.get("hits", {}).get("hits", [])
        for hit in hits:
            source = hit.get("_source", {})
            # 提取高亮片段，若匹配词仅在标题出现导致正文无高亮，则取正文前150字符兜底
            highlight_list = hit.get("highlight", {}).get("content", [])
            highlight_text = highlight_list[0] if highlight_list else source.get("content", "")[:150]
            
            parsed_results.append({
                "url": hit.get("_id"),
                "title": source.get("title", ""),
                "highlight": highlight_text,
                "score": hit.get("_score")
            })

        # 5. 异步调用 MySQL 写入日志表，不阻塞搜索主流程返回
        if user_id:
            self.mysql_dao.insert_search_log_async(user_id, query_text, search_type)

        return {
            "total_hits": raw_response.get("hits", {}).get("total", {}).get("value", 0),
            "current_page": page,
            "results": parsed_results
        }

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