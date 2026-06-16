import json
import logging
import os
import re
from typing import Dict, List, Set, Optional, Tuple
from urllib.parse import urlparse

from config.env_settings import settings
COLLEGE_ENTRIES: List[Tuple[str, str, str, str]] = [
    ("文学院", "wxy.nankai.edu.cn", "人文社科类", "人文学科群"),
    ("历史学院", "history.nankai.edu.cn", "人文社科类", "人文学科群"),
    ("哲学院", "phil.nankai.edu.cn", "人文社科类", "人文学科群"),
    ("外国语学院", "fsc.nankai.edu.cn", "人文社科类", "人文学科群"),
    ("汉语言文化学院", "hyxy.nankai.edu.cn", "人文社科类", "人文学科群"),
    ("法学院", "law.nankai.edu.cn", "人文社科类", "社会科学群"),
    ("周恩来政府管理学院", "zfxy.nankai.edu.cn", "人文社科类", "社会科学群"),
    ("马克思主义学院", "my.nankai.edu.cn", "人文社科类", "社会科学群"),
    ("社会学院", "shxy.nankai.edu.cn", "人文社科类", "社会科学群"),
    ("新闻与传播学院", "jc.nankai.edu.cn", "人文社科类", "社会科学群"),
    ("经济学院", "economics.nankai.edu.cn", "人文社科类", "经济管理群"),
    ("金融学院", "finance.nankai.edu.cn", "人文社科类", "经济管理群"),
    ("商学院", "bs.nankai.edu.cn", "人文社科类", "经济管理群"),
    ("旅游与服务学院", "tas.nankai.edu.cn", "人文社科类", "经济管理群"),
    ("国际教育学院", "sie.nankai.edu.cn", "人文社科类", "直属与交叉群"),
    ("数学科学学院", "math.nankai.edu.cn", "理工医学类", "数学群"),
    ("统计与数据科学学院", "stat.nankai.edu.cn", "理工医学类", "数学群"),
    ("物理科学学院", "physics.nankai.edu.cn", "理工医学类", "物理光电群"),
    ("电子信息与光学工程学院", "ceo.nankai.edu.cn", "理工医学类", "物理光电群"),
    ("化学学院", "chem.nankai.edu.cn", "理工医学类", "化材群"),
    ("材料科学与工程学院", "mse.nankai.edu.cn", "理工医学类", "化材群"),
    ("生命科学学院", "sky.nankai.edu.cn", "理工医学类", "生医环群"),
    ("环境科学与工程学院", "env.nankai.edu.cn", "理工医学类", "生医环群"),
    ("医学院", "medical.nankai.edu.cn", "理工医学类", "生医环群"),
    ("药学院", "pharmacy.nankai.edu.cn", "理工医学类", "生医环群"),
    ("计算机学院", "cc.nankai.edu.cn", "理工医学类", "信息科学群"),
    ("软件学院", "cs.nankai.edu.cn", "理工医学类", "信息科学群"),
    ("密码与网络空间安全学院", "cs.nankai.edu.cn", "理工医学类", "信息科学群"),
    ("人工智能学院", "ai.nankai.edu.cn", "理工医学类", "信息科学群"),
]

PORTAL_RULES = [
    ("news.nankai.edu.cn", ["topic:新闻"]),
    ("www.nankai.edu.cn", ["topic:综合"]),
    ("jwc.nankai.edu.cn", ["topic:教务", "topic:教育"]),
    ("graduate.nankai.edu.cn", ["topic:学术"]),
]

TOPIC_RULES = [
    ("topic:新闻", ("新闻", "通知", "公告", "动态", "报道", "要闻", "天开园")),
    ("topic:教务", ("教务", "选课", "成绩", "学籍", "考试安排", "培养方案")),
    ("topic:教育", ("教育", "教学", "课程", "师资", "教材", "育人")),
    ("topic:学术", ("学术", "科研", "论文", "课题", "研究生", "学术会议")),
    ("topic:综合", ("概况", "简介", "联系我们", "办事指南")),
]

_CATEGORY_KEYWORDS = (
    ("新闻", ("新闻", "校庆", "通知", "公告", "天开园")),
    ("教务", ("教务", "选课", "成绩", "招生", "规章")),
    ("教育", ("教育", "教学", "课程", "培养")),
    ("学术", ("科研", "论文", "研究生", "学术")),
)

