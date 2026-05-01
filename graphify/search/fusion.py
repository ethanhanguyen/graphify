from __future__ import annotations

from collections import defaultdict


def reciprocal_rank_fusion(*ranked_lists: list[tuple], k: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = defaultdict(float)
    for ranked in ranked_lists:
        for rank, (nid, _) in enumerate(ranked):
            scores[nid] += 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])


def merge_ranked_lists(lists: list[list[tuple]], k: int = 60) -> list[tuple]:
    return reciprocal_rank_fusion(*lists, k=k)
