"""Reciprocal Rank Fusion — merges multiple ranked result lists by rank, not score."""
from __future__ import annotations


def normalize_ranks(results: list[tuple[str, float]]) -> dict[str, int]:
    return {doc_id: rank + 1 for rank, (doc_id, _) in enumerate(results)}


def reciprocal_rank_fusion(
    result_sets: list[list[tuple[str, float]]],
    k: int = 60,
) -> list[tuple[str, float]]:
    """Merge multiple ranked result lists via Reciprocal Rank Fusion.

    RRF_score(doc) = sum over result_sets: 1 / (k + rank_in_list)

    Merges by rank, not score — avoids calibration issues between
    BM25 and vector scorers which use different scales.

    Each result_set is [(doc_id, score), ...] sorted by relevance.
    Returns merged [(doc_id, rrf_score), ...] sorted descending.
    """
    rrf_scores: dict[str, float] = {}
    for results in result_sets:
        for rank, (doc_id, _) in enumerate(results):
            rrf = 1.0 / (k + rank + 1)
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + rrf
    if not rrf_scores:
        return []
    return sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
