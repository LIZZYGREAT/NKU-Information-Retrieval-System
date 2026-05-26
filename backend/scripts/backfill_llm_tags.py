import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from config.env_settings import load_env
from config.page_tagger import tag_page_enriched
from elasticsearch import Elasticsearch
from config.env_settings import settings

load_env()

if not os.environ.get("DEEPSEEK_API_KEY"):
    print("请在 .env.key 中配置 DEEPSEEK_API_KEY")
    sys.exit(1)

es = Elasticsearch(settings.ES_HOST, request_timeout=60)
index = settings.ES_INDEX_NAME

es.indices.put_mapping(
    index=index,
    body={"properties": {"tags_detail": {"type": "object", "enabled": False}}},
)

res = es.search(
    index=index,
    body={"query": {"match_all": {}}, "_source": ["url", "title", "content"], "size": 200},
    scroll="5m",
)
sid = res["_scroll_id"]
n = 0
while True:
    hits = res["hits"]["hits"]
    if not hits:
        break
    for hit in hits:
        src = hit["_source"]
        url = src.get("url") or hit["_id"]
        enriched = tag_page_enriched(url, src.get("title", ""), src.get("content", ""))
        es.update(
            index=index,
            id=hit["_id"],
            doc={
                "tags": enriched["tags_kw"],
                "tags_kw": enriched["tags_kw"],
                "tags_detail": enriched["tags_detail"],
            },
        )
        n += 1
        if n % 20 == 0:
            print(f"已更新 {n} 条")
    res = es.scroll(scroll_id=sid, scroll="5m")
    sid = res["_scroll_id"]
print(f"完成，共 {n} 条")
