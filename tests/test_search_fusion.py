from graphify.search.fusion import reciprocal_rank_fusion, merge_ranked_lists


def test_rrf_two_simple_lists():
    a = [("n1", 0.9), ("n2", 0.7)]
    b = [("n2", 0.8), ("n3", 0.6)]
    fused = reciprocal_rank_fusion(a, b, k=60)
    assert len(fused) == 3
    assert fused[0][0] == "n2"


def test_rrf_formula_correctness():
    a = [("n1", 0.9)]
    b = [("n1", 0.7)]
    k = 60
    fused = reciprocal_rank_fusion(a, b, k=k)
    expected_score = 1.0 / (k + 0 + 1) + 1.0 / (k + 0 + 1)
    assert len(fused) == 1
    assert fused[0][0] == "n1"
    assert abs(fused[0][1] - expected_score) < 1e-9


def test_rrf_different_k_values():
    a = [("n1", 1.0), ("n2", 0.5)]
    b = [("n2", 1.0)]
    for k in [10, 60, 100]:
        fused = reciprocal_rank_fusion(a, b, k=k)
        score_n2 = 1.0 / (k + 0 + 1) + 1.0 / (k + 1 + 1)
        assert len(fused) == 2
        assert abs(fused[0][1] - score_n2) < 1e-9


def test_rrf_handles_empty_lists():
    a = [("n1", 0.9)]
    b: list = []
    fused = reciprocal_rank_fusion(a, b, k=60)
    assert len(fused) == 1
    assert fused[0][0] == "n1"


def test_rrf_all_empty():
    fused = reciprocal_rank_fusion([], [], k=60)
    assert fused == []


def test_rrf_same_rank_same_lists_are_tied():
    a = [("n1", 0.9), ("n2", 0.5)]
    b = [("n2", 0.9), ("n1", 0.5)]
    fused = reciprocal_rank_fusion(a, b, k=60)
    scores = dict(fused)
    assert abs(scores["n1"] - scores["n2"]) < 1e-9


def test_merge_ranked_lists():
    a = [("n1", 0.9)]
    b = [("n2", 0.8)]
    merged = merge_ranked_lists([a, b], k=60)
    assert len(merged) == 2
    ids = {r[0] for r in merged}
    assert ids == {"n1", "n2"}


def test_rrf_ignores_original_scores():
    a = [("n1", 0.9)]
    b = [("n1", 0.1)]
    fused = reciprocal_rank_fusion(a, b, k=60)
    assert len(fused) == 1
    assert fused[0][1] == 1.0 / 61 + 1.0 / 61