QUERY_SUBJECT_HINTS = (
    ("计算机", ("计算机学院", "软件学院", "人工智能学院", "密码与网络空间安全学院"), "信息科学群", "理工医学类", 0.93),
    ("软件", ("软件学院", "计算机学院"), "信息科学群", "理工医学类", 0.88),
    ("人工智能", ("人工智能学院", "计算机学院"), "信息科学群", "理工医学类", 0.90),
    ("数学", ("数学科学学院", "统计与数据科学学院"), "数学群", "理工医学类", 0.90),
    ("物理", ("物理科学学院", "电子信息与光学工程学院"), "物理光电群", "理工医学类", 0.88),
    ("化学", ("化学学院", "材料科学与工程学院"), "化材群", "理工医学类", 0.88),
    ("经济", ("经济学院", "金融学院", "商学院"), "经济管理群", "人文社科类", 0.85),
    ("金融", ("金融学院", "经济学院"), "经济管理群", "人文社科类", 0.85),
    ("法学", ("法学院",), "社会科学群", "人文社科类", 0.85),
    ("新闻", ("新闻与传播学院",), "社会科学群", "人文社科类", 0.82),
    ("医学", ("医学院", "药学院"), "生医环群", "理工医学类", 0.85),
    ("环境", ("环境科学与工程学院",), "生医环群", "理工医学类", 0.82),
)


def normalize_title(title: str) -> str:
    if not title:
        return ""
    m = re.search(r"【([^】]*)】", title)
    if m:
        return f"grp:{m.group(1).strip()}"
    t = re.sub(r"-南开要闻.*$", "", title)
    t = re.sub(r"-南开大学.*$", "", t)
    t = re.sub(r"\s+", "", t)
    return t[:80] or title[:80]


def colleges_as_dicts() -> List[Dict]:
    return [
        {
            "college_id": idx + 1,
            "college_name": name,
            "category": macro,
            "sub_category": group,
        }
        for idx, (name, _domain, macro, group) in enumerate(COLLEGE_ENTRIES)
    ]


