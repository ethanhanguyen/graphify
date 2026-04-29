"""Hybrid search orchestrator — BM25 + semantic embeddings + RRF fusion."""
from __future__ import annotations

from .bm25 import BM25Index
from .embeddings import search_by_embedding
from .fusion import reciprocal_rank_fusion


def hybrid_search(
    G,
    query: str,
    bm25_index: BM25Index,
    embeddings: dict[str, list[float]],
    processes: list | None = None,
    top_k: int = 20,
) -> list[tuple[str, float]]:
    bm25_results = bm25_index.search(query, top_k=top_k)

    emb_results = search_by_embedding(query, embeddings, top_k=top_k)

    merged = reciprocal_rank_fusion([bm25_results, emb_results], k=60)

    return merged
