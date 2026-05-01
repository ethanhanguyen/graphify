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
    _find_node,
    _bidirectional_shortest_path,
    _weighted_dijkstra,
    _astar,
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


class TestFindNodeRanked:
    def _make_graph(self):
        G = nx.Graph()
        G.graph["schema_version"] = 2
        G.add_node("n1", label="uri.ts", source_file="src/vs/base/common/uri.ts", source_location="L1")
        G.add_node("n2", label="uri.ts", source_file="extensions/terminal-suggest/src/helpers/uri.ts", source_location="L1")
        G.add_node("n3", label="uri.ts", source_file="extensions/copilot/src/deep/uri.ts", source_location="L1")
        for i, n in enumerate(["n1", "n2", "n3"], 1):
            for _ in range(i):
                G.add_node(f"nb_{n}_{_}", label=f"neighbor_{_}")
                G.add_edge(n, f"nb_{n}_{_}", relation="imports")
        return G

    def test_exact_label_match_ranks_first(self):
        G = nx.Graph()
        G.add_node("a", label="uri.ts", source_file="src/vs/uri.ts")
        G.add_node("b", label="UriHelper.ts", source_file="ext/helper.ts")
        result = _find_node(G, "uri.ts")
        assert result[0] == "a"

    def test_shorter_path_beats_deeper(self):
        G = nx.Graph()
        G.add_node("a", label="event.ts", source_file="src/vs/base/common/event.ts")
        G.add_node("b", label="event.ts", source_file="extensions/a/b/c/d/e/event.ts")
        result = _find_node(G, "event.ts")
        assert result[0] == "a"

    def test_higher_degree_beats_lower_for_same_depth(self):
        G = nx.Graph()
        G.add_node("a", label="foo.ts", source_file="src/foo.ts")
        G.add_node("b", label="foo.ts", source_file="lib/foo.ts")
        for _ in range(5):
            G.add_node(f"nb_{_}", label="x")
            G.add_edge("a", f"nb_{_}", relation="imports")
        G.add_edge("b", "nb_0", relation="imports")
        result = _find_node(G, "foo.ts")
        assert result[0] == "a"

    def test_no_match_returns_empty(self):
        G = nx.Graph()
        G.add_node("a", label="alpha")
        result = _find_node(G, "nonexistent")
        assert result == []

    def test_diacritic_insensitive(self):
        G = nx.Graph()
        G.add_node("a", label="café.ts")
        result = _find_node(G, "cafe")
        assert result[0] == "a"

    def test_exact_match_beats_substring(self):
        G = nx.Graph()
        G.add_node("b", label="sessionRequestLifecycle.ts", source_file="src/sessionRequestLifecycle.ts")
        G.add_node("a", label="lifecycle.ts", source_file="src/vs/base/common/lifecycle.ts")
        result = _find_node(G, "lifecycle.ts")
        assert result[0] == "a"

    def test_fname_match_boosts_score(self):
        G = nx.Graph()
        G.add_node("b", label="HelperClass", source_file="extensions/deep/nested/event.ts")
        G.add_node("a", label="OtherClass", source_file="src/vs/base/common/event.ts")
        result = _find_node(G, "event.ts")
        assert result[0] == "a"

    def test_vscode_like_scenario(self):
        G = self._make_graph()
        result = _find_node(G, "uri.ts")
        assert result[0] == "n1"

    def test_tiebreaker_shorter_id_wins(self):
        G = nx.Graph()
        G.add_node("longer_nid_here", label="app.ts", source_file="src/app.ts")
        G.add_node("short", label="app.ts", source_file="src/app.ts")
        result = _find_node(G, "app.ts")
        assert result[0] == "short"


class TestPathAlgorithms:
    def _make_path_graph(self):
        G = nx.Graph()
        G.add_node("a", label="A", source_file="src/a.ts", community=1)
        G.add_node("b", label="B", source_file="src/b.ts", community=1)
        G.add_node("c", label="C", source_file="src/c.ts", community=2)
        G.add_node("d", label="D", source_file="src/d.ts", community=2)
        G.add_edge("a", "b", relation="CALLS", confidence="EXTRACTED", confidence_score=1.0)
        G.add_edge("b", "c", relation="CALLS", confidence="INFERRED", confidence_score=0.5)
        G.add_edge("c", "d", relation="CALLS", confidence="EXTRACTED", confidence_score=1.0)
        return G

    def test_bidirectional_finds_path(self):
        G = self._make_path_graph()
        path, hops = _bidirectional_shortest_path(G, "a", "d")
        assert len(path) == 4
        assert hops == 3

    def test_bidirectional_no_path(self):
        G = nx.Graph()
        G.add_node("a", label="A")
        G.add_node("b", label="B")
        path, hops = _bidirectional_shortest_path(G, "a", "b")
        assert path == []
        assert hops == -1

    def test_bidirectional_max_hops(self):
        G = self._make_path_graph()
        path, hops = _bidirectional_shortest_path(G, "a", "d", max_hops=1)
        assert hops == -1

    def test_dijkstra_finds_path(self):
        G = self._make_path_graph()
        path, score = _weighted_dijkstra(G, "a", "d")
        assert len(path) == 4
        assert score > 0

    def test_dijkstra_no_path(self):
        G = nx.Graph()
        G.add_node("a", label="A")
        G.add_node("b", label="B")
        path, score = _weighted_dijkstra(G, "a", "b")
        assert path == []
        assert score == -1.0

    def test_astar_finds_path(self):
        G = self._make_path_graph()
        path, hops = _astar(G, "a", "d")
        assert len(path) == 4
        assert hops == 3

    def test_astar_same_node(self):
        G = self._make_path_graph()
        path, hops = _astar(G, "a", "a")
        assert path == ["a"]
        assert hops == 0

    def test_astar_no_path(self):
        G = nx.Graph()
        G.add_node("a", label="A")
        G.add_node("b", label="B")
        path, hops = _astar(G, "a", "b")
        assert hops == -1
