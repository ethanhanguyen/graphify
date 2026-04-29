import networkx as nx
from graphify.matviews import (
    compute_transitive_closure,
    write_materialized_view,
    load_materialized_view,
    check_materialized_path,
)


def _make_call_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node("a", label="A")
    G.add_node("b", label="B")
    G.add_node("c", label="C")
    G.add_node("d", label="D")
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    G.add_edge("b", "c", relation="calls", confidence="EXTRACTED")
    G.add_edge("c", "d", relation="calls", confidence="EXTRACTED")
    G.add_edge("a", "d", relation="imports", confidence="INFERRED")
    return G


def test_compute_transitive_closure_calls():
    G = _make_call_graph()
    closure = compute_transitive_closure(G, "calls")
    assert ("a", "b") in closure
    assert closure[("a", "b")] == 1
    assert ("a", "c") in closure
    assert closure[("a", "c")] == 2
    assert ("a", "d") in closure
    assert closure[("a", "d")] == 3


def test_compute_transitive_closure_empty_relation():
    G = _make_call_graph()
    closure = compute_transitive_closure(G, "nonexistent")
    assert closure == {}


def test_write_and_load_materialized_view(tmp_path):
    G = _make_call_graph()
    closure = compute_transitive_closure(G, "calls")
    out_dir = tmp_path / "matviews"
    write_materialized_view(closure, "calls", out_dir)
    assert (out_dir / "calls.edges").exists()
    loaded = load_materialized_view("calls", out_dir)
    assert loaded is not None
    assert len(loaded) == len(closure)
    assert loaded[("a", "c")] == 2


def test_load_materialized_view_not_found(tmp_path):
    result = load_materialized_view("missing", tmp_path / "matviews")
    assert result is None


def test_check_materialized_path_found(tmp_path):
    G = _make_call_graph()
    closure = compute_transitive_closure(G, "calls")
    out_dir = tmp_path / "matviews"
    write_materialized_view(closure, "calls", out_dir)
    distance = check_materialized_path(G, "a", "d", "calls", out_dir)
    assert distance == 3


def test_check_materialized_path_not_found(tmp_path):
    G = _make_call_graph()
    closure = compute_transitive_closure(G, "calls")
    out_dir = tmp_path / "matviews"
    write_materialized_view(closure, "calls", out_dir)
    G.add_node("z", label="Z")
    distance = check_materialized_path(G, "a", "z", "calls", out_dir)
    assert distance is None


def test_check_materialized_path_same_node(tmp_path):
    G = _make_call_graph()
    closure = compute_transitive_closure(G, "calls")
    out_dir = tmp_path / "matviews"
    write_materialized_view(closure, "calls", out_dir)
    distance = check_materialized_path(G, "a", "a", "calls", out_dir)
    assert distance == 0


def test_check_materialized_path_no_matviews_dir():
    G = _make_call_graph()
    from pathlib import Path
    distance = check_materialized_path(G, "a", "b", "calls", Path("/nonexistent_matviews"))
    assert distance is None
