import json
import logging
import re
import threading
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import quote
from urllib.request import urlopen

try:
    from rapidfuzz import fuzz, process
except ImportError:
    fuzz = None
    process = None

from difflib import get_close_matches

try:
    import jieba
    jieba.setLogLevel(logging.ERROR)
except ImportError:
    jieba = None

_STATIC_SEEDS = (
    "南开大学", "南开", "数学科学学院", "历史学院", "计算机学院", "教务处",
    "新闻", "通知公告", "选课", "研究生", "科研", "学院概况", "联系我们",
)

_ENGLISH_RE = re.compile(r"^[\x00-\x7f\s\-_'.,!?]+$")
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")

# 纠错保守 / 补全激进
_CORRECT_APPLY_SCORE = 94
_CORRECT_SINGLE_TOKEN_SCORE = 93
_CORRECT_MULTI_TOKEN_SCORE = 96
_SUGGEST_FUZZY_MIN = 62
_SUGGEST_TOKEN_FUZZY_MIN = 58
_SHORT_QUERY_JIEBA_LEN = 12
_DEFAULT_EN_ENGINE = "http://127.0.0.1:8080"


class QuerySuggestService:
    def __init__(self, correct_engine_url: str = ""):
        url = (correct_engine_url or "").strip().rstrip("/")
        self._correct_engine_url = url or _DEFAULT_EN_ENGINE
        self._vocab: List[str] = []
        self._vocab_set: Set[str] = set()
        self._lock = threading.Lock()
        self._loaded = False

    def ensure_vocabulary(self, mysql_dao, es_dao=None) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._vocab = self._build_vocabulary(mysql_dao, es_dao)
            self._vocab_set = set(self._vocab)
            self._loaded = True
            logging.info("Query vocabulary loaded: %d terms", len(self._vocab))

    def reload_vocabulary(self, mysql_dao, es_dao=None) -> int:
        with self._lock:
            self._vocab = self._build_vocabulary(mysql_dao, es_dao)
            self._vocab_set = set(self._vocab)
            self._loaded = True
            return len(self._vocab)

    def _build_vocabulary(self, mysql_dao, es_dao=None) -> List[str]:
        seen: Set[str] = set()
        ordered: List[str] = []

        def add(term: str) -> None:
            t = (term or "").strip()
            if len(t) < 2 or t in seen:
                return
            seen.add(t)
            ordered.append(t)

        for s in _STATIC_SEEDS:
            add(s)
        if es_dao:
            try:
                for title in es_dao.fetch_frequent_titles(500):
                    add(title)
                    for part in re.split(r"[-—|【】\s]+", title):
                        if 2 <= len(part) <= 24:
                            add(part)
            except Exception as e:
                logging.warning("ES frequent titles load failed: %s", e)
        try:
            for row in mysql_dao.get_popular_search_queries(400):
                add(row["query_text"])
        except Exception as e:
            logging.warning("popular queries load failed: %s", e)
        try:
            for name in mysql_dao.get_college_names():
                add(name)
                short = name.replace("学院", "").replace("科学", "")
                if len(short) >= 2:
                    add(short)
        except Exception as e:
            logging.warning("college names load failed: %s", e)
        try:
            for title in mysql_dao.get_distinct_titles(800):
                add(title)
                for part in re.split(r"[-—|【】\s]+", title):
                    if 2 <= len(part) <= 20:
                        add(part)
        except Exception as e:
            logging.warning("titles load failed: %s", e)
        return ordered

    @staticmethod
    def _is_chinese(q: str) -> bool:
        return bool(_CHINESE_RE.search(q))

    @staticmethod
    def _jieba_tokens(text: str) -> List[str]:
        if not jieba or not text:
            return [text] if text else []
        return [w.strip() for w in jieba.lcut(text.strip()) if len(w.strip()) >= 1]

    @staticmethod
    def _use_jieba_path(q: str) -> bool:
        return _CHINESE_RE.search(q) is not None and len(q) <= _SHORT_QUERY_JIEBA_LEN

    def suggest(
        self,
        prefix: str,
        user_id: Optional[int],
        mysql_dao,
        es_dao=None,
        limit: int = 8,
    ) -> List[Dict]:
        self.ensure_vocabulary(mysql_dao, es_dao)
        q = (prefix or "").strip()
        if not q:
            return []

        if _ENGLISH_RE.match(q):
            ext = self._english_suggest(q, limit)
            if ext:
                return ext

        out: List[Dict] = []
        seen: Set[str] = set()

        def push(text: str, source: str, score: float) -> None:
            t = text.strip()
            if not t or t in seen:
                return
            seen.add(t)
            out.append({"text": t, "source": source, "score": round(score, 4)})

        if user_id:
            for hist in mysql_dao.get_recent_search_logs(user_id, 15):
                if hist.startswith(q) or q in hist:
                    push(hist, "history", 1.0)

        for term in self._vocab:
            if term.startswith(q):
                push(term, "prefix", 0.92 - min(len(term) - len(q), 24) * 0.008)
            elif len(q) >= 2 and q in term:
                push(term, "contains", 0.78)

        if self._use_jieba_path(q):
            tokens = self._jieba_tokens(q)
            for tok in tokens:
                if len(tok) < 1:
                    continue
                for term in self._vocab:
                    if term.startswith(tok) and term != q:
                        push(term, "prefix", 0.85 - min(len(term) - len(tok), 20) * 0.01)
                for text, sc in self._fuzzy_match(tok, limit * 2, min_score=_SUGGEST_TOKEN_FUZZY_MIN):
                    if text not in seen:
                        push(text, "fuzzy", sc / 100.0 * 0.82)

        if len(out) < limit * 2:
            for text, sc in self._fuzzy_match(q, limit * 3, min_score=_SUGGEST_FUZZY_MIN):
                push(text, "fuzzy", sc / 100.0 * 0.8)

        correction = self.correct(q, mysql_dao, es_dao)
        if correction["changed"] and correction["corrected"] not in seen:
            push(correction["corrected"], "correct", 0.72)

        out.sort(key=lambda x: -x["score"])
        return out[:limit]

    def correct(self, query: str, mysql_dao, es_dao=None) -> Dict:
        self.ensure_vocabulary(mysql_dao, es_dao)
        q = (query or "").strip()
        if not q:
            return {"original": q, "corrected": q, "changed": False, "candidates": []}

        if _ENGLISH_RE.match(q):
            ext = self._english_correct(q)
            if ext:
                return ext

        if q in self._vocab_set:
            return {"original": q, "corrected": q, "changed": False, "candidates": []}

        if self._use_jieba_path(q) and jieba:
            return self._correct_chinese_short(q)

        candidates = self._fuzzy_match(q, 5, min_score=85)
        if not candidates:
            return {"original": q, "corrected": q, "changed": False, "candidates": []}

        best_text, best_score = candidates[0]
        changed = self._should_apply_correction(q, best_text, best_score, _CORRECT_APPLY_SCORE)
        return self._correction_result(q, best_text, best_score, changed, candidates)

    def _correct_chinese_short(self, q: str) -> Dict:
        tokens = [t for t in self._jieba_tokens(q) if t]
        if not tokens:
            return {"original": q, "corrected": q, "changed": False, "candidates": []}

        if len(tokens) == 1:
            tok = tokens[0]
            if tok in self._vocab_set:
                return {"original": q, "corrected": q, "changed": False, "candidates": []}
            candidates = self._fuzzy_match(tok, 5, min_score=88)
            if not candidates:
                return {"original": q, "corrected": q, "changed": False, "candidates": []}
            best_text, best_score = candidates[0]
            changed = self._should_apply_correction(tok, best_text, best_score, _CORRECT_SINGLE_TOKEN_SCORE)
            corrected = best_text if changed else q
            return self._correction_result(q, corrected, best_score, changed and corrected != q, candidates)

        candidates = self._fuzzy_match(q, 5, min_score=88)
        if not candidates:
            return {"original": q, "corrected": q, "changed": False, "candidates": []}
        best_text, best_score = candidates[0]
        changed = self._should_apply_correction(q, best_text, best_score, _CORRECT_MULTI_TOKEN_SCORE)
        return self._correction_result(q, best_text, best_score, changed, candidates)

    @staticmethod
    def _should_apply_correction(original: str, candidate: str, score: float, threshold: float) -> bool:
        if candidate == original:
            return False
        if score < threshold:
            return False
        if abs(len(candidate) - len(original)) > max(2, len(original) // 2):
            return score >= threshold + 3
        return True

    @staticmethod
    def _correction_result(
        q: str,
        best_text: str,
        best_score: float,
        changed: bool,
        candidates: List[Tuple[str, float]],
    ) -> Dict:
        return {
            "original": q,
            "corrected": best_text if changed else q,
            "changed": changed,
            "confidence": round(best_score / 100.0, 4),
            "candidates": [{"text": t, "score": round(s / 100.0, 4)} for t, s in candidates[:5]],
        }

    def _fuzzy_match(self, query: str, limit: int, min_score: int = 75) -> List[Tuple[str, float]]:
        if not self._vocab:
            return []
        if process and fuzz:
            raw = process.extract(query, self._vocab, scorer=fuzz.WRatio, limit=limit)
            return [(t, float(s)) for t, s, _ in raw if s >= min_score]
        hits = get_close_matches(query, self._vocab, n=limit, cutoff=min_score / 100.0)
        return [(t, float(min_score + 5)) for t in hits]

    def _english_suggest(self, q: str, limit: int) -> List[Dict]:
        try:
            url = f"{self._correct_engine_url}/suggest?q={quote(q)}"
            with urlopen(url, timeout=0.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if not isinstance(data, list):
                return []
            out = []
            for i, item in enumerate(data[:limit]):
                text = item.get("suggestion", "")
                if text:
                    out.append({
                        "text": text,
                        "source": "engine_en",
                        "score": 1.0 - i * 0.05,
                    })
            return out
        except Exception as e:
            logging.debug("English suggest engine unavailable: %s", e)
            return []

    def _english_correct(self, q: str) -> Optional[Dict]:
        try:
            url = f"{self._correct_engine_url}/search?q={quote(q)}"
            with urlopen(url, timeout=0.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if not isinstance(data, list) or not data:
                return {"original": q, "corrected": q, "changed": False, "candidates": []}
            top = data[0]
            corrected = (top.get("word") or top.get("suggestion") or q).strip()
            if corrected == q:
                return {"original": q, "corrected": q, "changed": False, "candidates": []}
            if fuzz and fuzz.ratio(q.lower(), corrected.lower()) < 72:
                return {"original": q, "corrected": q, "changed": False, "candidates": []}
            cands = [{"text": (it.get("word") or it.get("suggestion", "")), "score": 0.85} for it in data[:3] if it.get("word") or it.get("suggestion")]
            return {
                "original": q,
                "corrected": corrected,
                "changed": True,
                "confidence": 0.88,
                "candidates": cands,
            }
        except Exception as e:
            logging.debug("English correct engine unavailable: %s", e)
            return None
