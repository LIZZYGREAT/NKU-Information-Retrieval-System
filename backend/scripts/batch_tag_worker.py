import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse

import pymysql
from elasticsearch import Elasticsearch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from config.env_settings import load_env, settings
from config.llm_page_tagger import llm_available, tag_pages_batch_with_llm
from config.page_tagger import merge_llm_into_rule_tags, needs_llm_tagging, normalize_title

load_env()

PENDING_QUERY = {
    "bool": {
        "should": [
            {"term": {"tag_status": "pending"}},
            {"term": {"tag_status": "rule_only"}},
            {"bool": {"must_not": {"exists": {"field": "tag_status"}}}},
        ],
        "minimum_should_match": 1,
    }
}

_template_cache: Dict[str, Dict] = {}
_template_lock = threading.Lock()


def _template_key(hit: Dict) -> str:
    src = hit.get("_source", {})
    host = urlparse(src.get("url") or hit.get("_id", "")).netloc.lower()
    norm = src.get("title_norm") or normalize_title(src.get("title", ""))
    return f"{host}|{norm}"


def _mysql_update(url: str, tags_detail: List[Dict]):
    try:
        with pymysql.connect(
            host=settings.MYSQL_HOST,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            database=settings.MYSQL_DATABASE,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE WebPageCache SET tags = %s WHERE url = %s",
                    (json.dumps(tags_detail, ensure_ascii=False), url),
                )
            conn.commit()
    except Exception:
        pass


def _apply(es: Elasticsearch, index: str, hit: Dict, merged: Dict):
    url = hit.get("_source", {}).get("url") or hit["_id"]
    es.update(
        index=index,
        id=hit["_id"],
        doc={
            "tags": merged["tags_kw"],
            "tags_kw": merged["tags_kw"],
            "tags_detail": merged["tags_detail"],
            "tag_status": merged["tag_status"],
        },
    )
    _mysql_update(url, merged["tags_detail"])


def process_batch(es: Elasticsearch, index: str, hits: List[Dict]) -> int:
    pending_features: List[Dict] = []
    pending_hits: List[Dict] = []
    done = 0

    for hit in hits:
        src = hit.get("_source", {})
        if not needs_llm_tagging({"tag_status": src.get("tag_status"), "tags_detail": src.get("tags_detail") or []}):
            continue
        tkey = _template_key(hit)
        with _template_lock:
            cached = _template_cache.get(tkey)
        if cached:
            _apply(es, index, hit, cached)
            done += 1
            continue
        pf = src.get("page_features") or {
            "url": src.get("url") or hit["_id"],
            "title": src.get("title", ""),
            "headings": [],
            "keywords": [],
            "snippet": (src.get("content") or "")[:500],
            "rule_hints": src.get("tags_kw") or [],
        }
        pending_features.append(pf)
        pending_hits.append(hit)

    if not pending_hits:
        return done

    try:
        llm_map = tag_pages_batch_with_llm(pending_features)
    except Exception as e:
        print(f"LLM 批次失败: {e}")
        return done

    for idx, hit in enumerate(pending_hits):
        src = hit.get("_source", {})
        merged = merge_llm_into_rule_tags(src.get("tags_detail") or [], llm_map.get(str(idx), []))
        _apply(es, index, hit, merged)
        with _template_lock:
            _template_cache[_template_key(hit)] = merged
        done += 1
    return done


def run(batch_size: int, workers: int, limit: int):
    if not llm_available():
        print("请在 .env.key 中配置 DEEPSEEK_API_KEY")
        sys.exit(1)

    es = Elasticsearch(settings.ES_HOST, request_timeout=120)
    index = settings.ES_INDEX_NAME
    es.indices.put_mapping(
        index=index,
        body={
            "properties": {
                "page_features": {"type": "object", "enabled": False},
                "tag_status": {"type": "keyword"},
            }
        },
    )

    res = es.search(
        index=index,
        query=PENDING_QUERY,
        source=["url", "title", "title_norm", "content", "tags_kw", "tags_detail", "page_features", "tag_status"],
        size=batch_size,
        scroll="10m",
    )
    sid = res.get("_scroll_id")
    updated = 0
    scanned = 0
    pool_futures = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        while True:
            hits = res["hits"]["hits"]
            if not hits:
                break
            if limit and scanned >= limit:
                break
            if limit:
                hits = hits[: max(0, limit - scanned)]
            scanned += len(hits)
            pool_futures.append(pool.submit(process_batch, es, index, hits))
            if limit and scanned >= limit:
                break
            res = es.scroll(scroll_id=sid, scroll="10m")
            sid = res.get("_scroll_id")

        for fut in as_completed(pool_futures):
            n = fut.result()
            updated += n
            print(f"批次完成 +{n}，累计 LLM 更新 {updated}")

    try:
        es.clear_scroll(scroll_id=sid)
    except Exception:
        pass
    print(f"全部完成，共 LLM 更新 {updated} 条")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--batch-size", type=int, default=settings.BATCH_TAG_SIZE)
    p.add_argument("--workers", type=int, default=settings.BATCH_TAG_WORKERS)
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()
    run(args.batch_size, args.workers, args.limit)
