import re
from typing import List, Tuple
from urllib.parse import urlparse

REPLACEMENT = "\ufffd"
MOJIBAKE_RE = re.compile(
    r"Ã.|Â.|ä.|å.|æ.|ç.|è.|é.|ê.|ë.|ì.|í.|î.|ï.|ð.|ñ.|ò.|ó.|ô.|õ.|ö.|÷.|ø.|ù.|ú.|û.|ü.|ý.|þ.|ÿ."
)
ERROR_PAGE_RE = re.compile(
    r"404|not\s*found|403|forbidden|access\s*denied|页面不存在|找不到|非法访问|系统错误",
    re.I,
)
GARBAGE_TITLE_RE = re.compile(r"^[\s\-_|·.]+$")


def _cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    n = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return n / len(text)


def detect_garbage(url: str, title: str = "", content: str = "") -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    title = (title or "").strip()
    content = (content or "").strip()
    blob = f"{title}\n{content}"

    host = urlparse(url or "").netloc.lower()
    if host and "nankai.edu.cn" not in host:
        reasons.append("off_domain")

    if REPLACEMENT in blob:
        reasons.append("replacement_char")

    if len(content) < 12 and len(title) < 3:
        reasons.append("empty_content")

    if title in ("无标题", "Untitled", "") and len(content) < 35:
        reasons.append("untitled_empty")

    if GARBAGE_TITLE_RE.match(title) and len(content) < 40:
        reasons.append("invalid_title")

    if ERROR_PAGE_RE.search(title) and len(content) < 250:
        reasons.append("error_page")

    mojibake_hits = len(MOJIBAKE_RE.findall(blob))
    if mojibake_hits >= 4:
        reasons.append("mojibake")
    elif mojibake_hits >= 1 and len(blob) > 40 and _cjk_ratio(blob) < 0.06:
        reasons.append("mojibake")

    if len(blob) > 100 and _cjk_ratio(blob) < 0.05:
        latin_ext = sum(
            1 for c in blob if ord(c) > 127 and not ("\u4e00" <= c <= "\u9fff")
        )
        if latin_ext / len(blob) > 0.4:
            reasons.append("low_cjk_ratio")

    if content:
        printable = sum(1 for c in content if c.isprintable() or c in "\n\r\t")
        if printable / len(content) < 0.82:
            reasons.append("non_printable")

    if content and len(content) > 200:
        unique_chars = len(set(content))
        if unique_chars / len(content) < 0.02:
            reasons.append("repetitive_gibberish")

    return bool(reasons), reasons
