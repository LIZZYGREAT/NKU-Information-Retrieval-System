"""
查询建议服务，负责搜索联想、拼写纠错和查询补全功能

主要功能：
1. 查询联想：根据用户输入提供搜索建议
2. 拼写纠错：自动修正输入错误
3. 查询补全：预测用户可能的完整查询
4. 历史记录：结合用户搜索历史提供个性化建议

调用链：
search_router -> QuerySuggestService -> (mysql_dao, es_dao)

依赖：
- rapidfuzz: 模糊匹配算法（可选，降级使用difflib）
- jieba: 中文分词（可选）
"""

import json
import logging
import re
import threading
from collections import defaultdict
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

# 静态种子词：系统内置的常用搜索词
_STATIC_SEEDS = (
    "南开大学", "南开", "数学科学学院", "历史学院", "计算机学院", "教务处",
    "新闻", "通知公告", "选课", "研究生", "科研", "学院概况", "联系我们",
)

# 正则表达式：检测英文和中文
_ENGLISH_RE = re.compile(r"^[\x00-\x7f\s\-_'.,!?]+$")
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")

# 纠错和建议的阈值配置
_CORRECT_APPLY_SCORE = 94          # 纠错应用阈值
_CORRECT_SINGLE_TOKEN_SCORE = 93   # 单分词纠错阈值
_CORRECT_MULTI_TOKEN_SCORE = 96    # 多分词纠错阈值
_SUGGEST_FUZZY_MIN = 62            # 建议模糊匹配最低分
_SUGGEST_TOKEN_FUZZY_MIN = 58      # 分词建议模糊匹配最低分
_SHORT_QUERY_JIEBA_LEN = 24        # 使用结巴分词的最大查询长度
_DEFAULT_EN_ENGINE = "http://127.0.0.1:8080"  # 英文建议引擎地址


