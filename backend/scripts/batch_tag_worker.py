import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import pymysql
from elasticsearch import Elasticsearch, BadRequestError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from config.env_settings import load_env, settings
from config.llm_page_tagger import llm_available, tag_pages_batch_with_llm
from config.page_tagger import merge_llm_into_rule_tags, needs_llm_tagging, normalize_title

load_env()

DEFAULT_PROGRESS_FILE = ROOT / "backend" / "data" / "batch_tag_progress.json"

PENDING_QUERY = {
    "bool": {
        "should": [
            {"match": {"tag_status": "pending"}},
            {"match": {"tag_status": "rule_only"}},
            {"bool": {"must_not": {"exists": {"field": "tag_status"}}}},
        ],
        "minimum_should_match": 1,
    }
}

_template_cache: Dict[str, Dict] = {}
_template_lock = threading.Lock()
_stats = {"llm_fail": 0, "skipped": 0, "cached": 0, "tagged": 0, "scanned": 0}
_stats_lock = threading.Lock()
_progress: Dict[str, Any] = {}
_progress_path: Path = DEFAULT_PROGRESS_FILE
_progress_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_progress(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_progress():
    with _progress_lock:
        _progress["updated_at"] = _now()
        _progress["tagged_total"] = _stats["tagged"]
        _progress["cached_total"] = _stats["cached"]
        _progress["failed_batches"] = _stats["llm_fail"]
        _progress["scanned_total"] = _stats["scanned"]
        _progress_path.parent.mkdir(parents=True, exist_ok=True)
        _progress_path.write_text(
            json.dumps(_progress, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _init_progress(path: Path, index: str, initial_pending: int, reset: bool):
    global _progress, _progress_path
    _progress_path = path
    if reset or not path.is_file():
        _progress = {
            "index": index,
            "started_at": _now(),
            "updated_at": _now(),
            "initial_pending": initial_pending,
            "tagged_total": 0,
            "cached_total": 0,
            "failed_batches": 0,
            "scanned_total": 0,
            "last_batch_urls": [],
            "note": "中断后重新运行即可续标；已完成文档 tag_status=llm_done 不会重复处理",
        }
    else:
        old = _load_progress(path)
        _progress = {
            **old,
            "index": index,
            "resumed_at": _now(),
            "initial_pending": initial_pending,
            "tagged_total": old.get("tagged_total", 0),
            "cached_total": old.get("cached_total", 0),
            "failed_batches": old.get("failed_batches", 0),
            "scanned_total": old.get("scanned_total", 0),
        }
        _stats["tagged"] = int(_progress.get("tagged_total", 0))
        _stats["cached"] = int(_progress.get("cached_total", 0))
        _stats["llm_fail"] = int(_progress.get("failed_batches", 0))
        _stats["scanned"] = int(_progress.get("scanned_total", 0))


def print_progress_status(path: Optional[Path] = None):
    p = path or DEFAULT_PROGRESS_FILE
    data = _load_progress(p)
    if not data:
        print(f"无进度文件: {p}")
        return
    pending_hint = data.get("initial_pending", "?")
    tagged = data.get("tagged_total", 0)
    cached = data.get("cached_total", 0)
    failed = data.get("failed_batches", 0)
    scanned = data.get("scanned_total", 0)
    print(f"进度文件: {p}")
    print(f"索引: {data.get('index')}")
    print(f"开始: {data.get('started_at')}  更新: {data.get('updated_at')}")
    if data.get("resumed_at"):
        print(f"最近续跑: {data.get('resumed_at')}")
    print(f"待标(启动时): {pending_hint}  已扫描: {scanned}  已标注: {tagged}  模板复用: {cached}  失败批次: {failed}")
    last = data.get("last_batch_urls") or []
    if last:
        print("最近一批 URL:")
        for u in last[:5]:
            print(f"  - {u}")


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
    with _stats_lock:
        _stats["tagged"] += 1


def process_batch(es: Elasticsearch, index: str, hits: List[Dict]) -> int:
    pending_features: List[Dict] = []
    pending_hits: List[Dict] = []
    done = 0
    batch_urls: List[str] = []

    with _stats_lock:
        _stats["scanned"] += len(hits)

    for hit in hits:
        src = hit.get("_source", {})
        url = src.get("url") or hit.get("_id", "")
        if not needs_llm_tagging(
            {"tag_status": src.get("tag_status"), "tags_detail": src.get("tags_detail") or []}
        ):
            continue
        tkey = _template_key(hit)
        with _template_lock:
            cached = _template_cache.get(tkey)
        if cached:
            _apply(es, index, hit, cached)
            with _stats_lock:
                _stats["cached"] += 1
            done += 1
            batch_urls.append(url)
            continue
        pf = src.get("page_features") or {
            "url": url,
            "title": src.get("title", ""),
            "headings": [],
            "keywords": [],
            "snippet": (src.get("content") or "")[:500],
            "rule_hints": src.get("tags_kw") or [],
        }
        pending_features.append(pf)
        pending_hits.append(hit)

    if not pending_hits:
        with _stats_lock:
            _stats["skipped"] += len(hits) - done
        if batch_urls:
            with _progress_lock:
                _progress["last_batch_urls"] = batch_urls[-10:]
            _save_progress()
        return done

    llm_map = None
    last_err = None
    for attempt in range(3):
        try:
            llm_map = tag_pages_batch_with_llm(pending_features)
            break
        except Exception as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    if llm_map is None:
        print(f"LLM 批次失败(重试3次): {last_err}")
        with _stats_lock:
            _stats["llm_fail"] += 1
        _save_progress()
        return done

    for idx, hit in enumerate(pending_hits):
        src = hit.get("_source", {})
        merged = merge_llm_into_rule_tags(src.get("tags_detail") or [], llm_map.get(str(idx), []))
        _apply(es, index, hit, merged)
        with _template_lock:
            _template_cache[_template_key(hit)] = merged
        batch_urls.append(src.get("url") or hit["_id"])
        done += 1

    with _progress_lock:
        _progress["last_batch_urls"] = batch_urls[-10:]
    _save_progress()
    return done


def _ensure_mapping(es: Elasticsearch, index: str):
    existing = {}
    try:
        m = es.indices.get_mapping(index=index)
        existing = m[index]["mappings"].get("properties", {})
    except Exception:
        pass
    to_add = {}
    if "page_features" not in existing:
        to_add["page_features"] = {"type": "object", "enabled": False}
    if "tag_status" not in existing:
        to_add["tag_status"] = {"type": "keyword"}
    if not to_add:
        return
    try:
        es.indices.put_mapping(index=index, body={"properties": to_add})
    except BadRequestError as e:
        print(f"put_mapping 跳过: {e}")


def _count_pending(es: Elasticsearch, index: str) -> int:
    try:
        r = es.count(index=index, query=PENDING_QUERY)
        return int(r.get("count", 0))
    except Exception:
        return 0


def run(batch_size: int, workers: int, limit: int, progress_file: Path, reset_progress: bool):
    if not llm_available():
        print("请在 .env.key 中配置 DEEPSEEK_API_KEY")
        sys.exit(1)

    es = Elasticsearch(settings.ES_HOST, request_timeout=120)
    index = settings.ES_INDEX_NAME
    _ensure_mapping(es, index)

    pending = _count_pending(es, index)
    _init_progress(progress_file, index, pending, reset_progress)
    print(f"待标注约 {pending} 条 | 进度文件 {progress_file}")
    if _progress.get("resumed_at"):
        print(f"续跑会话，历史已标注 {_stats['tagged']} 条")

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

    try:
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
                remain = _count_pending(es, index)
                print(
                    f"批次 +{n} | 本轮累计 {updated} | 总已标 {_stats['tagged']} | 剩余约 {remain}"
                )
    except KeyboardInterrupt:
        print("\n已中断，进度已写入。重新运行 batch-tag 即可续标。")
        _save_progress()
        raise
    finally:
        try:
            if sid:
                es.clear_scroll(scroll_id=sid)
        except Exception:
            pass
        _save_progress()

    print(
        f"完成 | 本轮 LLM 更新 {updated} | 总已标 {_stats['tagged']} | "
        f"失败批次 {_stats['llm_fail']} | 模板复用 {_stats['cached']} | 进度 {progress_file}"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--batch-size", type=int, default=settings.BATCH_TAG_SIZE)
    p.add_argument("--workers", type=int, default=settings.BATCH_TAG_WORKERS)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument(
        "--progress-file",
        type=str,
        default=str(DEFAULT_PROGRESS_FILE),
        help="进度 JSON 路径",
    )
    p.add_argument("--reset-progress", action="store_true", help="清空进度计数后重新开始")
    p.add_argument("--status", action="store_true", help="仅查看进度文件")
    args = p.parse_args()
    pf = Path(args.progress_file)
    if args.status:
        print_progress_status(pf)
        sys.exit(0)
    run(args.batch_size, args.workers, args.limit, pf, args.reset_progress)
