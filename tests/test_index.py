"""Tests for graphify/index.py - indexing layer."""
import networkx as nx
from graphify.index import (
    build_edge_index,
    get_edges_by_relation,
    get_neighbors_by_relation,
    build_confidence_bitmap,
    filter_edges_by_confidence,
    build_label_index,
    lookup_nodes_by_prefix,
    build_indexes,
)


def _make_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node("n1", label="extract", norm_label="extract", source_file="extract.py")
    G.add_node("n2", label="cluster", norm_label="cluster", source_file="cluster.py")
    G.add_node("n3", label="build", norm_label="build", source_file="build.py")
    G.add_node("n4", label="report", norm_label="report", source_file="report.py")
    G.add_edge("n1", "n2", relation="calls", confidence="INFERRED")
    G.add_edge("n2", "n3", relation="imports", confidence="EXTRACTED")
    G.add_edge("n3", "n4", relation="uses", confidence="EXTRACTED")
    G.add_edge("n1", "n4", relation="calls", confidence="AMBIGUOUS")
    return G


class TestBuildEdgeIndex:
    def test_build_edge_index_keys(self):
        G = _make_graph()
        idx = build_edge_index(G)
        assert "calls" in idx
        assert "imports" in idx
        assert "uses" in idx

    def test_build_edge_index_counts(self):
        G = _make_graph()
        idx = build_edge_index(G)
        assert len(idx["calls"]) == 2
        assert len(idx["imports"]) == 1
        assert len(idx["uses"]) == 1

    def test_build_edge_index_empty_graph(self):
        G = nx.Graph()
        idx = build_edge_index(G)
        assert idx == {}


class TestGetEdgesByRelation:
    def test_get_edges_by_relation_indexed(self):
        G = _make_graph()
        G.graph["indexes"] = {"edge_relation": build_edge_index(G)}
        edges = get_edges_by_relation(G, "calls")
        assert len(edges) == 2

    def test_get_edges_by_relation_fallback(self):
        G = _make_graph()
        edges = get_edges_by_relation(G, "calls")
        assert len(edges) == 2

    def test_get_edges_by_relation_none(self):
        G = _make_graph()
        edges = get_edges_by_relation(G, "nonexistent")
        assert edges == []


class TestGetNeighborsByRelation:
    def test_get_neighbors_by_relation_indexed(self):
        G = _make_graph()
        G.graph["indexes"] = {"edge_relation": build_edge_index(G)}
        nbs = get_neighbors_by_relation(G, "n1", "calls")
        assert "n2" in nbs
        assert "n4" in nbs

    def test_get_neighbors_by_relation_fallback(self):
        G = _make_graph()
        nbs = get_neighbors_by_relation(G, "n2", "imports")
        assert "n3" in nbs

    def test_get_neighbors_by_relation_none(self):
        G = _make_graph()
        nbs = get_neighbors_by_relation(G, "n1", "uses")
        assert nbs == []


class TestBuildConfidenceBitmap:
    def test_build_confidence_bitmap_keys(self):
        G = _make_graph()
        bitmap = build_confidence_bitmap(G)
        assert "EXTRACTED" in bitmap
        assert "INFERRED" in bitmap
        assert "AMBIGUOUS" in bitmap

    def test_build_confidence_bitmap_counts(self):
        G = _make_graph()
        bitmap = build_confidence_bitmap(G)
        assert len(bitmap["EXTRACTED"]) == 2
        assert len(bitmap["INFERRED"]) == 1
        assert len(bitmap["AMBIGUOUS"]) == 1


class TestFilterEdgesByConfidence:
    def test_filter_extracted_only(self):
        G = _make_graph()
        G.graph["indexes"] = {"confidence_bitmap": build_confidence_bitmap(G)}
        edges = [("n1", "n2"), ("n2", "n3"), ("n3", "n4"), ("n1", "n4")]
        filtered = filter_edges_by_confidence(G, edges, "EXTRACTED")
        result = sorted(tuple(sorted(e)) for e in filtered)
        expected = sorted(tuple(sorted(e)) for e in [("n2", "n3"), ("n3", "n4")])
        assert result == expected

    def test_filter_inferred_and_above(self):
        G = _make_graph()
        G.graph["indexes"] = {"confidence_bitmap": build_confidence_bitmap(G)}
        edges = [("n1", "n2"), ("n2", "n3"), ("n3", "n4"), ("n1", "n4")]
        filtered = filter_edges_by_confidence(G, edges, "INFERRED")
        assert len(filtered) == 3

    def test_filter_all(self):
        G = _make_graph()
        G.graph["indexes"] = {"confidence_bitmap": build_confidence_bitmap(G)}
        edges = [("n1", "n2"), ("n2", "n3"), ("n3", "n4"), ("n1", "n4")]
        filtered = filter_edges_by_confidence(G, edges, "AMBIGUOUS")
        assert len(filtered) == 4

    def test_filter_fallback_no_bitmap(self):
        G = _make_graph()
        edges = [("n1", "n2"), ("n2", "n3"), ("n3", "n4"), ("n1", "n4")]
        filtered = filter_edges_by_confidence(G, edges, "EXTRACTED")
        assert len(filtered) == 2


class TestBuildLabelIndex:
    def test_build_label_index_prefixes(self):
        G = _make_graph()
        idx = build_label_index(G)
        assert "ext" in idx
        assert "clu" in idx
        assert "bui" in idx
        assert "rep" in idx

    def test_build_label_index_node_ids(self):
        G = _make_graph()
        idx = build_label_index(G)
        assert "n1" in idx["ext"]
        assert "n2" in idx["clu"]
        assert "n3" in idx["bui"]
        assert "n4" in idx["rep"]

    def test_build_label_index_empty_graph(self):
        G = nx.Graph()
        idx = build_label_index(G)
        assert idx == {}


class TestLookupNodesByPrefix:
    def test_lookup_nodes_by_prefix_exact(self):
        G = _make_graph()
        idx = build_label_index(G)
        result = lookup_nodes_by_prefix("ext", idx)
        assert "n1" in result

    def test_lookup_nodes_by_prefix_case_insensitive(self):
        G = _make_graph()
        idx = build_label_index(G)
        result = lookup_nodes_by_prefix("EXT", idx)
        assert "n1" in result

    def test_lookup_nodes_by_prefix_missing(self):
        G = _make_graph()
        idx = build_label_index(G)
        result = lookup_nodes_by_prefix("zzz", idx)
        assert result == []


class TestBuildIndexes:
    def test_build_indexes_returns_all_three(self):
        G = _make_graph()
        idx = build_indexes(G)
        assert "edge_relation" in idx
        assert "confidence_bitmap" in idx
        assert "label_index" in idx

    def test_indexes_stored_on_graph(self):
        G = _make_graph()
        G.graph["indexes"] = build_indexes(G)
        assert "edge_relation" in G.graph["indexes"]
        assert "confidence_bitmap" in G.graph["indexes"]
        assert "label_index" in G.graph["indexes"]

    def test_build_indexes_empty_graph(self):
        G = nx.Graph()
        idx = build_indexes(G)
        assert idx["edge_relation"] == {}
        assert idx["confidence_bitmap"]["EXTRACTED"] == []
        assert idx["label_index"] == {}
