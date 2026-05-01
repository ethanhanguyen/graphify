"""Tests for graphify/group_search.py."""
import json
import pytest
from pathlib import Path
from graphify.group_search import (
    group_search,
    group_search_text,
    _rrf_score,
    _fan_out,
    _query_single_repo,
)


def _make_graph(path: Path, nodes: list[dict], edges: list[dict] | None = None) -> Path:
    from networkx.readwrite import json_graph as _jg
    import networkx as nx
    G = nx.Graph()
    for n in nodes:
        G.add_node(n["id"], **{k: v for k, v in n.items() if k != "id"})
    for e in (edges or []):
        G.add_edge(e["source"], e["target"])
    data = _jg.node_link_data(G, edges="links")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


class TestRRFScore:
    def test_rank1(self):
        s = _rrf_score(1, k=60)
        assert s > 0
        assert s == 1.0 / 61

    def test_decreasing(self):
        s1 = _rrf_score(1)
        s2 = _rrf_score(10)
        assert s1 > s2


class TestFanOut:
    def test_fan_out_two_repos(self, tmp_path):
        r1 = tmp_path / "r1" / "graphify-out"
        r2 = tmp_path / "r2" / "graphify-out"
        _make_graph(r1 / "graph.json", [
            {"id": "n1", "label": "AuthService", "source_file": "auth.py", "file_type": "code"},
        ])
        _make_graph(r2 / "graph.json", [
            {"id": "n2", "label": "AuthService", "source_file": "auth.ts", "file_type": "code"},
        ])
        results = _fan_out("auth", [str(r1 / "graph.json"), str(r2 / "graph.json")])
        assert len(results) == 2
        for path, items in results:
            assert len(items) > 0

    def test_fan_out_missing_repo(self, tmp_path):
        results = _fan_out("test", [str(tmp_path / "missing.json")])
        assert len(results) == 1
        assert results[0][1] == []


class TestQuerySingleRepo:
    def test_query_with_terms(self, tmp_path):
        r = tmp_path / "repo" / "graphify-out"
        _make_graph(r / "graph.json", [
            {"id": "n1", "label": "UserHandler", "source_file": "user.py", "file_type": "code"},
            {"id": "n2", "label": "Config", "source_file": "config.py", "file_type": "code"},
        ])
        results = _query_single_repo(str(r / "graph.json"), "user", {})
        assert len(results) > 0

    def test_query_missing_graph(self, tmp_path):
        results = _query_single_repo(str(tmp_path / "nope.json"), "test", {})
        assert results == []

    def test_query_limit(self, tmp_path):
        r = tmp_path / "repo" / "graphify-out"
        _make_graph(r / "graph.json", [
            {"id": f"n{i}", "label": f"Item{i}", "source_file": f"f{i}.py", "file_type": "code"}
            for i in range(20)
        ])
        results = _query_single_repo(str(r / "graph.json"), "Item", {"limit": 5})
        assert len(results) <= 5


class TestGroupSearch:
    def test_merges_results(self, tmp_path):
        r1 = tmp_path / "r1" / "graphify-out"
        r2 = tmp_path / "r2" / "graphify-out"
        _make_graph(r1 / "graph.json", [
            {"id": "n1", "label": "UserService", "source_file": "user.py", "file_type": "code"},
        ])
        _make_graph(r2 / "graph.json", [
            {"id": "n2", "label": "UserService", "source_file": "user.ts", "file_type": "code"},
        ])
        result = group_search("user", [str(r1 / "graph.json"), str(r2 / "graph.json")])
        assert result["repos_searched"] == 2
        assert result["total_results"] > 0

    def test_empty_search(self, tmp_path):
        result = group_search("zzz_nonexistent", [])
        assert result["repos_searched"] == 0
        assert result["total_results"] == 0

    def test_limit_option(self, tmp_path):
        r1 = tmp_path / "r1" / "graphify-out"
        _make_graph(r1 / "graph.json", [
            {"id": f"n{i}", "label": f"Item{i}", "source_file": f"f{i}.py", "file_type": "code"}
            for i in range(15)
        ])
        result = group_search("Item", [str(r1 / "graph.json")], {"limit": 3})
        assert len(result["results"]) <= 3

    def test_multi_repo_merge_with_same_name(self, tmp_path):
        r1 = tmp_path / "r1" / "graphify-out"
        r2 = tmp_path / "r2" / "graphify-out"
        _make_graph(r1 / "graph.json", [
            {"id": "n1", "label": "SharedClass", "source_file": "lib.ts", "file_type": "code"},
        ])
        _make_graph(r2 / "graph.json", [
            {"id": "n2", "label": "SharedClass", "source_file": "lib.ts", "file_type": "code"},
        ])
        result = group_search("shared", [str(r1 / "graph.json"), str(r2 / "graph.json")])
        assert result["total_results"] >= 1
        for r in result["results"]:
            if r["name"] == "SharedClass":
                assert len(r["repos"]) >= 1

    def test_with_options(self, tmp_path):
        r1 = tmp_path / "r1" / "graphify-out"
        _make_graph(r1 / "graph.json", [
            {"id": "n1", "label": "AlphaBeta", "source_file": "a.py", "file_type": "code"},
        ])
        result = group_search("alpha", [str(r1 / "graph.json")], {"limit": 5, "extra": "ignored"})
        assert result["repos_searched"] == 1


class TestGroupSearchText:
    def test_output_format(self, tmp_path):
        r1 = tmp_path / "r1" / "graphify-out"
        _make_graph(r1 / "graph.json", [
            {"id": "n1", "label": "Alpha", "source_file": "a.py", "file_type": "code"},
        ])
        text = group_search_text("alpha", [str(r1 / "graph.json")])
        assert "Cross-repo search" in text
        assert "Alpha" in text
