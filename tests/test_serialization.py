from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path
from unittest.mock import patch

import networkx as nx
import pytest

from graphify.serve import _load_graph_file
from graphify.export import to_json


MIN_GRAPH_DATA = {
    "nodes": [
        {"id": "a", "label": "Alpha", "source_file": "src/a.py", "source_location": "L1", "node_type": "FILE"},
        {"id": "b", "label": "Beta", "source_file": "src/b.py", "source_location": "L1", "node_type": "FILE"},
    ],
    "links": [
        {"source": "a", "target": "b", "relation": "imports", "confidence": "EXTRACTED", "confidence_score": 1.0, "weight": 1.0, "source_file": "src/a.py", "source_location": "L2"},
    ],
    "directed": False,
    "multigraph": False,
    "graph": {"schema_version": 2},
}


def _build_test_graph(extra_attrs: dict | None = None):
    G = nx.Graph()
    G.graph["schema_version"] = 2
    G.add_node("a", label="Alpha", source_file="src/a.py", source_location="L1")
    G.add_node("b", label="Beta", source_file="src/b.py", source_location="L1")
    attrs = {"relation": "imports", "confidence": "EXTRACTED", "confidence_score": 1.0, "weight": 1.0, "source_file": "src/a.py", "source_location": "L2"}
    if extra_attrs:
        attrs.update(extra_attrs)
    G.add_edge("a", "b", **attrs)
    return G


def _make_communities(G):
    return {0: list(G.nodes())}


class TestLoadGraphFile:
    def test_loads_compact_json(self, tmp_path):
        p = tmp_path / "graph.json"
        p.write_text(json.dumps(MIN_GRAPH_DATA, separators=(",", ":")), encoding="utf-8")
        G = _load_graph_file(p)
        assert G.number_of_nodes() == 2
        assert G.number_of_edges() == 1
        assert G.graph["schema_version"] == 2

    def test_loads_indented_json(self, tmp_path):
        p = tmp_path / "graph.json"
        p.write_text(json.dumps(MIN_GRAPH_DATA, indent=2), encoding="utf-8")
        G = _load_graph_file(p)
        assert G.number_of_nodes() == 2
        assert G.number_of_edges() == 1

    def test_loads_json_gz(self, tmp_path):
        p = tmp_path / "graph.json.gz"
        raw = json.dumps(MIN_GRAPH_DATA, separators=(",", ":")).encode("utf-8")
        p.write_bytes(gzip.compress(raw))
        G = _load_graph_file(p)
        assert G.number_of_nodes() == 2
        assert G.number_of_edges() == 1

    def test_auto_detect_json_gz_when_json_missing(self, tmp_path):
        gz = tmp_path / "graph.json.gz"
        raw = json.dumps(MIN_GRAPH_DATA, separators=(",", ":")).encode("utf-8")
        gz.write_bytes(gzip.compress(raw))
        G = _load_graph_file(tmp_path / "graph.json")
        assert G.number_of_nodes() == 2

    def test_prefers_json_over_json_gz(self, tmp_path):
        json_path = tmp_path / "graph.json"
        gz_path = tmp_path / "graph.json.gz"
        json_path.write_text(json.dumps(MIN_GRAPH_DATA, separators=(",", ":")), encoding="utf-8")
        gz_path.write_bytes(gzip.compress(b'{"nodes":[],"links":[]}'))
        G = _load_graph_file(json_path)
        assert G.number_of_nodes() == 2

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _load_graph_file(tmp_path / "nonexistent.json")

    def test_files_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _load_graph_file(tmp_path / "nonexistent.json.gz")

    def test_round_trip_through_file(self, tmp_path):
        G = _build_test_graph()
        p = tmp_path / "graph.json"
        to_json(G, _make_communities(G), str(p))
        G2 = _load_graph_file(p)
        assert G2.number_of_nodes() == 2
        assert G2.number_of_edges() == 1
        assert G2.nodes["a"]["label"] == "Alpha"
        assert G2.nodes["a"]["community"] is not None

    def test_orjson_fallback(self, tmp_path):
        p = tmp_path / "graph.json"
        p.write_text(json.dumps(MIN_GRAPH_DATA, separators=(",", ":")), encoding="utf-8")
        with patch.dict(sys.modules, {"orjson": None}):
            G = _load_graph_file(p)
        assert G.number_of_nodes() == 2

    def test_node_attributes_preserved(self, tmp_path):
        G = _build_test_graph()
        G.nodes["a"]["custom_attr"] = "value"
        p = tmp_path / "graph.json"
        to_json(G, _make_communities(G), str(p))
        G2 = _load_graph_file(p)
        assert G2.nodes["a"].get("custom_attr") == "value"

    def test_edge_attributes_preserved(self, tmp_path):
        G = _build_test_graph({"extra": "data"})
        p = tmp_path / "graph.json"
        to_json(G, _make_communities(G), str(p))
        G2 = _load_graph_file(p)
        edge = G2.edges["a", "b"]
        assert edge.get("relation") == "imports"
        assert edge.get("extra") == "data"

    def test_no_src_tgt_in_export(self, tmp_path):
        G = _build_test_graph()
        p = tmp_path / "graph.json"
        assert to_json(G, _make_communities(G), str(p))
        data = json.loads(p.read_text(encoding="utf-8"))
        for link in data["links"]:
            assert "_src" not in link
            assert "_tgt" not in link

    def test_no_src_tgt_in_gz_export_round_trip(self, tmp_path):
        G = _build_test_graph()
        p = tmp_path / "graph.json"
        to_json(G, _make_communities(G), str(p))
        data = json.loads(p.read_text(encoding="utf-8"))
        for link in data["links"]:
            assert "_src" not in link
            assert "_tgt" not in link


