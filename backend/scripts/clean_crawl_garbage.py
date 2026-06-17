import argparse
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pymysql
from elasticsearch import Elasticsearch
from elasticsearch.helpers import scan

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(SCRIPT_DIR))
os.chdir(ROOT / "backend")

from config.env_settings import load_env, settings
from crawl_quality import detect_garbage

load_env()

SNAPSHOT_DIR = ROOT / "backend" / "snapshots"


def _mysql_conn():
    return pymysql.connect(
        host=settings.MYSQL_HOST,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DATABASE,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def _snapshot_file(snapshot_path: Optional[str]) -> Optional[Path]:
    if not snapshot_path:
        return None
    name = os.path.basename(snapshot_path)
    full = SNAPSHOT_DIR / name
    return full if full.is_file() else None


def purge_url(
    url: str,
    es: Elasticsearch,
    index: str,
    conn,
    snapshot_path: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, bool]:
    result = {"es": False, "cache": False, "links": False, "snapshot": False}
    if dry_run:
        return result

    try:
        es.delete(index=index, id=url, ignore=[404])
        result["es"] = True
    except Exception:
        pass

    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM PageLinks WHERE source_url = %s OR target_url = %s",
            (url, url),
        )
        result["links"] = cur.rowcount > 0
        cur.execute("SELECT snapshot_path FROM WebPageCache WHERE url = %s", (url,))
        row = cur.fetchone()
        sp = snapshot_path or (row["snapshot_path"] if row else None)
        cur.execute("DELETE FROM WebPageCache WHERE url = %s", (url,))
        result["cache"] = cur.rowcount > 0
    conn.commit()

    sf = _snapshot_file(sp)
    if sf:
        try:
            sf.unlink()
            result["snapshot"] = True
        except OSError:
            pass
    return result


def scan_garbage(es: Elasticsearch, index: str, limit: int = 0) -> List[Tuple[str, List[str], Dict]]:
    bad: List[Tuple[str, List[str], Dict]] = []
    n = 0
    for doc in scan(
        es,
        index=index,
        query={"query": {"match_all": {}}},
        _source=["url", "title", "content"],
    ):
        src = doc.get("_source", {})
        url = src.get("url") or doc.get("_id", "")
        title = src.get("title") or ""
        content = src.get("content") or ""
        is_bad, reasons = detect_garbage(url, title, content)
        if is_bad:
            bad.append((url, reasons, src))
        n += 1
        if limit and len(bad) >= limit:
            break
        if limit and n >= limit * 50:
            break
    return bad


def run(dry_run: bool, limit: int, url: Optional[str]):
    es = Elasticsearch(settings.ES_HOST, request_timeout=60)
    index = settings.ES_INDEX_NAME

    if url:
        doc = es.get(index=index, id=url, ignore=[404])
        if not doc.get("found"):
            print(f"ES 中无此 URL: {url}")
            return
        src = doc["_source"]
        is_bad, reasons = detect_garbage(url, src.get("title", ""), src.get("content", ""))
        targets = [(url, reasons, src)] if is_bad else []
        if not is_bad:
            print(f"未判定为垃圾页: {url}")
            return
    else:
        print(f"扫描索引 {index} ...")
        targets = scan_garbage(es, index, limit=limit)

    print(f"待清理 {len(targets)} 条")
    if not targets:
        return

    conn = _mysql_conn()
    removed = 0
    try:
        for u, reasons, src in targets:
            line = f"[{','.join(reasons)}] {u}"
            if dry_run:
                print(f"DRY-RUN {line}")
                continue
            purge_url(u, es, index, conn)
            print(f"DEL {line}")
            removed += 1
    finally:
        conn.close()

    if dry_run:
        print(f"试运行结束，共 {len(targets)} 条（未实际删除）")
    else:
        print(f"已清理 {removed} 条")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="清理乱码/无效抓取页，同步删 MySQL+ES+快照")
    p.add_argument("--dry-run", action="store_true", help="只打印不删除")
    p.add_argument("--limit", type=int, default=0, help="最多处理条数，0=不限")
    p.add_argument("--url", type=str, default="", help="只检查并清理指定 URL")
    args = p.parse_args()
    run(args.dry_run, args.limit, args.url.strip() or None)
