"""Tests for process_cluster.py."""
from graphify.entry_points import EntryPoint
from graphify.processes import Process, ProcessStep
from graphify.process_cluster import (
    ProcessCluster,
    cluster_processes,
    deduplicate,
    merge_cluster,
)


def _make_step(node_id, depth):
    return ProcessStep(node_id=node_id, label=node_id, file=f"{node_id}.py", line=0, depth=depth)


def _make_process(name, steps, entry_file="a.py"):
    ep = EntryPoint(name=name, kind="CLI", file=entry_file, line=1, language="python")
    proc = Process(
        name=name, entry_point=ep, steps=list(steps),
        total_steps=len(steps),
        max_depth=max((s.depth for s in steps), default=0),
        language="python",
    )
    return proc


def test_process_cluster_dataclass():
    ep = EntryPoint(name="main", kind="CLI", file="a.py", line=1, language="python")
    canonical = Process(name="main", entry_point=ep, total_steps=3, max_depth=2, language="python")
    cluster = ProcessCluster(canonical=canonical, variants=[canonical], cohesion_score=0.95)
    assert cluster.canonical == canonical
    assert len(cluster.variants) == 1
    assert cluster.cohesion_score == 0.95


def test_cluster_processes_groups_similar_high_overlap():
    steps_a = [_make_step("A", 0), _make_step("B", 1), _make_step("C", 2), _make_step("D", 3)]
    steps_b = [_make_step("A", 0), _make_step("B", 1), _make_step("C", 2), _make_step("E", 3)]
    p1 = _make_process("p1", steps_a)
    p2 = _make_process("p2", steps_b)

    clusters = cluster_processes([p1, p2], overlap_threshold=0.5)
    assert len(clusters) == 1
    assert len(clusters[0].variants) == 2


def test_cluster_processes_keeps_dissimilar_separate():
    steps_a = [_make_step("A", 0), _make_step("B", 1)]
    steps_b = [_make_step("X", 0), _make_step("Y", 1), _make_step("Z", 2)]
    p1 = _make_process("p1", steps_a)
    p2 = _make_process("p2", steps_b)

    clusters = cluster_processes([p1, p2], overlap_threshold=0.9)
    assert len(clusters) == 2


def test_cluster_processes_empty_list():
    assert cluster_processes([]) == []


def test_deduplicate_keeps_deepest_variant():
    steps_shallow = [
        _make_step("A", 0), _make_step("B", 1), _make_step("C", 2), _make_step("D", 3),
        _make_step("E", 4), _make_step("F", 5), _make_step("G", 6), _make_step("H", 7),
        _make_step("I", 8),
    ]
    steps_deep = [
        _make_step("A", 0), _make_step("B", 1), _make_step("C", 2), _make_step("D", 3),
        _make_step("E", 4), _make_step("F", 5), _make_step("G", 6), _make_step("H", 7),
        _make_step("I", 8), _make_step("J", 9),
    ]
    p_shallow = _make_process("shallow", steps_shallow)
    p_deep = _make_process("deep", steps_deep)

    result = deduplicate([p_shallow, p_deep])
    assert len(result) == 1
    assert result[0].total_steps >= p_deep.total_steps


def test_deduplicate_empty_list():
    assert deduplicate([]) == []


def test_merge_cluster_produces_canonical_trace():
    steps_a = [_make_step("A", 0), _make_step("B", 1), _make_step("C", 2)]
    steps_b = [_make_step("A", 0), _make_step("B", 1), _make_step("D", 3)]
    p1 = _make_process("p1", steps_a)
    p2 = _make_process("p2", steps_b)

    cluster = ProcessCluster(canonical=p1, variants=[p1, p2])
    merged = merge_cluster(cluster)

    node_ids = {s.node_id for s in merged.steps}
    assert "A" in node_ids
    assert "B" in node_ids
    assert "C" in node_ids
    assert "D" in node_ids
    assert merged.total_steps == 4
    assert merged.confidence <= 1.0


def test_merge_cluster_single_variant_returns_canonical():
    steps = [_make_step("A", 0), _make_step("B", 1)]
    p = _make_process("p1", steps)
    cluster = ProcessCluster(canonical=p, variants=[p])
    merged = merge_cluster(cluster)
    assert merged.total_steps == 2


def test_cluster_processes_multiple_clusters():
    steps_group1_a = [_make_step("A", 0), _make_step("B", 1), _make_step("C", 2)]
    steps_group1_b = [_make_step("A", 0), _make_step("B", 1), _make_step("D", 2)]
    steps_group2_a = [_make_step("X", 0), _make_step("Y", 1), _make_step("W", 2)]
    steps_group2_b = [_make_step("X", 0), _make_step("Y", 1), _make_step("Z", 2)]

    p1 = _make_process("p1", steps_group1_a)
    p2 = _make_process("p2", steps_group1_b)
    p3 = _make_process("p3", steps_group2_a)
    p4 = _make_process("p4", steps_group2_b)

    clusters = cluster_processes([p1, p2, p3, p4], overlap_threshold=0.3)
    assert len(clusters) == 2
    for c in clusters:
        assert len(c.variants) == 2
