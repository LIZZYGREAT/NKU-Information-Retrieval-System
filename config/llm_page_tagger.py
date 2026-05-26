import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen

from config.tag_taxonomy import (
    AUDIENCES,
    COLLEGE_NAMES,
    DISCIPLINE_GROUPS,
    INTENTS,
    MACRO_CATEGORIES,
    PAGE_TYPES,
    TOPIC_LABELS,
)

_CACHE: Dict[str, Dict] = {}
_LAST_CALL = 0.0

SYSTEM_PROMPT = """你是南开大学站内网页分类助手。根据 URL、标题与正文摘要，输出结构化标签与置信度。

## 标签命名空间（namespace）与取值
1. college — 所属学院，取值必须来自给定学院名单，或 null
2. macro — 宏观门类：人文社科类 | 理工医学类 | null
3. group — 学科群：人文学科群、社会科学群、经济管理群、直属与交叉群、数学群、物理光电群、化材群、生医环群、信息科学群 | null
4. topic — 主题，从给定主题词表选 1~4 个最贴切项（可组合理解，但 value 必须原样来自词表）
5. page_type — 页面类型，从给定页面类型词表选 1 项
6. audience — 主要受众，从给定受众词表选 1~2 项
7. intent — 访问意图，从给定意图词表选 1 项

## 规则
- 只输出 JSON，不要 Markdown，不要解释。
- confidence 为 0~1 小数；仅当你较确定时 >=0.7；不确定但相关 0.5~0.69；猜测 <0.5 不要输出该条。
- 学院以正文与标题为准；若域名明显属于某学院但正文是全校新闻，college 可为 null，macro 仍可为全校口径。
- 同一 namespace 可多条（如多个 topic），但 college/macro/group 通常各 0~1 条。
- 正文为空或极短时，主要依据 URL 与标题，confidence 相应降低。

## 输出 JSON  schema
{
  "tags": [
    {"namespace": "topic", "value": "通知公告", "confidence": 0.91},
    {"namespace": "page_type", "value": "新闻详情", "confidence": 0.85}
  ]
}"""


def _user_prompt(url: str, title: str, content: str, rule_hints: List[str]) -> str:
    body = (content or "")[:2800]
    hints = ", ".join(rule_hints[:12]) if rule_hints else "无"
    return f"""请标注以下网页。

【学院名单】{", ".join(COLLEGE_NAMES)}
【宏观门类】{", ".join(MACRO_CATEGORIES)}
【学科群】{", ".join(DISCIPLINE_GROUPS)}
【主题词表】{", ".join(TOPIC_LABELS)}
【页面类型】{", ".join(PAGE_TYPES)}
【受众】{", ".join(AUDIENCES)}
【意图】{", ".join(INTENTS)}

【URL】{url}
【标题】{title or "(无标题)"}
【规则引擎预标签（可参考，可修正）】{hints}
【正文摘要】
{body}
"""


def _load_llm_config() -> Dict[str, Any]:
    return {
        "api_key": os.environ.get("DEEPSEEK_API_KEY", "").strip(),
        "base_url": os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        "min_confidence": float(os.environ.get("TAGGER_MIN_CONFIDENCE", "0.55")),
        "enabled": os.environ.get("TAGGER_MODE", "hybrid").lower() in ("llm", "hybrid"),
        "interval_sec": float(os.environ.get("DEEPSEEK_CALL_INTERVAL", "0.35")),
    }


def llm_available() -> bool:
    cfg = _load_llm_config()
    return bool(cfg["enabled"] and cfg["api_key"])


def _throttle(interval: float) -> None:
    global _LAST_CALL
    if interval <= 0:
        return
    now = time.time()
    wait = interval - (now - _LAST_CALL)
    if wait > 0:
        time.sleep(wait)
    _LAST_CALL = time.time()


def _call_deepseek(user_prompt: str) -> str:
    cfg = _load_llm_config()
    if not cfg["api_key"]:
        raise RuntimeError("DEEPSEEK_API_KEY missing")
    _throttle(cfg["interval_sec"])
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    req = Request(
        f"{cfg['base_url']}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}",
        },
        method="POST",
    )
    with urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def _parse_llm_json(raw: str) -> List[Dict[str, Any]]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    obj = json.loads(text)
    items = obj.get("tags") if isinstance(obj, dict) else obj
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        ns = (it.get("namespace") or "").strip()
        val = (it.get("value") or "").strip()
        if not ns or not val or val.lower() == "null":
            continue
        try:
            conf = float(it.get("confidence", 0))
        except (TypeError, ValueError):
            conf = 0.0
        conf = max(0.0, min(1.0, conf))
        out.append({"namespace": ns, "value": val, "confidence": conf})
    return out


def _to_tag_key(namespace: str, value: str) -> str:
    return f"{namespace}:{value}"


def tag_page_with_llm(
    url: str,
    title: str = "",
    content: str = "",
    rule_hints: Optional[List[str]] = None,
    use_cache: bool = True,
) -> List[Dict[str, Any]]:
    cfg = _load_llm_config()
    cache_key = hashlib.md5(f"{url}|{title}|{len(content or '')}".encode()).hexdigest()
    if use_cache and cache_key in _CACHE:
        return _CACHE[cache_key]["tags_detail"]

    hints = rule_hints or []
    raw = _call_deepseek(_user_prompt(url, title, content, hints))
    parsed = _parse_llm_json(raw)
    details = []
    for it in parsed:
        if it["confidence"] < cfg["min_confidence"]:
            continue
        details.append({
            "tag": _to_tag_key(it["namespace"], it["value"]),
            "namespace": it["namespace"],
            "value": it["value"],
            "confidence": round(it["confidence"], 4),
            "source": "llm",
        })
    if use_cache:
        _CACHE[cache_key] = {"tags_detail": details}
    return details
