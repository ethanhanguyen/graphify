"""Tests for serve.py - MCP graph query helpers (no mcp package required)."""
import json
import pytest
import networkx as nx
from networkx.readwrite import json_graph

from graphify.serve import (
    _communities_from_graph,
    _score_nodes,
    _bfs,
    _dfs,
    _subgraph_to_text,
    _load_graph,
    _bidirectional_shortest_path,
    _dijkstra_shortest_path,
    _astar_search,
)


def _make_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node("n1", label="extract", source_file="extract.py", source_location="L10", community=0)
    G.add_node("n2", label="cluster", source_file="cluster.py", source_location="L5", community=0)
    G.add_node("n3", label="build", source_file="build.py", source_location="L1", community=1)
    G.add_node("n4", label="report", source_file="report.py", source_location="L1", community=1)
    G.add_node("n5", label="isolated", source_file="other.py", source_location="L1", community=2)
    G.add_edge("n1", "n2", relation="calls", confidence="INFERRED")
    G.add_edge("n2", "n3", relation="imports", confidence="EXTRACTED")
    G.add_edge("n3", "n4", relation="uses", confidence="EXTRACTED")
    return G


# --- _communities_from_graph ---

def test_communities_from_graph_basic():
    G = _make_graph()
    communities = _communities_from_graph(G)
    assert 0 in communities
    assert 1 in communities
    assert "n1" in communities[0]
    assert "n2" in communities[0]
    assert "n3" in communities[1]

def test_communities_from_graph_no_community_attr():
    G = nx.Graph()
    G.add_node("a", label="foo")  # no community attr
    communities = _communities_from_graph(G)
    assert communities == {}

def test_communities_from_graph_isolated():
    G = _make_graph()
    communities = _communities_from_graph(G)
    assert 2 in communities
    assert "n5" in communities[2]


# --- _score_nodes ---

def test_score_nodes_exact_label_match():
    G = _make_graph()
    scored = _score_nodes(G, ["extract"])
    nids = [nid for _, nid in scored]
    assert "n1" in nids
    assert scored[0][1] == "n1"  # highest score first

def test_score_nodes_no_match():
    G = _make_graph()
    scored = _score_nodes(G, ["xyzzy"])
    assert scored == []

def test_score_nodes_source_file_partial():
    G = _make_graph()
    # "cluster.py" contains "cluster" - should score 0.5 for source match
    scored = _score_nodes(G, ["cluster"])
    nids = [nid for _, nid in scored]
    assert "n2" in nids


# --- _bfs ---

def test_bfs_depth_1():
    G = _make_graph()
    visited, edges = _bfs(G, ["n1"], depth=1)
    assert "n1" in visited
    assert "n2" in visited  # direct neighbor
    assert "n3" not in visited  # 2 hops away

def test_bfs_depth_2():
    G = _make_graph()
    visited, edges = _bfs(G, ["n1"], depth=2)
    assert "n3" in visited  # n1 -> n2 -> n3

def test_bfs_disconnected():
    G = _make_graph()
    visited, edges = _bfs(G, ["n5"], depth=3)
    assert visited == {"n5"}  # isolated node

def test_bfs_returns_edges():
    G = _make_graph()
    visited, edges = _bfs(G, ["n1"], depth=1)
    assert len(edges) >= 1
    assert any(u == "n1" or v == "n1" for u, v in edges)


# --- _dfs ---

def test_dfs_depth_1():
    G = _make_graph()
    visited, edges = _dfs(G, ["n1"], depth=1)
    assert "n1" in visited
    assert "n2" in visited
    assert "n3" not in visited

def test_dfs_full_chain():
    G = _make_graph()
    visited, edges = _dfs(G, ["n1"], depth=5)
    assert {"n1", "n2", "n3", "n4"}.issubset(visited)


# --- _subgraph_to_text ---

def test_subgraph_to_text_contains_labels():
    G = _make_graph()
    text = _subgraph_to_text(G, {"n1", "n2"}, [("n1", "n2")])
    assert "extract" in text
    assert "cluster" in text

def test_subgraph_to_text_truncates():
    G = _make_graph()
    # Very small budget forces truncation
    text = _subgraph_to_text(G, {"n1", "n2", "n3", "n4"}, [("n1", "n2")], token_budget=1)
    assert "truncated" in text

def test_subgraph_to_text_edge_included():
    G = _make_graph()
    text = _subgraph_to_text(G, {"n1", "n2"}, [("n1", "n2")])
    assert "EDGE" in text
    assert "calls" in text


# --- _load_graph ---

def test_load_graph_roundtrip(tmp_path):
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))
    G2 = _load_graph(str(p))
    assert G2.number_of_nodes() == G.number_of_nodes()
    assert G2.number_of_edges() == G.number_of_edges()

def test_load_graph_missing_file(tmp_path):
    graphify_dir = tmp_path / "graphify-out"
    graphify_dir.mkdir()
    with pytest.raises(SystemExit):
        _load_graph(str(graphify_dir / "nonexistent.json"))


# --- _bidirectional_shortest_path ---