def _host(url: str) -> str:
    if not url:
        return ""
    h = urlparse(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def infer_query_category(query_text: str) -> str:
    profile = infer_query_tag_profile(query_text)
    topics = [p for p in profile if p.get("namespace") == "topic"]
    if topics:
        return topics[0]["value"]
    return "综合"


def infer_query_tag_profile(query_text: str) -> List[Dict]:
    q = (query_text or "").strip()
    if not q:
        return [{"namespace": "topic", "value": "综合", "confidence": 0.3, "tag": "topic:综合"}]

    profile: List[Dict] = []
    seen: Set[str] = set()

    def add(ns: str, val: str, conf: float):
        key = f"{ns}:{val}"
        if key in seen:
            return
        seen.add(key)
        profile.append({"namespace": ns, "value": val, "confidence": conf, "tag": key})

    for hint, colleges, group, macro, base_conf in QUERY_SUBJECT_HINTS:
        if hint not in q:
            continue
        for name in colleges:
            add("college", name, base_conf * (0.98 if name in q else 0.85))
        add("group", group, base_conf * 0.92)
        add("macro", macro, base_conf * 0.88)

    for name, _domain, macro, group in COLLEGE_ENTRIES:
        short = name.replace("学院", "").replace("科学", "")
        if name in q or (len(short) >= 2 and short in q):
            add("college", name, 0.95)
            add("macro", macro, 0.82)
            add("group", group, 0.80)

    for cat, kws in _CATEGORY_KEYWORDS:
        hits = [kw for kw in kws if kw in q]
        if hits:
            add("topic", cat, min(0.55 + 0.12 * len(hits), 0.92))

    if not profile:
        add("topic", "综合", 0.35)
    return sorted(profile, key=lambda x: -x["confidence"])


def _merge_query_profiles(rule_profile: List[Dict], llm_rows: List[Dict]) -> List[Dict]:
    merged: Dict[str, Dict] = {}
    for row in rule_profile:
        tag = row.get("tag") or f"{row.get('namespace')}:{row.get('value')}"
        merged[tag] = {**row, "tag": tag, "source": row.get("source", "rule")}
    for row in llm_rows:
        tag = row.get("tag") or f"{row.get('namespace')}:{row.get('value')}"
        if tag not in merged or row.get("confidence", 0) > merged[tag].get("confidence", 0):
            merged[tag] = row
    return sorted(merged.values(), key=lambda x: -float(x.get("confidence", 0)))


def _needs_llm_intent(profile: List[Dict]) -> bool:
    if not profile:
        return True
    if len(profile) == 1 and profile[0].get("tag") == "topic:综合":
        return True
    if all(float(p.get("confidence", 0)) < 0.55 for p in profile):
        return True
    has_subject = any(p.get("namespace") in ("college", "group", "macro") for p in profile)
    has_topic = any(p.get("namespace") == "topic" and p.get("value") != "综合" for p in profile)
    return not has_subject and not has_topic


def resolve_query_intent(query_text: str) -> Dict:
    q = (query_text or "").strip()
    rule_profile = infer_query_tag_profile(q)
    for row in rule_profile:
        row.setdefault("source", "rule")

    profile = rule_profile
    source = "rule"
    if _needs_llm_intent(rule_profile):
        try:
            from config.llm_page_tagger import llm_available, infer_query_intent_llm
            if llm_available():
                llm_rows = infer_query_intent_llm(q)
                if llm_rows:
                    profile = _merge_query_profiles(rule_profile, llm_rows)
                    source = "hybrid"
        except Exception as e:
            logging.getLogger(__name__).warning("query intent LLM skipped: %s", e)

    topics = [p for p in profile if p.get("namespace") == "topic"]
    category = topics[0]["value"] if topics else "综合"
    return {
        "query_text": q,
        "category": category,
        "tags": profile[:8],
        "source": source,
    }


def format_query_intent_display(intent: Dict) -> List[Dict[str, str]]:
    type_name = {"college": "学院", "macro": "大类", "group": "学科群", "topic": "主题"}
    out = []
    for row in intent.get("tags") or []:
        ns = row.get("namespace", "topic")
        val = row.get("value", "")
        conf = float(row.get("confidence", 0))
        prefix = type_name.get(ns, ns)
        suffix = f" {int(conf * 100)}%" if conf < 0.95 else ""
        out.append({"type": ns, "label": f"{prefix}:{val}{suffix}"})
    return out


def tag_page_rules(url: str, title: str = "", content: str = "") -> List[str]:
    return list(tag_page_rules_scored(url, title, content).keys())


def tag_page_rules_scored(url: str, title: str = "", content: str = "") -> Dict[str, float]:
    scores: Dict[str, float] = {}
    host = _host(url)
    title_blob = (title or "")[:500]
    blob = f"{title_blob} {(content or '')[:3000]}"

    for portal_host, portal_tags in PORTAL_RULES:
        if host == portal_host or host.endswith("." + portal_host):
            for t in portal_tags:
                scores[t] = max(scores.get(t, 0), 0.78)

    for name, domain, macro, group in COLLEGE_ENTRIES:
        if host == domain or host.endswith("." + domain):
            scores[f"college:{name}"] = 0.95
            scores[f"macro:{macro}"] = 0.90
            scores[f"group:{group}"] = 0.88

    for tag, keywords in TOPIC_RULES:
        title_hits = sum(1 for kw in keywords if kw in title_blob)
        body_hits = sum(1 for kw in keywords if kw in blob)
        hits = title_hits + body_hits
        if hits == 0:
            continue
        conf = 0.50 + 0.08 * hits + (0.12 if title_hits else 0)
        matched_kws = [kw for kw in keywords if kw in blob or kw in title_blob]
        if hits == 1 and matched_kws and max(len(kw) for kw in matched_kws) < 3:
            conf = min(conf, 0.62)
        scores[tag] = max(scores.get(tag, 0), min(conf, 0.85))

    topic_tags = [t for t in scores if t.startswith("topic:")]
    if len(topic_tags) > 3:
        ranked = sorted(((t, scores[t]) for t in topic_tags), key=lambda x: -x[1])
        for t, _ in ranked[3:]:
            del scores[t]

    if not any(t.startswith("topic:") for t in scores):
        scores["topic:综合"] = 0.38

    return scores


def tag_page(url: str, title: str = "", content: str = "") -> List[str]:
    return tag_page_enriched(url, title, content)["tags_kw"]


def tag_page_enriched(url: str, title: str = "", content: str = "") -> Dict:
    rule_scores = tag_page_rules_scored(url, title, content)
    rule_tags = sorted(rule_scores.keys())
    min_conf = settings.TAGGER_MIN_CONFIDENCE
    mode = (settings.TAGGER_MODE or "hybrid").lower()
    if (settings.CRAWL_TAGGER_MODE or "rule").lower() == "rule":
        mode = "rule"

    details: Dict[str, Dict] = {}
    for t, conf in rule_scores.items():
        details[t] = {
            "tag": t,
            "namespace": t.split(":", 1)[0] if ":" in t else "other",
            "value": t.split(":", 1)[1] if ":" in t else t,
            "confidence": round(conf, 4),
            "source": "rule",
        }

    if mode in ("llm", "hybrid"):
        try:
            from config.llm_page_tagger import llm_available, tag_page_with_llm

            if llm_available():
                for row in tag_page_with_llm(url, title, content, rule_hints=rule_tags):
                    tag = row["tag"]
                    if tag not in details or row["confidence"] > details[tag]["confidence"]:
                        details[tag] = row
            else:
                logging.getLogger(__name__).debug("LLM tagger skipped: DEEPSEEK_API_KEY not set")
        except Exception as e:
            logging.getLogger(__name__).warning("LLM tagger skipped: %s", e)

    tags_kw = sorted(t for t, d in details.items() if d["confidence"] >= min_conf)
    tag_status = "llm_done" if any(d.get("source") == "llm" for d in details.values()) else "rule_only"
    return {
        "tags_kw": tags_kw,
        "tags_detail": sorted(details.values(), key=lambda x: -x["confidence"]),
        "tag_status": tag_status,
    }


def tag_page_crawl_only(url: str, title: str = "", content: str = "", page_features: Optional[Dict] = None) -> Dict:
    from config.page_features import build_page_features
    pf = page_features or build_page_features(url, title, content)
    rule_hints = pf.get("rule_hints")
    if not rule_hints:
        rule_hints = tag_page_rules(url, title, content)
        pf["rule_hints"] = rule_hints
    rule_scores = tag_page_rules_scored(url, title, content)
    min_conf = settings.TAGGER_MIN_CONFIDENCE
    details: Dict[str, Dict] = {}
    for t, conf in rule_scores.items():
        details[t] = {
            "tag": t,
            "namespace": t.split(":", 1)[0] if ":" in t else "other",
            "value": t.split(":", 1)[1] if ":" in t else t,
            "confidence": round(conf, 4),
            "source": "rule",
        }

    tags_kw = sorted(t for t, d in details.items() if d["confidence"] >= min_conf)
    return {
        "tags_kw": tags_kw,
        "tags_detail": sorted(details.values(), key=lambda x: -x["confidence"]),
        "tag_status": "pending",
        "page_features": pf,
        "rule_hints": rule_hints,
    }


def merge_llm_into_rule_tags(rule_details: List[Dict], llm_rows: List[Dict]) -> Dict:
    min_conf = settings.TAGGER_MIN_CONFIDENCE
    details: Dict[str, Dict] = {}
    for row in rule_details or []:
        tag = row.get("tag") or f"{row.get('namespace')}:{row.get('value')}"
        details[tag] = dict(row, tag=tag)

    for row in llm_rows or []:
        tag = row.get("tag") or f"{row.get('namespace')}:{row.get('value')}"
        if tag not in details or row.get("confidence", 0) > details[tag].get("confidence", 0):
            details[tag] = row

    tags_kw = sorted(t for t, d in details.items() if d.get("confidence", 0) >= min_conf)
    return {
        "tags_kw": tags_kw,
        "tags_detail": sorted(details.values(), key=lambda x: -float(x.get("confidence", 0))),
        "tag_status": "llm_done" if llm_rows else "rule_only",
    }


def needs_llm_tagging(enriched: Dict) -> bool:
    if enriched.get("tag_status") == "llm_done":
        return False
    details = enriched.get("tags_detail") or []
    if any(d.get("source") == "llm" for d in details):
        return False
    topic_rows = [d for d in details if (d.get("namespace") or d.get("tag", "").split(":")[0]) == "topic"]
    if not topic_rows:
        return True
    if len(topic_rows) == 1 and topic_rows[0].get("value") == "综合":
        return float(topic_rows[0].get("confidence", 0)) < 0.5
    weak = all(float(d.get("confidence", 0)) < 0.72 for d in topic_rows)
    return weak


def build_user_tag_weights(context: Optional[Dict]) -> Dict[str, float]:
    if not context:
        return {}
    weights: Dict[str, float] = {}
    college = context.get("college_name")
    q = (context.get("query_text") or "").strip()

    if college:
        weights[f"college:{college}"] = 2.0
        short = college.replace("学院", "").replace("科学", "")
        if short and len(short) >= 2 and short in q:
            weights[f"college:{college}"] += 2.0
        if "学院" in q or "科学" in q:
            weights[f"college:{college}"] = max(weights.get(f"college:{college}", 0), 3.5)

    for name in context.get("sibling_colleges_t1", []):
        weights[f"college:{name}"] = max(weights.get(f"college:{name}", 0), 0.7)

    for name in context.get("sibling_colleges_t2", []):
        weights[f"college:{name}"] = max(weights.get(f"college:{name}", 0), 0.25)

    macro = context.get("macro_category")
    if macro:
        weights[f"macro:{macro}"] = 1.2

    group = context.get("sub_category")
    if group:
        weights[f"group:{group}"] = 1.5

    for interest in context.get("active_interests", []):
        weights[f"topic:{interest}"] = max(weights.get(f"topic:{interest}", 0), 1.4)

    interest_w = float(context.get("weight", 1.0))
    boost = max(0, (interest_w - 1.0) * 2.0)
    for topic in context.get("active_interests", []):
        weights[f"topic:{topic}"] = max(weights.get(f"topic:{topic}", 0), 1.2 + boost)

    qc = context.get("query_category", "综合")
    weights[f"topic:{qc}"] = weights.get(f"topic:{qc}", 0) + 0.8

    role = context.get("role", "访客")
    if role == "本科生":
        weights["topic:教务"] = max(weights.get("topic:教务", 0), 0.45)
    elif role == "研究生":
        weights["topic:学术"] = max(weights.get("topic:学术", 0), 0.5)

    for kw in context.get("recent_keywords", []):
        kw = (kw or "").strip()
        if not kw or kw == q:
            continue
        if college and college in kw:
            weights[f"college:{college}"] = max(weights.get(f"college:{college}", 0), 1.2)
        for cat, keys in _CATEGORY_KEYWORDS:
            if any(k in kw for k in keys):
                weights[f"topic:{cat}"] = max(weights.get(f"topic:{cat}", 0), 0.35)

    return weights


def compute_tag_match_score(
    page_tags_detail: Optional[List[Dict]],
    page_tags_kw: Optional[List[str]],
    query_profile: List[Dict],
    user_weights: Optional[Dict[str, float]] = None,
) -> float:
    if not query_profile:
        return 0.0
    page_map: Dict[str, float] = {}
    if page_tags_detail and isinstance(page_tags_detail, list):
        for row in page_tags_detail:
            if not isinstance(row, dict):
                continue
            tag = row.get("tag") or ""
            if not tag and row.get("namespace"):
                tag = f"{row['namespace']}:{row.get('value', '')}"
            if tag:
                page_map[tag] = max(page_map.get(tag, 0), float(row.get("confidence", 0.7)))
    elif page_tags_kw:
        for t in page_tags_kw:
            if t:
                page_map[t] = 0.65

    score = 0.0
    uw = user_weights or {}
    for q in query_profile:
        tag = q.get("tag") or f"{q.get('namespace')}:{q.get('value')}"
        qconf = float(q.get("confidence", 0.5))
        pconf = page_map.get(tag, 0.0)
        if pconf > 0:
            score += qconf * pconf * (1.0 + 0.15 * uw.get(tag, 0.0))
    return score
