import json
import re
from typing import Dict, List, Set, Optional, Tuple
from urllib.parse import urlparse

COLLEGE_ENTRIES: List[Tuple[str, str, str, str]] = [
    ("文学院", "wxy.nankai.edu.cn", "人文社科类", "人文学科群"),
    ("历史学院", "history.nankai.edu.cn", "人文社科类", "人文学科群"),
    ("哲学院", "phil.nankai.edu.cn", "人文社科类", "人文学科群"),
    ("外国语学院", "fsc.nankai.edu.cn", "人文社科类", "人文学科群"),
    ("汉语言文化学院", "hyxy.nankai.edu.cn", "人文社科类", "人文学科群"),
    ("法学院", "law.nankai.edu.cn", "人文社科类", "社会科学群"),
    ("周恩来政府管理学院", "zf.nankai.edu.cn", "人文社科类", "社会科学群"),
    ("马克思主义学院", "my.nankai.edu.cn", "人文社科类", "社会科学群"),
    ("社会学院", "shxy.nankai.edu.cn", "人文社科类", "社会科学群"),
    ("新闻与传播学院", "jc.nankai.edu.cn", "人文社科类", "社会科学群"),
    ("经济学院", "eco.nankai.edu.cn", "人文社科类", "经济管理群"),
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
    ("学术", ("科研", "论文", "研究生", "学术", "数学")),
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
    text = (query_text or "").strip()
    for cat, kws in _CATEGORY_KEYWORDS:
        if any(k in text for k in kws):
            return cat
    return "综合"


def tag_page(url: str, title: str = "", content: str = "") -> List[str]:
    tags: Set[str] = set()
    host = _host(url)
    blob = f"{title or ''} {content or ''}"[:4000]

    for portal_host, portal_tags in PORTAL_RULES:
        if host == portal_host or host.endswith("." + portal_host):
            tags.update(portal_tags)

    for name, domain, macro, group in COLLEGE_ENTRIES:
        if host == domain or host.endswith("." + domain):
            tags.add(f"college:{name}")
            tags.add(f"macro:{macro}")
            tags.add(f"group:{group}")

    for tag, keywords in TOPIC_RULES:
        if any(kw in blob or kw in (url or "") for kw in keywords):
            tags.add(tag)

    if not any(t.startswith("topic:") for t in tags):
        tags.add("topic:综合")

    return sorted(tags)


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
        weights[f"macro:{macro}"] = 0.35

    group = context.get("sub_category")
    if group:
        weights[f"group:{group}"] = 0.9

    interest_w = float(context.get("weight", 1.0))
    boost = max(0, (interest_w - 1.0) * 1.2)
    for topic in context.get("active_interests", []):
        weights[f"topic:{topic}"] = max(weights.get(f"topic:{topic}", 0), 0.5 + boost)

    qc = context.get("query_category", "综合")
    weights[f"topic:{qc}"] = weights.get(f"topic:{qc}", 0) + 0.6

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