def test_bidirectional_shortest_path_direct():
    G = _make_graph()
    path, length = _bidirectional_shortest_path(G, "n1", "n2")
    assert path == ["n1", "n2"]
    assert length == 1.0


def test_bidirectional_shortest_path_two_hops():
    G = _make_graph()
    path, length = _bidirectional_shortest_path(G, "n1", "n3")
    assert path == ["n1", "n2", "n3"]
    assert length == 2.0


def test_bidirectional_no_path():
    G = _make_graph()
    G.add_node("n10", label="orphan")
    path, length = _bidirectional_shortest_path(G, "n1", "n10")
    assert path == []
    assert length == float("inf")


def test_bidirectional_max_hops_exceeded():
    G = _make_graph()
    path, length = _bidirectional_shortest_path(G, "n1", "n4", max_hops=1)
    assert path == []
    assert length == float("inf")


def test_bidirectional_same_node():
    G = _make_graph()
    path, length = _bidirectional_shortest_path(G, "n1", "n1")
    assert path == ["n1"]
    assert length == 0.0


def test_bidirectional_missing_node():
    G = _make_graph()
    path, length = _bidirectional_shortest_path(G, "n1", "zzz")
    assert path == []
    assert length == float("inf")


# --- _dijkstra_shortest_path ---

def test_dijkstra_with_weights():
    G = nx.Graph()
    G.add_node("a", label="A")
    G.add_node("b", label="B")
    G.add_node("c", label="C")
    G.add_edge("a", "b", weight=10.0)
    G.add_edge("b", "c", weight=1.0)
    G.add_edge("a", "c", weight=100.0)
    path, total = _dijkstra_shortest_path(G, "a", "c")
    assert path == ["a", "b", "c"]
    assert total == 11.0


def test_dijkstra_same_node():
    G = _make_graph()
    path, total = _dijkstra_shortest_path(G, "n1", "n1")
    assert path == ["n1"]
    assert total == 0.0


def test_dijkstra_no_path():
    G = _make_graph()
    G.add_node("orphan", label="orphan")
    path, total = _dijkstra_shortest_path(G, "n1", "orphan")
    assert path == []
    assert total == float("inf")


# --- _astar_search ---

def test_astar_with_communities():
    G = _make_graph()
    communities = _communities_from_graph(G)
    path = _astar_search(G, "n1", "n4", communities)
    assert len(path) >= 2
    assert path[0] == "n1"
    assert path[-1] == "n4"


def test_astar_stays_in_community():
    G = nx.Graph()
    G.add_node("a", label="A", community=0)
    G.add_node("b", label="B", community=0)
    G.add_node("c", label="C", community=1)
    G.add_edge("a", "b")
    G.add_edge("b", "c")
    communities = {0: ["a", "b"], 1: ["c"]}
    path = _astar_search(G, "a", "c", communities)
    assert path == ["a", "b", "c"]


def test_astar_same_node():
    G = _make_graph()
    communities = _communities_from_graph(G)
    path = _astar_search(G, "n1", "n1", communities)
    assert path == ["n1"]


def test_astar_no_path():
    G = _make_graph()
    G.add_node("orphan", label="orphan")
    communities = _communities_from_graph(G)
    path = _astar_search(G, "n1", "orphan", communities)
    assert path == []


# --- _score_nodes with label index ---

def test_score_nodes_with_label_index():
    G = _make_graph()
    from graphify.index import build_label_index
    G.graph["indexes"] = {"label_index": build_label_index(G)}
    scored = _score_nodes(G, ["extract"])
    nids = [nid for _, nid in scored]
    assert "n1" in nids


def test_score_nodes_index_no_matches():
    G = _make_graph()
    from graphify.index import build_label_index
    G.graph["indexes"] = {"label_index": build_label_index(G)}
    scored = _score_nodes(G, ["zzzzzz"])
    assert scored == []


# --- detect_changes tool response format ---

def test_detect_changes_tool_response():
    G = nx.Graph()
    G.add_node("n1", label="handle_root()", source_file="handlers.py",
               source_location="L10", node_type="FUNCTION")
    G.add_node("n2", label="do_auth()", source_file="auth.py",
               source_location="L20", node_type="FUNCTION")
    G.add_node("n3", label="query_db()", source_file="db.py",
               source_location="L30", node_type="FUNCTION")
    G.add_node("n4", label="main()", source_file="main.py",
               source_location="L1", node_type="FUNCTION")
    G.add_edge("n1", "n2", relation="calls", confidence="EXTRACTED",
               confidence_score=1.0)
    G.add_edge("n2", "n3", relation="calls", confidence="EXTRACTED",
               confidence_score=1.0)
    G.add_edge("n1", "n4", relation="handles_route", confidence="EXTRACTED",
               route="/api")

    from graphify.processes import build_processes, detect_changes
    procs = build_processes(G)
    result = detect_changes(G, procs, changed_files=["auth.py"])
    assert "summary" in result
    assert "changed_symbols" in result
    assert "affected_processes" in result
    assert "recommendations" in result
    assert result["summary"]["risk_level"] in ("LOW", "MEDIUM", "HIGH")
    assert result["summary"]["changed_count"] == 1