class TestCompactJSONExport:
    def test_compact_format_no_indentation(self, tmp_path):
        G = _build_test_graph()
        p = tmp_path / "graph.json"
        assert to_json(G, _make_communities(G), str(p))
        content = p.read_text(encoding="utf-8")
        assert "\n" not in content

    def test_compact_format_valid_json(self, tmp_path):
        G = _build_test_graph()
        p = tmp_path / "graph.json"
        to_json(G, _make_communities(G), str(p))
        data = json.loads(p.read_text(encoding="utf-8"))
        assert len(data["nodes"]) == 2
        assert len(data["links"]) == 1

    def test_community_preserved_in_export(self, tmp_path):
        G = _build_test_graph()
        p = tmp_path / "graph.json"
        comms = {42: ["a", "b"]}
        to_json(G, comms, str(p))
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["nodes"][0]["community"] == 42

    def test_norm_label_present(self, tmp_path):
        G = _build_test_graph()
        p = tmp_path / "graph.json"
        to_json(G, _make_communities(G), str(p))
        data = json.loads(p.read_text(encoding="utf-8"))
        for node in data["nodes"]:
            assert "norm_label" in node

    def test_confidence_score_defaults_added(self, tmp_path):
        G = nx.Graph()
        G.graph["schema_version"] = 2
        G.add_node("a", label="A")
        G.add_node("b", label="B")
        G.add_edge("a", "b", relation="imports", confidence="INFERRED")
        p = tmp_path / "graph.json"
        to_json(G, _make_communities(G), str(p))
        data = json.loads(p.read_text(encoding="utf-8"))
        assert "confidence_score" in data["links"][0]

    def test_empty_graph_compact_export(self, tmp_path):
        G = nx.Graph()
        G.graph["schema_version"] = 2
        p = tmp_path / "graph.json"
        assert to_json(G, {}, str(p))
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["nodes"] == []
        assert data["links"] == []

    def test_hyperedges_preserved(self, tmp_path):
        G = _build_test_graph()
        G.graph["hyperedges"] = [{"id": "he1", "nodes": ["a", "b"]}]
        p = tmp_path / "graph.json"
        to_json(G, _make_communities(G), str(p))
        data = json.loads(p.read_text(encoding="utf-8"))
        assert len(data["hyperedges"]) == 1
        assert data["hyperedges"][0]["id"] == "he1"

    def test_force_overwrite_allows_smaller_graph(self, tmp_path):
        G = _build_test_graph()
        p = tmp_path / "graph.json"
        to_json(G, _make_communities(G), str(p))
        G.remove_node("b")
        assert to_json(G, _make_communities(G), str(p), force=True)

    def test_no_overwrite_without_force(self, tmp_path):
        G_big = _build_test_graph()
        G_big.add_node("c", label="Gamma")
        p = tmp_path / "graph.json"
        to_json(G_big, _make_communities(G_big), str(p))
        G_small = nx.Graph()
        G_small.graph["schema_version"] = 2
        G_small.add_node("a", label="Alpha")
        result = to_json(G_small, _make_communities(G_small), str(p))
        assert result is False

    def test_gzip_round_trip(self, tmp_path):
        G = _build_test_graph({"extra": "gzip_test"})
        p_json = tmp_path / "graph.json"
        to_json(G, _make_communities(G), str(p_json))
        raw = p_json.read_bytes()
        p_gz = tmp_path / "graph.json.gz"
        p_gz.write_bytes(gzip.compress(raw))
        G2 = _load_graph_file(p_gz)
        assert G2.number_of_nodes() == 2
        assert G2.edges["a", "b"].get("extra") == "gzip_test"
