from __future__ import annotations

import json

import networkx as nx
import pytest

from graphify.index import (
    EdgeTypeIndex,
    NodeLabelTrie,
    ConfidenceBitmap,
    CompositeIndex,
    build_indexes,
    save_indexes,
    load_indexes,
    load_or_build_indexes,
    has_index,
    get_index,
)


def _make_graph():
    G = nx.Graph()
    G.graph["schema_version"] = 2
    G.add_node("f1", label="file1.ts", source_file="src/file1.ts")
    G.add_node("f2", label="file2.ts", source_file="src/file2.ts")
    G.add_node("func1", label="process()", source_file="src/file1.ts")
    G.add_node("func2", label="transform()", source_file="src/file2.ts")
    G.add_edge("f1", "func1", relation="contains", confidence="EXTRACTED")
    G.add_edge("f2", "func2", relation="contains", confidence="EXTRACTED")
    G.add_edge("func1", "func2", relation="calls", confidence="INFERRED")
    return G


class TestEdgeTypeIndex:
    def test_edges_by_type(self):
        G = _make_graph()
        idx = EdgeTypeIndex(G)
        contains = idx.edges("contains")
        assert len(contains) == 2
        calls = idx.edges("calls")
        assert len(calls) == 1

    def test_count(self):
        G = _make_graph()
        idx = EdgeTypeIndex(G)
        assert idx.count("contains") == 2
        assert idx.count("calls") == 1
        assert idx.count("nonexistent") == 0

    def test_edge_types(self):
        G = _make_graph()
        idx = EdgeTypeIndex(G)
        types = idx.edge_types()
        assert "contains" in types
        assert "calls" in types

    def test_type_counts(self):
        G = _make_graph()
        idx = EdgeTypeIndex(G)
        counts = idx.type_counts()
        assert counts["contains"] == 2
        assert counts["calls"] == 1

    def test_empty_graph(self):
        G = nx.Graph()
        idx = EdgeTypeIndex(G)
        assert idx.edges("x") == []
        assert idx.edge_types() == []


class TestNodeLabelTrie:
    def test_prefix_search(self):
        G = _make_graph()
        trie = NodeLabelTrie(G)
        results = trie.search("file")
        assert len(results) == 2

    def test_exact_search(self):
        G = _make_graph()
        trie = NodeLabelTrie(G)
        results = trie.search("file1.ts")
        assert results == ["f1"]

    def test_no_match(self):
        G = _make_graph()
        trie = NodeLabelTrie(G)
        assert trie.search("zzz") == []

    def test_empty_graph(self):
        G = nx.Graph()
        trie = NodeLabelTrie(G)
        assert trie.search("a") == []

    def test_limit(self):
        G = nx.Graph()
        for i in range(10):
            G.add_node(f"n{i}", label=f"item_{i}")
        trie = NodeLabelTrie(G)
        results = trie.search("item", limit=3)
        assert len(results) <= 3

    def test_case_insensitive(self):
        G = nx.Graph()
        G.add_node("n1", label="FileType.ts")
        trie = NodeLabelTrie(G)
        assert len(trie.search("filetype")) == 1


class TestConfidenceBitmap:
    def test_extracted_tier(self):
        G = _make_graph()
        bm = ConfidenceBitmap(G)
        assert bm.tier("f1", "func1") == 0

    def test_inferred_tier(self):
        G = _make_graph()
        bm = ConfidenceBitmap(G)
        assert bm.tier("func1", "func2") == 1

    def test_unknown_edge(self):
        G = _make_graph()
        bm = ConfidenceBitmap(G)
        assert bm.tier("f1", "nonexistent") == 99

    def test_is_extracted(self):
        G = _make_graph()
        bm = ConfidenceBitmap(G)
        assert bm.is_extracted("f1", "func1") is True
        assert bm.is_extracted("func1", "func2") is False

    def test_filter_neighbors(self):
        G = _make_graph()
        bm = ConfidenceBitmap(G)
        filtered = bm.filter_neighbors(G, "f1", min_tier=0)
        assert len(filtered) == 1
        assert filtered == ["func1"]


class TestCompositeIndex:
    def test_query_edge_type_confidence(self):
        G = _make_graph()
        ci = CompositeIndex(G)
        results = ci.query("contains", min_tier=0)
        assert "f1" in results
        assert "func1" in results

    def test_query_with_label_prefix(self):
        G = _make_graph()
        ci = CompositeIndex(G)
        results = ci.query("contains", label_prefix="file2")
        assert "f2" in results

    def test_to_dict(self):
        G = _make_graph()
        ci = CompositeIndex(G)
        d = ci.to_dict()
        assert "confidence" in d
        assert "trie_nodes" in d
        assert "edge_types" in d
        assert len(d["confidence"]) == 3

    def test_from_dict_round_trip(self):
        G = _make_graph()
        ci1 = CompositeIndex(G)
        d = ci1.to_dict()
        ci2 = CompositeIndex.from_dict(d)
        results = ci2.query("contains", min_tier=0)
        assert "f1" in results
        assert ci2.confidence.tier("func1", "func2") == 1

    def test_to_dict_from_dict_trie_preserved(self):
        G = _make_graph()
        ci1 = CompositeIndex(G)
        d = ci1.to_dict()
        ci2 = CompositeIndex.from_dict(d)
        assert ci2.labels.search("file") == ["f1", "f2"]
        assert ci2.labels.search("file1.ts") == ["f1"]


class TestSaveLoadIndexes:
    def test_save_and_load_round_trip(self, tmp_path):
        G = _make_graph()
        build_indexes(G)
        graph_path = str(tmp_path / "graph.json")
        save_indexes(G, graph_path)
        loaded = load_indexes(graph_path)
        assert loaded is not None
        assert loaded.confidence.tier("func1", "func2") == 1
        assert loaded.labels.search("file1.ts") == ["f1"]

    def test_load_nonexistent(self, tmp_path):
        assert load_indexes(str(tmp_path / "nonexistent.json")) is None

    def test_load_or_build_loads_when_exists(self, tmp_path):
        G = _make_graph()
        build_indexes(G)
        graph_path = str(tmp_path / "graph.json")
        save_indexes(G, graph_path)
        G2 = _make_graph()
        idx = load_or_build_indexes(G2, graph_path)
        assert idx.confidence.tier("func1", "func2") == 1

    def test_load_or_build_builds_when_missing(self, tmp_path):
        G = _make_graph()
        graph_path = str(tmp_path / "graph.json")
        idx = load_or_build_indexes(G, graph_path)
        assert idx is not None
        assert has_index(G)


class TestBuildIndexes:
    def test_build_attaches_to_graph(self):
        G = _make_graph()
        idx = build_indexes(G)
        assert G.graph["index"] is idx
        assert has_index(G)

    def test_get_index(self):
        G = _make_graph()
        idx = build_indexes(G)
        assert get_index(G) is idx

    def test_get_index_no_index(self):
        G = nx.Graph()
        G.graph["schema_version"] = 2
        assert get_index(G) is None
