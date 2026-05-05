"""Search profile helpers for Chaeshin retrieve.

User-facing callers should be able to pass only the raw request.  Explicit
keywords stay explicit; an empty keyword list is not auto-filled.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Iterable, List, Sequence, Set

from chaeshin.schema import ProblemFeatures


_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+\-/#]*|[가-힣][가-힣A-Za-z0-9_.+\-/#]*")
_TRIM_RE = re.compile(r"^[^\w가-힣]+|[^\w가-힣]+$")

_STOPWORDS: Set[str] = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "into",
    "about",
    "please",
    "해야",
    "하고",
    "하는",
    "하면",
    "해서",
    "되어",
    "되게",
    "되게끔",
    "있음",
    "없는",
    "같은",
    "관련",
    "대한",
    "위한",
    "으로",
    "에서",
    "에게",
    "까지",
    "부터",
    "그리고",
    "또는",
    "이런",
    "저런",
    "해줘",
    "해주세요",
    "만들어",
    "만들기",
}


def normalize_token(value: Any) -> str:
    """Normalize a token for matching, not for display."""
    text = _TRIM_RE.sub("", str(value or "").strip()).lower()
    return text


def infer_keywords(text: str, max_keywords: int = 12) -> List[str]:
    """Tokenize natural-language text for internal lexical matching."""
    out: List[str] = []
    seen: Set[str] = set()

    for raw in _TOKEN_RE.findall(text or ""):
        token = _TRIM_RE.sub("", raw.strip())
        norm = normalize_token(token)
        if not norm or norm in _STOPWORDS:
            continue
        if len(norm) < 2 and not any(ch.isdigit() for ch in norm):
            continue
        if norm in seen:
            continue
        seen.add(norm)
        out.append(token)
        if len(out) >= max_keywords:
            break

    return out


def normalize_keywords(keywords: Sequence[Any] | str | None) -> List[str]:
    """Accept list or comma-separated string keywords and return clean values."""
    if keywords is None:
        return []
    if isinstance(keywords, str):
        parts: Iterable[Any] = keywords.split(",")
    else:
        parts = keywords

    out: List[str] = []
    seen: Set[str] = set()
    for part in parts:
        token = _TRIM_RE.sub("", str(part or "").strip())
        norm = normalize_token(token)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(token)
    return out


def build_search_problem(problem: ProblemFeatures) -> ProblemFeatures:
    """Return a retrieve-ready ProblemFeatures object.

    Explicit keywords remain authoritative.  If the caller omitted them, the
    list stays empty and the raw request is used as the primary search input.
    """
    explicit_keywords = normalize_keywords(problem.keywords)
    return replace(problem, keywords=explicit_keywords)


def problem_to_search_text(problem: ProblemFeatures) -> str:
    """Build text used for dense retrieval."""
    parts: List[str] = [
        problem.request,
        problem.category,
        " ".join(problem.keywords),
        " ".join(problem.constraints),
    ]
    parts.extend(_flatten_context(problem.context))
    return " ".join(p for p in parts if p).strip()


def problem_tokens(problem: ProblemFeatures) -> Set[str]:
    """Token set used for lexical retrieval."""
    values: List[str] = [
        problem.request,
        problem.category,
        " ".join(problem.keywords),
        " ".join(problem.constraints),
    ]
    values.extend(_flatten_context(problem.context, max_items=20))
    tokens = infer_keywords(" ".join(values), max_keywords=64)
    return {normalize_token(t) for t in tokens if normalize_token(t)}


def lexical_similarity(query: ProblemFeatures, candidate: ProblemFeatures) -> float:
    """Score keyword/request/category overlap on a 0..1 scale."""
    q_tokens = problem_tokens(query)
    c_tokens = problem_tokens(candidate)

    token_score = 0.0
    if q_tokens and c_tokens:
        intersection = q_tokens & c_tokens
        union = q_tokens | c_tokens
        jaccard = len(intersection) / len(union) if union else 0.0
        coverage = len(intersection) / len(q_tokens)
        token_score = max(jaccard, coverage * 0.75)

    category_score = 0.0
    q_category = normalize_token(query.category)
    c_category = normalize_token(candidate.category)
    if q_category and c_category:
        if q_category == c_category:
            category_score = 1.0
        else:
            q_cat_tokens = set(infer_keywords(query.category))
            c_cat_tokens = set(infer_keywords(candidate.category))
            if q_cat_tokens and q_cat_tokens & c_cat_tokens:
                category_score = 0.5

    return min(1.0, token_score * 0.75 + category_score * 0.25)


def _flatten_context(context: dict[str, Any], max_items: int = 40) -> List[str]:
    out: List[str] = []

    def visit(value: Any, depth: int = 0) -> None:
        if len(out) >= max_items or depth > 2 or value is None:
            return
        if isinstance(value, (str, int, float, bool)):
            out.append(str(value))
            return
        if isinstance(value, dict):
            for k, v in value.items():
                if len(out) >= max_items:
                    break
                out.append(str(k))
                visit(v, depth + 1)
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                if len(out) >= max_items:
                    break
                visit(item, depth + 1)

    visit(context or {})
    return out[:max_items]
