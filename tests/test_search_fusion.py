import pytest
from graphify.search.fusion import normalize_ranks, reciprocal_rank_fusion


def test_normalize_ranks():
    results = [("doc1", 0.9), ("doc2", 0.7), ("doc3", 0.3)]
    ranks = normalize_ranks(results)
    assert ranks == {"doc1": 1, "doc2": 2, "doc3": 3}


def test_normalize_ranks_empty():
    ranks = normalize_ranks([])
    assert ranks == {}


def test_rrf_merges_rankings():
    bm25 = [("a", 0.9), ("b", 0.7), ("c", 0.3)]
    semantic = [("b", 0.8), ("d", 0.6), ("a", 0.2)]

    merged = reciprocal_rank_fusion([bm25, semantic], k=60)

    assert len(merged) == 4
    scores = {doc: score for doc, score in merged}
    assert "a" in scores
    assert "b" in scores
    assert "c" in scores


def test_rrf_empty_input():
    merged = reciprocal_rank_fusion([], k=60)
    assert merged == []


def test_rrf_empty_lists():
    merged = reciprocal_rank_fusion([[], []], k=60)
    assert merged == []


def test_rrf_single_list():
    results = [("a", 0.9), ("b", 0.7), ("c", 0.3)]
    merged = reciprocal_rank_fusion([results], k=60)
    assert len(merged) == 3
    assert merged[0][0] == "a"
    assert round(merged[0][1], 10) == round(1 / 61, 10)


def test_rrf_rank_based_not_score_based():
    bm25 = [("a", 100.0), ("b", 0.1)]
    semantic = [("b", 0.1), ("a", 100.0)]

    merged = reciprocal_rank_fusion([bm25, semantic], k=60)
    assert len(merged) == 2
    assert merged[0][0] == "a"


def test_rrf_custom_k():
    bm25 = [("a", 1.0)]
    merged = reciprocal_rank_fusion([bm25], k=10)
    assert abs(merged[0][1] - 1 / 11) < 1e-9
