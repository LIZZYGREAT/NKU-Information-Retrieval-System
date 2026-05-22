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



PAGE_SIZE = 10

W_RELEVANCE = 0.52

W_PAGERANK = 0.13

W_PERSONAL = 0.18

W_EXACT = 0.17





class SearchService:

    def __init__(self, es_dao, mysql_dao):

        self.es_dao = es_dao

        self.mysql_dao = mysql_dao

        self.snapshot_base_dir = "../backend/snapshots"



    def process_search(self, query_text: str, search_type: str, user_id: int = None, page: int = 1) -> Dict[str, Any]:

        if not query_text or not query_text.strip():

            raise ValueError("Query text cannot be empty")



        query_text = query_text.strip()

        context = None

        if user_id:

            context = self.mysql_dao.get_personalization_context(user_id, query_text)



        base_query = self.es_dao.build_base_query(query_text, search_type)

        raw_response = self.es_dao.fetch_candidates(base_query, query_text)

        hits = raw_response.get("hits", {}).get("hits", [])



        if context:

            hits = self._rerank_hits(hits, query_text, context)



        parsed_results = []

        for hit in hits:

            source = hit.get("_source", {})

            highlight_list = hit.get("highlight", {}).get("content", [])

            highlight_text = highlight_list[0] if highlight_list else source.get("content", "")[:150]

            tags_raw = source.get("tags_kw") or source.get("tags") or []
            if isinstance(tags_raw, str):
                tags_raw = [tags_raw]
            parsed_results.append({
                "url": hit.get("_id"),
                "title": source.get("title", ""),
                "highlight": highlight_text,
                "score": round(hit.get("_final_score", hit.get("_score", 0.0)), 4),
                "tags": self._format_tags_for_display(tags_raw),
            })



        parsed_results = self._dedupe_results(parsed_results)
        total_display = len(parsed_results)
        total_pages = max(1, (total_display + PAGE_SIZE - 1) // PAGE_SIZE)
        start = (page - 1) * PAGE_SIZE
        page_results = parsed_results[start : start + PAGE_SIZE]



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

        if not values:

            return []

        lo, hi = min(values), max(values)

        if hi <= lo:

            return [1.0 if hi > 0 else 0.0 for _ in values]

        return [(v - lo) / (hi - lo) for v in values]



    @staticmethod

    def _query_affinity(query: str, context: Dict[str, Any]) -> float:

        q = query.strip()

        college = context.get("college_name") or ""

        if college:

            short = college.replace("学院", "").replace("科学", "")

            if college in q or (len(short) >= 2 and short in q):

                return 1.0

        if len(q) <= 6 and any(k in q for k in ("学院", "科学", "专业")):

            return 0.5

        for kw in context.get("recent_keywords", []):

            kw = (kw or "").strip()

            if kw and (kw in q or q in kw):

                return 0.42

        qc = context.get("query_category", "综合")

        if qc != "综合":

            return 0.35

        return 0.2



    @staticmethod

    def _exact_match_score(query: str, title: str, url: str) -> float:

        q = query.strip()

        t = (title or "").strip()

        if not q or not t:

            return 0.0

        score = 0.0

        if t == q:

            score += 3.0

        elif q in t:

            score += 2.0 if len(q) >= 3 else 0.8

        if t.startswith(q) and len(q) >= 2:

            score += 1.2

        if len(t) <= len(q) + 12 and q in t:

            score += 0.8

        host = urlparse(url).netloc.lower()

        if host in ("www.nankai.edu.cn", "nankai.edu.cn") and q in ("南开大学", "南开"):

            score += 2.5

        path = urlparse(url).path.rstrip("/")

        if path in ("", "/") and q in t:

            score += 1.0

        return score



    def _personal_score(self, hit: Dict, context: Dict[str, Any]) -> float:

        src = hit.get("_source", {})

        url = src.get("url") or hit.get("_id", "")

        tags = src.get("tags_kw") or []

        if isinstance(tags, str):

            tags = [tags]

        score = 0.0

        tw = context.get("tag_weights") or {}

        for tag in tags:

            score += tw.get(tag, 0.0)

        host = urlparse(url).netloc.lower()

        pref = (context.get("preferred_domain") or "").lower()

        if pref and pref in host:

            score += 2.5

        for dom in context.get("sibling_domains_t1", []):

            if dom and dom.lower() in host:

                score += 0.6

        return score



    def _rerank_hits(self, hits: List[Dict], query: str, context: Dict[str, Any]) -> List[Dict]:

        if not hits:

            return hits



        rel = [float(h.get("_score", 0)) for h in hits]

        pr = [math.log1p(float(h.get("_source", {}).get("pagerank", 0.001))) for h in hits]

        pers = [self._personal_score(h, context) for h in hits]

        exact = [self._exact_match_score(query, h.get("_source", {}).get("title", ""), h.get("_id", "")) for h in hits]



        n_rel = self._minmax(rel)

        n_pr = self._minmax(pr)

        n_pers = self._minmax(pers)

        n_exact = self._minmax(exact)



        affinity = self._query_affinity(query, context)

        max_exact = max(exact) if exact else 0.0



        scored: List[Tuple[float, Dict]] = []

        for i, h in enumerate(hits):

            exact_raw = exact[i]

            exact_part = W_EXACT * n_exact[i]

            if exact_raw >= 2.0 and max_exact > 0:

                exact_part += 0.12 * (exact_raw / max_exact)



            final = (

                W_RELEVANCE * n_rel[i]

                + W_PAGERANK * n_pr[i]

                + W_PERSONAL * n_pers[i] * affinity

                + exact_part

            )

            h["_final_score"] = final

            scored.append((final, h))



        scored.sort(key=lambda x: x[0], reverse=True)

        return [h for _, h in scored]



    @staticmethod
    def _format_tags_for_display(tags: List) -> List[Dict[str, str]]:
        out = []
        for tag in tags:
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
        return out[:6]

    @staticmethod
    def _dedupe_key(title: str, url: str) -> str:
        norm = normalize_title(title)

        if norm and len(norm) >= 4:

            return f"t:{norm}"

        return f"h:{urlparse(url).netloc}"



    def _dedupe_results(self, results: List[Dict]) -> List[Dict]:

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

        try:

            self.mysql_dao.insert_search_log_async(user_id, query_text, search_type)

        except Exception as e:

            logging.warning(f"Search log write failed for user {user_id}: {e}")



    def get_snapshot(self, url: str) -> str:

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

        raw_edges = self.mysql_dao.get_all_topology_edges()

        try:

            pr_map = self.es_dao.fetch_all_pageranks()

        except Exception:

            pr_map = {}



        domain_pr = defaultdict(float)

        domain_edges = defaultdict(int)

        unique_domains = set()



        for edge in raw_edges:

            src_domain = urlparse(edge['source_url']).netloc

            tgt_domain = urlparse(edge['target_url']).netloc

            unique_domains.add(src_domain)

            unique_domains.add(tgt_domain)

            if src_domain != tgt_domain:

                domain_edges[(src_domain, tgt_domain)] += 1



        for url, pr in pr_map.items():

            domain = urlparse(url).netloc

            domain_pr[domain] += pr



        nodes = [{"id": dom, "name": dom, "pagerank": domain_pr[dom], "type": "domain"} for dom in unique_domains]

        links = [{"source": src, "target": tgt, "weight": weight} for (src, tgt), weight in domain_edges.items()]

        return {"nodes": nodes, "links": links}



    def get_micro_topology(self, target_domain: str) -> Dict[str, Any]:

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

            if src_dom == target_domain and tgt_dom == target_domain:

                unique_urls.add(src)

                unique_urls.add(tgt)

                links.append({"source": src, "target": tgt})



        nodes = []

        for url in unique_urls:

            name = title_map.get(url, url.replace("https://", "").replace("http://", "")[:25])

            nodes.append({"id": url, "name": name, "pagerank": pr_map.get(url, 0.001), "type": "page"})



        return {"nodes": nodes, "links": links}


