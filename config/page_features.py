import re
from collections import Counter
from typing import Dict, List, Optional

from config.page_tagger import tag_page_rules

_STOP = frozenset(
    "的 了 在 是 我 有 和 就 不 人 都 一 一个 上 也 很 到 说 要 去 你 会 着 没有 看 好 自己 这".split()
)
_WORD_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}")


def extract_headings(response) -> List[str]:
    seen = set()
    out = []
    for xp in ("//h1//text()", "//h2//text()", "//h3//text()"):
        for t in response.xpath(xp).getall():
            t = (t or "").strip()
            if not t or len(t) < 2 or t in seen:
                continue
            seen.add(t)
            out.append(t)
            if len(out) >= 12:
                return out
    return out


def top_keywords(text: str, limit: int = 20) -> List[str]:
    if not text:
        return []
    try:
        import jieba
        words = [w.strip() for w in jieba.lcut(text) if len(w.strip()) >= 2]
    except ImportError:
        words = _WORD_RE.findall(text)
    words = [w for w in words if w not in _STOP and not w.isdigit()]
    return [w for w, _ in Counter(words).most_common(limit)]


def build_page_features(
    url: str,
    title: str = "",
    content: str = "",
    headings: Optional[List[str]] = None,
) -> Dict:
    rule_hints = tag_page_rules(url, title, content)
    snippet = (content or "")[:500]
    kw_source = f"{title or ''} {' '.join(headings or [])} {snippet}"
    return {
        "url": url,
        "title": (title or "")[:200],
        "headings": (headings or [])[:12],
        "keywords": top_keywords(kw_source, 20),
        "snippet": snippet,
        "rule_hints": rule_hints[:12],
    }
