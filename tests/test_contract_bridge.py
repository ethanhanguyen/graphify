"""Tests for graphify/contract_bridge.py."""
import json
import pytest
from pathlib import Path
from graphify.contract_bridge import (
    detect_shared_interfaces,
    bridge_report,
    _load_graph,
    _node_signature,
    _normalize_signature,
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


class TestNodeSignature:
    def test_basic(self):
        sig = _node_signature({"label": "MyFunc", "file_type": "code", "language": "python"})
        assert "MyFunc" in sig
        assert "code" in sig
        assert "python" in sig

    def test_missing_fields(self):
        sig = _node_signature({"label": "X"})
        assert sig.startswith("X")


class TestNormalizeSignature:
    def test_lowercase(self):
        assert _normalize_signature("MyFunc::code::python") == "myfunc_code_python"

    def test_empty(self):
        assert _normalize_signature("") == ""


class TestDetectSharedInterfaces:
    def test_shared_found(self, tmp_path):
        r1 = tmp_path / "repo1" / "graphify-out"
        r2 = tmp_path / "repo2" / "graphify-out"
        _make_graph(r1 / "graph.json", [
            {"id": "n1", "label": "UserService", "file_type": "code", "language": "typescript"},
            {"id": "n2", "label": "AuthHandler", "file_type": "code", "language": "typescript"},
        ])
        _make_graph(r2 / "graph.json", [
            {"id": "n3", "label": "UserService", "file_type": "code", "language": "typescript"},
            {"id": "n4", "label": "Logger", "file_type": "code", "language": "typescript"},
        ])
        results = detect_shared_interfaces([str(r1 / "graph.json"), str(r2 / "graph.json")])
        assert len(results) == 1
        assert results[0]["shared_count"] >= 1

    def test_no_shared(self, tmp_path):
        r1 = tmp_path / "repo1" / "graphify-out"
        r2 = tmp_path / "repo2" / "graphify-out"
        _make_graph(r1 / "graph.json", [
            {"id": "n1", "label": "Alpha", "file_type": "code", "language": "python"},
        ])
        _make_graph(r2 / "graph.json", [
            {"id": "n2", "label": "Beta", "file_type": "code", "language": "go"},
        ])
        results = detect_shared_interfaces([str(r1 / "graph.json"), str(r2 / "graph.json")])
        assert len(results) == 0

    def test_missing_graph(self, tmp_path):
        results = detect_shared_interfaces([str(tmp_path / "nonexistent.json")])
        assert results == []

    def test_single_repo(self, tmp_path):
        r1 = tmp_path / "repo1" / "graphify-out"
        _make_graph(r1 / "graph.json", [
            {"id": "n1", "label": "Foo", "file_type": "code", "language": "python"},
        ])
        results = detect_shared_interfaces([str(r1 / "graph.json")])
        assert results == []

    def test_three_repos(self, tmp_path):
        r1 = tmp_path / "r1" / "graphify-out"
        r2 = tmp_path / "r2" / "graphify-out"
        r3 = tmp_path / "r3" / "graphify-out"
        _make_graph(r1 / "graph.json", [
            {"id": "n1", "label": "SharedUtil", "file_type": "code", "language": "python"},
        ])
        _make_graph(r2 / "graph.json", [
            {"id": "n2", "label": "SharedUtil", "file_type": "code", "language": "python"},
        ])
        _make_graph(r3 / "graph.json", [
            {"id": "n3", "label": "SharedUtil", "file_type": "code", "language": "python"},
        ])
        results = detect_shared_interfaces([
            str(r1 / "graph.json"),
            str(r2 / "graph.json"),
            str(r3 / "graph.json"),
        ])
        assert len(results) >= 3


class TestBridgeReport:
    def test_report_with_results(self, tmp_path):
        r1 = tmp_path / "r1" / "graphify-out"
        r2 = tmp_path / "r2" / "graphify-out"
        _make_graph(r1 / "graph.json", [
            {"id": "n1", "label": "SharedInterface", "file_type": "code", "language": "java"},
        ])
        _make_graph(r2 / "graph.json", [
            {"id": "n2", "label": "SharedInterface", "file_type": "code", "language": "java"},
        ])
        report = bridge_report([str(r1 / "graph.json"), str(r2 / "graph.json")])
        assert "Contract Bridge Report" in report

    def test_report_empty(self, tmp_path):
        report = bridge_report([])
        assert "No shared interfaces" in report


class TestLoadGraph:
    def test_load_valid(self, tmp_path):
        r = tmp_path / "repo" / "graphify-out"
        _make_graph(r / "graph.json", [{"id": "n1", "label": "Test"}])
        G = _load_graph(str(r / "graph.json"))
        assert G is not None
        assert G.number_of_nodes() == 1

    def test_load_missing(self, tmp_path):
        assert _load_graph(str(tmp_path / "missing.json")) is None

    def test_load_corrupt(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json")
        assert _load_graph(str(p)) is None
