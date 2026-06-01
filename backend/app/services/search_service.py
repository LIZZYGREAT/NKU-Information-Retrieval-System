import os
import math
import logging
import threading
from typing import Dict, Any, List, Tuple, Optional
from urllib.parse import urlparse
from collections import defaultdict

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.page_tagger import normalize_title

# 分页大小配置，每页显示10条搜索结果
PAGE_SIZE = 10

# 多维度排序权重配置（总和为1.0）
# 这些权重经过实验调优，平衡相关性、权威性、个性化和精确匹配
W_RELEVANCE = 0.52  # Elasticsearch相关性得分权重
W_PAGERANK = 0.13   # PageRank权威性权重
W_PERSONAL = 0.18   # 个性化推荐权重
W_EXACT = 0.17      # 精确匹配权重


class SearchService:
    """
    搜索服务核心类，负责执行全文检索、结果重排序和个性化推荐
    
    主要职责：
    1. 构建查询请求并调用ES DAO获取候选结果
    2. 根据用户画像进行个性化重排序
    3. 处理分页、去重和高亮显示
    4. 异步记录搜索日志
    
    调用链：
    search_router -> SearchService -> (es_dao, mysql_dao)
    """

    def __init__(self, es_dao, mysql_dao):
        """
        初始化搜索服务
        
        :param es_dao: Elasticsearch数据访问对象，负责执行ES查询
        :param mysql_dao: MySQL数据访问对象，负责用户画像和日志操作
        """
        self.es_dao = es_dao
        self.mysql_dao = mysql_dao
        self.snapshot_base_dir = "../backend/snapshots"  # 网页快照存储目录

    def process_search(self, query_text: str, search_type: str, user_id: int = None, page: int = 1) -> Dict[str, Any]:
        """
        执行完整的搜索流程
        
        :param query_text: 用户输入的查询文本
        :param search_type: 搜索类型（site/phrase/wildcard/document）
        :param user_id: 用户ID，用于个性化推荐（可选）
        :param page: 页码，用于分页显示
        :return: 包含搜索结果的字典，包含总数、分页信息和结果列表
        
        处理流程：
        1. 参数校验
        2. 获取用户个性化上下文（如已登录）
        3. 构建ES查询并获取候选结果
        4. 个性化重排序（如已登录）
        5. 解析结果、去重、分页
        6. 异步记录搜索日志
        """
        if not query_text or not query_text.strip():
            raise ValueError("Query text cannot be empty")

        query_text = query_text.strip()

        # 获取用户个性化上下文，用于后续重排序
        context = None
        if user_id:
            context = self.mysql_dao.get_personalization_context(user_id, query_text)

        # 构建基础查询并获取候选结果
        base_query = self.es_dao.build_base_query(query_text, search_type)
        raw_response = self.es_dao.fetch_candidates(base_query, query_text)
        hits = raw_response.get("hits", {}).get("hits", [])

        # 个性化重排序：仅在有用户上下文时执行
        if context:
            hits = self._rerank_hits(hits, query_text, context)

        # 解析ES返回结果，提取关键信息
        parsed_results = []
        for hit in hits:
            source = hit.get("_source", {})
            highlight_list = hit.get("highlight", {}).get("content", [])
            # 使用高亮片段或截取内容前150字符作为摘要
            highlight_text = highlight_list[0] if highlight_list else source.get("content", "")[:150]

            # 处理标签数据，支持多种格式
            tags_raw = source.get("tags_kw") or source.get("tags") or []
            if isinstance(tags_raw, str):
                tags_raw = [tags_raw]
            
            parsed_results.append({
                "url": hit.get("_id"),
                "title": source.get("title", ""),
                "highlight": highlight_text,
                "score": round(hit.get("_final_score", hit.get("_score", 0.0)), 4),
                "tags": self._format_tags_for_display(tags_raw, source.get("tags_detail")),
            })

        # 去重处理，避免重复结果
        parsed_results = self._dedupe_results(parsed_results)
        
        # 计算分页参数
        total_display = len(parsed_results)
        total_pages = max(1, (total_display + PAGE_SIZE - 1) // PAGE_SIZE)
        start = (page - 1) * PAGE_SIZE
        page_results = parsed_results[start : start + PAGE_SIZE]

        # 异步记录搜索日志（不阻塞主流程）
        if user_id:
            threading.Thread(
                target=self._write_search_log_safe,
                args=(user_id, query_text, search_type),
                daemon=True,
            ).start()

        return {
            "total_hits": total_display,
            "total_indexed": raw_response.get("hits", {}).get("total", {}).get("value", 0),
            "total_pages": total_pages,
            "page_size": PAGE_SIZE,
            "current_page": page,
            "results": page_results,
        }

    @staticmethod
    def _minmax(values: List[float]) -> List[float]:
        """
        Min-Max归一化：将数值缩放到[0,1]区间
        
        :param values: 待归一化的数值列表
        :return: 归一化后的数值列表
        
        用途：在多维度排序时，将不同量纲的得分统一到相同范围，
        确保各维度权重配置的有效性
        """
        if not values:
            return []
        lo, hi = min(values), max(values)
        if hi <= lo:
            return [1.0 if hi > 0 else 0.0 for _ in values]
        return [(v - lo) / (hi - lo) for v in values]

    @staticmethod
    def _query_affinity(query: str, context: Dict[str, Any]) -> float:
        """
        计算查询与用户上下文的亲和度分数
        
        :param query: 用户查询文本
        :param context: 用户个性化上下文字典
        :return: 亲和度分数（0.2-1.0）
        
        亲和度决定个性化因子的影响程度：
        - 高亲和度：用户查询与用户画像高度相关，个性化权重应加大
        - 低亲和度：用户查询与用户画像无关，应降低个性化影响
        
        判断逻辑：
        1. 查询包含学院名称 → 高亲和度（1.0）
        2. 查询包含学院相关关键词 → 中等亲和度（0.5）
        3. 查询与历史搜索相关 → 较低亲和度（0.42）
        4. 查询属于特定分类 → 基础亲和度（0.35）
        5. 其他情况 → 默认亲和度（0.2）
        """
        q = query.strip()
        college = context.get("college_name") or ""

        # 完全匹配学院名称
        if college:
            short = college.replace("学院", "").replace("科学", "")
            if college in q or (len(short) >= 2 and short in q):
                return 1.0

        # 包含学院相关关键词
        if len(q) <= 6 and any(k in q for k in ("学院", "科学", "专业")):
            return 0.5

        # 与历史搜索记录匹配
        for kw in context.get("recent_keywords", []):
            kw = (kw or "").strip()
            if kw and (kw in q or q in kw):
                return 0.42

        # 查询属于特定分类（非综合类）
        qc = context.get("query_category", "综合")
        if qc != "综合":
            return 0.35

        return 0.2

    @staticmethod
    def _exact_match_score(query: str, title: str, url: str) -> float:
        """
        计算精确匹配得分
        
        :param query: 用户查询文本
        :param title: 网页标题
        :param url: 网页URL
        :return: 精确匹配得分（0-7.5）
        
        精确匹配是提升搜索结果准确性的关键因素，包括：
        - 标题完全匹配（+3.0）
        - 标题包含查询（+0.8~2.0）
        - 标题以查询开头（+1.2）
        - 短标题包含查询（+0.8）
        - 南开大学官方域名特殊加分（+2.5）
        - 首页特殊加分（+1.0）
        """
        q = query.strip()
        t = (title or "").strip()

        if not q or not t:
            return 0.0

        score = 0.0

        # 标题完全匹配
        if t == q:
            score += 3.0
        # 标题包含查询（长度>=3时加分更高）
        elif q in t:
            score += 2.0 if len(q) >= 3 else 0.8

        # 标题以查询开头
        if t.startswith(q) and len(q) >= 2:
            score += 1.2

        # 短标题包含查询
        if len(t) <= len(q) + 12 and q in t:
            score += 0.8

        # 南开大学官方域名特殊处理
        host = urlparse(url).netloc.lower()
        if host in ("www.nankai.edu.cn", "nankai.edu.cn") and q in ("南开大学", "南开"):
            score += 2.5

        # 首页特殊处理
        path = urlparse(url).path.rstrip("/")
        if path in ("", "/") and q in t:
            score += 1.0

        return score

    def _personal_score(self, hit: Dict, context: Dict[str, Any]) -> float:
        """
        计算个性化得分
        
        :param hit: ES搜索结果单条记录
        :param context: 用户个性化上下文字典
        :return: 个性化得分
        
        个性化得分基于：
        1. 标签匹配：根据用户兴趣标签计算匹配度
        2. 域名偏好：用户所属学院域名优先
        3. 兄弟域名：同类别其他学院域名加分
        """
        src = hit.get("_source", {})
        url = src.get("url") or hit.get("_id", "")
        tags = src.get("tags_kw") or []

        if isinstance(tags, str):
            tags = [tags]

        score = 0.0

        # 标签权重匹配
        tw = context.get("tag_weights") or {}
        for tag in tags:
            score += tw.get(tag, 0.0)

        # 域名偏好匹配
        host = urlparse(url).netloc.lower()
        pref = (context.get("preferred_domain") or "").lower()
        if pref and pref in host:
            score += 2.5

        # 兄弟域名匹配（同二级分类）
        for dom in context.get("sibling_domains_t1", []):
            if dom and dom.lower() in host:
                score += 0.6

        return score

    def _rerank_hits(self, hits: List[Dict], query: str, context: Dict[str, Any]) -> List[Dict]:
        """
        多维度融合重排序算法
        
        :param hits: ES原始搜索结果列表
        :param query: 用户查询文本
        :param context: 用户个性化上下文字典
        :return: 重排序后的结果列表
        
        核心算法：
        1. 提取四个维度的原始得分
        2. 分别进行Min-Max归一化
        3. 计算查询亲和度
        4. 加权融合得到最终得分
        5. 按最终得分降序排序
        
        公式：
        final_score = W_RELEVANCE * rel_norm
                    + W_PAGERANK * pr_norm
                    + W_PERSONAL * pers_norm * affinity
                    + W_EXACT * exact_norm + bonus
        
        其中bonus是精确匹配超过阈值时的额外加分
        """
        if not hits:
            return hits

        # 提取四个维度的原始得分
        rel = [float(h.get("_score", 0)) for h in hits]
        pr = [math.log1p(float(h.get("_source", {}).get("pagerank", 0.001))) for h in hits]
        pers = [self._personal_score(h, context) for h in hits]
        exact = [self._exact_match_score(query, h.get("_source", {}).get("title", ""), h.get("_id", "")) for h in hits]

        # 归一化处理
        n_rel = self._minmax(rel)
        n_pr = self._minmax(pr)
        n_pers = self._minmax(pers)
        n_exact = self._minmax(exact)

        # 计算查询亲和度
        affinity = self._query_affinity(query, context)
        max_exact = max(exact) if exact else 0.0

        # 加权融合
        scored: List[Tuple[float, Dict]] = []
        for i, h in enumerate(hits):
            exact_raw = exact[i]
            exact_part = W_EXACT * n_exact[i]

            # 精确匹配超过阈值时增加额外加分
            if exact_raw >= 2.0 and max_exact > 0:
                exact_part += 0.12 * (exact_raw / max_exact)

            # 计算最终得分
            final = (
                W_RELEVANCE * n_rel[i]
                + W_PAGERANK * n_pr[i]
                + W_PERSONAL * n_pers[i] * affinity
                + exact_part
            )

            h["_final_score"] = final
            scored.append((final, h))

        # 按最终得分降序排序
        scored.sort(key=lambda x: x[0], reverse=True)
        return [h for _, h in scored]

    @staticmethod
    def _format_tags_for_display(tags, tags_detail=None) -> List[Dict[str, str]]:
        """
        格式化标签用于前端展示
        
        :param tags: 标签列表（简单格式）
        :param tags_detail: 标签详情（包含置信度的复杂格式）
        :return: 格式化后的标签列表
        
        支持两种标签格式：
        1. tags_detail格式：包含标签值、置信度、命名空间
        2. tags格式：简单的命名空间:值格式
        
        过滤规则：置信度低于0.55的标签不显示
        """
        out = []
        
        # 优先处理tags_detail格式（包含置信度信息）
        if tags_detail and isinstance(tags_detail, list):
            for row in sorted(tags_detail, key=lambda x: -float(x.get("confidence", 0)))[:8]:
                if not isinstance(row, dict):
                    continue
                conf = row.get("confidence")
                label = row.get("value") or row.get("tag", "")
                ns = row.get("namespace", "topic")
                # 过滤低置信度标签
                if conf is not None and conf < 0.55:
                    continue
                suffix = f" {int(conf * 100)}%" if conf is not None else ""
                out.append({"type": ns, "label": f"{label}{suffix}"})
            if out:
                return out[:8]

        # 处理简单格式的标签
        for tag in tags or []:
            if not tag or not isinstance(tag, str):
                continue
            if tag.startswith("college:"):
                out.append({"type": "college", "label": tag[8:]})
            elif tag.startswith("macro:"):
                out.append({"type": "macro", "label": tag[6:]})
            elif tag.startswith("group:"):
                out.append({"type": "group", "label": tag[6:]})
            elif tag.startswith("topic:"):
                out.append({"type": "topic", "label": tag[6:]})
            elif ":" in tag:
                ns, val = tag.split(":", 1)
                out.append({"type": ns, "label": val})
        return out[:8]

    @staticmethod
    def _dedupe_key(title: str, url: str) -> str:
        """
        生成去重键
        
        :param title: 网页标题
        :param url: 网页URL
        :return: 去重键字符串
        
        去重策略：
        - 标题规范化后长度>=4时，使用标题作为去重键
        - 否则使用域名作为去重键
        """
        norm = normalize_title(title)
        if norm and len(norm) >= 4:
            return f"t:{norm}"
        return f"h:{urlparse(url).netloc}"

    def _dedupe_results(self, results: List[Dict]) -> List[Dict]:
        """
        对搜索结果进行去重
        
        :param results: 原始搜索结果列表
        :return: 去重后的结果列表
        
        去重逻辑：
        1. 遍历结果，生成去重键
        2. 使用集合记录已出现的键
        3. 保留首次出现的结果
        """
        seen = set()
        out = []
        for item in results:
            key = self._dedupe_key(item.get("title", ""), item.get("url", ""))
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    def _write_search_log_safe(self, user_id: int, query_text: str, search_type: str) -> None:
        """
        安全写入搜索日志（带异常捕获）
        
        :param user_id: 用户ID
        :param query_text: 查询文本
        :param search_type: 搜索类型
        
        用途：在独立线程中执行，避免阻塞搜索主流程
        失败时仅记录警告日志，不影响搜索结果返回
        """
        try:
            self.mysql_dao.insert_search_log_async(user_id, query_text, search_type)
        except Exception as e:
            logging.warning(f"Search log write failed for user {user_id}: {e}")

    def get_snapshot(self, url: str) -> str:
        """
        获取网页快照内容
        
        :param url: 网页URL
        :return: 快照HTML内容
        :raises FileNotFoundError: 快照不存在时抛出异常
        
        获取流程：
        1. 从数据库查询快照路径
        2. 拼接完整文件路径
        3. 读取并返回HTML内容
        """
        snapshot_path = self.mysql_dao.get_snapshot_path_by_url(url)
        if not snapshot_path:
            raise FileNotFoundError("Snapshot mapping not found in DB")

        file_name = os.path.basename(snapshot_path)
        full_path = os.path.join(self.snapshot_base_dir, file_name)

        if not os.path.exists(full_path):
            raise FileNotFoundError("Physical snapshot HTML file is missing")

        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()

    def get_macro_topology(self) -> Dict[str, Any]:
        """
        获取宏观拓扑图数据（域名级别）
        
        :return: 包含节点和边的拓扑图数据
        
        用途：管理员后台展示网站间链接关系
        节点为域名，边为域名间的链接关系
        """
        raw_edges = self.mysql_dao.get_all_topology_edges()
        
        # 获取PageRank数据（用于节点大小展示）
        try:
            pr_map = self.es_dao.fetch_all_pageranks()
        except Exception:
            pr_map = {}

        # 聚合域名级别数据
        domain_pr = defaultdict(float)
        domain_edges = defaultdict(int)
        unique_domains = set()

        for edge in raw_edges:
            src_domain = urlparse(edge['source_url']).netloc
            tgt_domain = urlparse(edge['target_url']).netloc
            unique_domains.add(src_domain)
            unique_domains.add(tgt_domain)

            # 只统计跨域名链接
            if src_domain != tgt_domain:
                domain_edges[(src_domain, tgt_domain)] += 1

        # 聚合域名的PageRank
        for url, pr in pr_map.items():
            domain = urlparse(url).netloc
            domain_pr[domain] += pr

        # 构建节点和边
        nodes = [{"id": dom, "name": dom, "pagerank": domain_pr[dom], "type": "domain"} for dom in unique_domains]
        links = [{"source": src, "target": tgt, "weight": weight} for (src, tgt), weight in domain_edges.items()]

        return {"nodes": nodes, "links": links}

    def get_micro_topology(self, target_domain: str) -> Dict[str, Any]:
        """
        获取微观拓扑图数据（页面级别）
        
        :param target_domain: 目标域名
        :return: 包含节点和边的拓扑图数据
        
        用途：展示特定域名下页面间的链接关系
        节点为具体页面URL，边为页面间的链接关系
        """
        raw_edges = self.mysql_dao.get_all_topology_edges()
        title_map = self.mysql_dao.get_url_to_title_map()

        try:
            pr_map = self.es_dao.fetch_all_pageranks()
        except Exception:
            pr_map = {}

        unique_urls = set()
        links = []

        # 筛选目标域名内的链接
        for edge in raw_edges:
            src = edge['source_url']
            tgt = edge['target_url']
            src_dom = urlparse(src).netloc
            tgt_dom = urlparse(tgt).netloc

            # 只保留域名内部的链接
            if src_dom == target_domain and tgt_dom == target_domain:
                unique_urls.add(src)
                unique_urls.add(tgt)
                links.append({"source": src, "target": tgt})

        # 构建节点（使用标题作为名称）
        nodes = []
        for url in unique_urls:
            name = title_map.get(url, url.replace("https://", "").replace("http://", "")[:25])
            nodes.append({"id": url, "name": name, "pagerank": pr_map.get(url, 0.001), "type": "page"})

        return {"nodes": nodes, "links": links}