class QuerySuggestService:
    """
    查询建议服务类，提供搜索联想、拼写纠错和查询补全功能
    
    核心数据结构：
    - _vocab: 词汇表列表
    - _vocab_set: 词汇表集合（用于快速查找）
    - _term_freq: 词频统计字典
    - _prefix_hits: 前缀索引，用于快速前缀匹配
    
    线程安全：使用_lock保证词汇表加载的线程安全
    """

    def __init__(self, correct_engine_url: str = ""):
        """
        初始化查询建议服务
        
        :param correct_engine_url: 英文拼写纠错引擎URL（可选）
        """
        url = (correct_engine_url or "").strip().rstrip("/")
        self._correct_engine_url = url or _DEFAULT_EN_ENGINE
        self._vocab: List[str] = []        # 词汇表
        self._vocab_set: Set[str] = set()  # 词汇集合（快速查找）
        self._term_freq: Dict[str, int] = defaultdict(int)  # 词频统计
        self._prefix_hits: Dict[str, List[Tuple[str, int]]] = defaultdict(list)  # 前缀索引
        self._lock = threading.Lock()      # 线程锁
        self._loaded = False               # 词汇表是否已加载

    def ensure_vocabulary(self, mysql_dao, es_dao=None) -> None:
        """
        确保词汇表已加载（懒加载）
        
        :param mysql_dao: MySQL数据访问对象
        :param es_dao: Elasticsearch数据访问对象（可选）
        
        线程安全的懒加载机制：
        1. 检查是否已加载
        2. 获取锁后再次检查（双重检查锁定）
        3. 构建词汇表和前缀索引
        """
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._vocab = self._build_vocabulary(mysql_dao, es_dao)
            self._vocab_set = set(self._vocab)
            self._build_prefix_index()
            self._loaded = True
            logging.info("Query vocabulary loaded: %d terms", len(self._vocab))

    def reload_vocabulary(self, mysql_dao, es_dao=None) -> int:
        """
        重新加载词汇表
        
        :param mysql_dao: MySQL数据访问对象
        :param es_dao: Elasticsearch数据访问对象（可选）
        :return: 词汇表大小
        """
        with self._lock:
            self._vocab = self._build_vocabulary(mysql_dao, es_dao)
            self._vocab_set = set(self._vocab)
            self._build_prefix_index()
            self._loaded = True
            return len(self._vocab)

    def _build_prefix_index(self) -> None:
        """
        构建前缀索引
        
        为每个词的所有前缀（1到20字符）建立索引，
        支持快速前缀匹配查询补全功能。
        """
        self._prefix_hits.clear()
        for term, freq in self._term_freq.items():
            for i in range(1, min(len(term), 20)):
                p = term[:i]
                self._prefix_hits[p].append((term, freq))
        # 按词频降序、长度升序排序
        for p in self._prefix_hits:
            self._prefix_hits[p].sort(key=lambda x: (-x[1], len(x[0])))

    def _build_vocabulary(self, mysql_dao, es_dao=None) -> List[str]:
        seen: Set[str] = set()
        ordered: List[str] = []
        self._term_freq = defaultdict(int)

        def add(term: str, weight: int = 1) -> None:
            t = (term or "").strip()
            if len(t) < 2:
                return
            self._term_freq[t] += weight
            if t in seen:
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
                cnt = int(row.get("cnt") or 1)
                add(row["query_text"], cnt)
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

    def _query_tokens(self, q: str) -> List[str]:
        if not q:
            return []
        if _CHINESE_RE.search(q) and jieba:
            toks = [w for w in jieba.lcut(q) if len(w.strip()) >= 1]
            if len(toks) >= 2:
                return toks
        return [q]

    def _token_match_score(self, term: str, tokens: List[str], q: str) -> float:
        if not term:
            return 0.0
        if term.startswith(q):
            return 100.0 + min(len(q), 20)
        if not tokens:
            return 0.0
        joined = "".join(tokens)
        if joined and term.startswith(joined):
            return 96.0 + len(joined) * 0.5
        hit = [t for t in tokens if t in term]
        if not hit:
            return 0.0
        pos = 0
        ordered = True
        for t in tokens:
            idx = term.find(t, pos)
            if idx < 0:
                ordered = False
                break
            pos = idx + len(t)
        score = 55.0 + len(hit) * 12.0
        if len(hit) == len(tokens):
            score += 18.0
        if ordered:
            score += 14.0
        if len(q) >= 2 and q in term:
            score += 8.0
        return score

    def history_suggestions(
        self,
        user_id: Optional[int],
        mysql_dao,
        limit: int = 8,
    ) -> List[Dict]:
        self.ensure_vocabulary(mysql_dao)
        out: List[Dict] = []
        seen: Set[str] = set()

        def push(text: str, source: str, score: float) -> None:
            t = (text or "").strip()
            if len(t) < 1 or t in seen:
                return
            seen.add(t)
            out.append({"text": t, "source": source, "score": score})

        if user_id:
            for hist in mysql_dao.get_recent_search_logs(user_id, limit):
                push(hist, "history", 1.0)
        need = limit - len(out)
        if need > 0:
            try:
                for row in mysql_dao.get_popular_search_queries(need + 5):
                    push(row["query_text"], "hot", 0.85)
                    if len(out) >= limit:
                        break
            except Exception:
                pass
        for s in _STATIC_SEEDS[: max(0, limit - len(out))]:
            push(s, "hot", 0.7)
        return out[:limit]

    def associate(
        self,
        prefix: str,
        user_id: Optional[int],
        mysql_dao,
        es_dao=None,
        limit: int = 8,
    ) -> Dict:
        q = (prefix or "").strip()
        if not q:
            return {
                "query": q,
                "correction": {"original": q, "corrected": q, "changed": False, "candidates": []},
                "top_completion": None,
                "continuations": [],
                "suggestions": [],
            }

        correction = self.correct(q, mysql_dao, es_dao)
        suggestions = self.suggest(q, user_id, mysql_dao, es_dao, limit=limit, skip_correct=True)
        continuations = self._predict_continuations(q, user_id, mysql_dao, limit=limit)

        top = continuations[0] if continuations else None
        if not top and suggestions:
            first = suggestions[0]
            if first["text"].startswith(q) and len(first["text"]) > len(q):
                top = {
                    "full": first["text"],
                    "suffix": first["text"][len(q):],
                    "source": first["source"],
                }

        return {
            "query": q,
            "correction": correction,
            "top_completion": top,
            "continuations": continuations,
            "suggestions": suggestions,
        }

    def _predict_continuations(
        self,
        q: str,
        user_id: Optional[int],
        mysql_dao,
        limit: int = 8,
    ) -> List[Dict]:
        scored: Dict[str, Tuple[float, str]] = {}
        tokens = self._query_tokens(q)

        def add(full: str, source: str, boost: float = 0.0) -> None:
            if len(full) <= len(q):
                return
            if not (full.startswith(q) or self._token_match_score(full, tokens, q) >= 65):
                return
            freq = self._term_freq.get(full, 1)
            tscore = self._token_match_score(full, tokens, q)
            score = tscore + freq * 2.0 + boost
            if full not in scored or scored[full][0] < score:
                scored[full] = (score, source)

        for term, freq in self._prefix_hits.get(q, [])[:80]:
            add(term, "continuation", boost=freq * 2)

        if user_id:
            for hist in mysql_dao.get_recent_search_logs(user_id, 20):
                if hist.startswith(q) and len(hist) > len(q):
                    add(hist, "history", boost=50.0)
                elif self._token_match_score(hist, tokens, q) >= 70:
                    add(hist, "history", boost=40.0)

        for tok in tokens:
            for term, freq in self._prefix_hits.get(tok, [])[:35]:
                add(term, "token", boost=freq + 8.0)
            last = tokens[-1]
            head = q[: max(0, len(q) - len(last))]
            for term, _ in self._prefix_hits.get(last, [])[:30]:
                add(head + term, "token", boost=10.0)

        if tokens and len(tokens) >= 2:
            for term in self._vocab:
                if self._token_match_score(term, tokens, q) >= 75 and len(term) > len(q):
                    add(term, "token", boost=self._term_freq.get(term, 0))

        ranked = sorted(scored.items(), key=lambda x: -x[1][0])
        out = []
        for full, (sc, source) in ranked[:limit]:
            out.append({
                "full": full,
                "suffix": full[len(q):],
                "source": source,
                "score": round(sc, 2),
            })
        return out

    def suggest(
        self,
        prefix: str,
        user_id: Optional[int],
        mysql_dao,
        es_dao=None,
        limit: int = 8,
        skip_correct: bool = False,
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
                if hist.startswith(q):
                    push(hist, "history", 1.0 + (0.05 if len(hist) > len(q) else 0))

        tokens = self._query_tokens(q)

        for term, freq in self._prefix_hits.get(q, [])[:60]:
            push(term, "continuation", 0.88 + min(freq, 20) * 0.005)

        token_scored: List[Tuple[float, str]] = []
        for term in self._vocab:
            ts = self._token_match_score(term, tokens, q)
            if ts >= 60:
                token_scored.append((ts, term))
        token_scored.sort(key=lambda x: -x[0])
        for ts, term in token_scored[: limit * 3]:
            if term.startswith(q):
                push(term, "prefix", 0.9 + ts / 200.0)
            else:
                push(term, "token", 0.82 + ts / 250.0)

        for tok in tokens:
            if len(tok) < 1:
                continue
            for term, _ in self._prefix_hits.get(tok, [])[:25]:
                if term != q:
                    push(term, "token", 0.86)
            for text, sc in self._fuzzy_match(tok, limit * 2, min_score=_SUGGEST_TOKEN_FUZZY_MIN):
                if text not in seen:
                    push(text, "fuzzy", sc / 100.0 * 0.82)

        if len(out) < limit * 2:
            for text, sc in self._fuzzy_match(q, limit * 3, min_score=_SUGGEST_FUZZY_MIN):
                push(text, "fuzzy", sc / 100.0 * 0.8)

        if not skip_correct:
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
