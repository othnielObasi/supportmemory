from __future__ import annotations

import re
from typing import Iterable, List, Sequence, Set

from app.services.embedding_service import cosine_similarity

_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "for", "in", "on", "at", "by", "with",
    "is", "are", "was", "were", "be", "been", "being", "this", "that", "these", "those",
    "it", "its", "as", "from", "into", "about", "can", "we", "you", "your", "our",
    "when", "what", "how", "why", "which", "who", "whom", "do", "does", "did",
}


def tokenize(text: str) -> List[str]:
    cleaned = (text or "").lower().replace("_", " ").replace("-", " ")
    tokens = re.findall(r"[a-z0-9\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]{2,}", cleaned)
    return [t for t in tokens if t not in _STOPWORDS]


def bigrams(tokens: Sequence[str]) -> Set[str]:
    return {f"{tokens[i]} {tokens[i + 1]}" for i in range(len(tokens) - 1)}


def coverage_score(query_terms: Sequence[str], doc_terms: Set[str]) -> float:
    """Fraction of query terms present in the document (better than Jaccard for asymmetric lengths)."""
    if not query_terms:
        return 0.0
    hits = sum(1 for term in query_terms if term in doc_terms)
    return hits / len(query_terms)


def phrase_score(query_text: str, doc_text: str, query_terms: Sequence[str]) -> float:
    q = (query_text or "").lower()
    d = (doc_text or "").lower()
    score = 0.0
    # Multi-word phrases from the query
    q_tokens = tokenize(q)
    for gram in bigrams(q_tokens):
        if gram in d:
            score += 0.12
    # Important content words as substrings (helps PDF OCR noise)
    for term in query_terms:
        if len(term) >= 4 and term in d:
            score += 0.03
    return min(0.45, score)


def title_tag_boost(query_terms: Sequence[str], title: str = "", tags: Iterable[str] | None = None) -> float:
    blob = f"{title or ''} {' '.join(tags or [])}".lower()
    if not blob or not query_terms:
        return 0.0
    hits = sum(1 for term in query_terms if term in blob)
    return min(0.25, 0.08 * hits)


def rank_score(
    *,
    query: str,
    document_text: str,
    query_embedding: List[float],
    doc_embedding: List[float],
    title: str = "",
    tags: Iterable[str] | None = None,
    extra_boost: float = 0.0,
    hash_embeddings: bool = True,
) -> float:
    """Hybrid ranker tuned for SupportMemory KB/lesson retrieval.

    Hash embeddings are noisy, so keyword/coverage dominates when hash_embeddings=True.
    With real embeddings (Qwen/OpenAI), vector weight increases.
    """
    query_terms = tokenize(query)
    doc_terms = set(tokenize(document_text))
    cov = coverage_score(query_terms, doc_terms)
    phrases = phrase_score(query, document_text, query_terms)
    title_boost = title_tag_boost(query_terms, title=title, tags=tags)
    vector = cosine_similarity(query_embedding, doc_embedding)

    if hash_embeddings:
        # Emphasize lexical match; keep a little vector signal
        score = 0.20 * vector + 0.45 * cov + 0.25 * phrases + title_boost + extra_boost
    else:
        score = 0.55 * vector + 0.25 * cov + 0.15 * phrases + title_boost + extra_boost

    return min(1.0, max(0.0, score))
