import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from config.env_settings import settings
from config.page_tagger import tag_page, normalize_title
from elasticsearch import Elasticsearch

es = Elasticsearch(settings.ES_HOST, request_timeout=60)
index = settings.ES_INDEX_NAME

def _ensure_mapping():
    props = {"title_norm": {"type": "keyword"}, "tags_kw": {"type": "keyword"}}
    try:
        m = es.indices.get_mapping(index=index)
        existing = m[index]["mappings"].get("properties", {})
        to_add = {k: v for k, v in props.items() if k not in existing}
        if to_add:
            es.indices.put_mapping(index=index, body={"properties": to_add})
    except Exception as e:
        print(f"put_mapping 跳过: {e}")

_ensure_mapping()

res = es.search(
    index=index,
    body={"query": {"match_all": {}}, "_source": ["url", "title", "content"], "size": 500},
    scroll="5m",
)
sid = res["_scroll_id"]
updated = 0
while True:
    hits = res["hits"]["hits"]
    if not hits:
        break
    for hit in hits:
        src = hit["_source"]
        url = src.get("url") or hit["_id"]
        title = src.get("title", "")
        tags = tag_page(url, title, src.get("content", ""))
        es.update(
            index=index,
            id=hit["_id"],
            doc={"tags": tags, "tags_kw": tags, "title_norm": normalize_title(title)},
        )
        updated += 1
    res = es.scroll(scroll_id=sid, scroll="5m")
    sid = res["_scroll_id"]
print(f"已更新 {updated} 条文档 tags")
