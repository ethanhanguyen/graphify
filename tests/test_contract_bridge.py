"""Tests for graphify/contract_bridge.py."""
import pytest
import networkx as nx

from graphify.contract_bridge import (
    detect_shared_interfaces,
    detect_shared_types,
    map_api_consumers,
    build_cross_repo_edges,
)


def _make_graph_a():
    G = nx.Graph()
    G.add_node("a1", label="UserService", node_type="class", source_file="a.py")
    G.add_node("a2", label="get_user", node_type="function", source_file="a.py")
    G.add_edge("a1", "a2", relation="defines")
    return G


def _make_graph_b():
    G = nx.Graph()
    G.add_node("b1", label="userservice", node_type="class", source_file="b.py")
    G.add_node("b2", label="list_users", node_type="function", source_file="b.py")
    G.add_edge("b1", "b2", relation="defines")
    return G


def _make_graph_no_shared():
    G = nx.Graph()
    G.add_node("c1", label="Foo", node_type="class", source_file="c.py")
    G.add_node("c2", label="Bar", node_type="class", source_file="d.py")
    return G


def test_detect_shared_interfaces():
    G_a = _make_graph_a()
    G_b = _make_graph_b()
    results = detect_shared_interfaces({"repoA": G_a, "repoB": G_b})
    assert len(results) == 1
    assert results[0]["interface_name"] == "userservice"
    assert "repoA" in results[0]["repos"]
    assert "repoB" in results[0]["repos"]
    assert "get_user" in results[0]["methods"]


def test_detect_shared_types():
    G_a = _make_graph_a()
    G_b = _make_graph_b()
    results = detect_shared_types({"repoA": G_a, "repoB": G_b})
    assert len(results) == 1


def test_no_shared_symbols():
    G_a = _make_graph_no_shared()
    G_b = nx.Graph()
    G_b.add_node("d1", label="UniqueService", node_type="class", source_file="d.py")
    results = detect_shared_interfaces({"repoA": G_a, "repoB": G_b})
    assert len(results) == 0


def test_build_cross_repo_edges():
    G_a = _make_graph_a()
    G_b = _make_graph_b()

    class FakePool:
        def get_graph(self, rid):
            return {"repoA": G_a, "repoB": G_b}.get(rid)
    pool = FakePool()
    edges = build_cross_repo_edges("repoA", "repoB", pool)
    assert len(edges) == 1
    assert edges[0]["interface"] == "userservice"
    assert edges[0]["relation"] == "shared_interface"


def test_map_api_consumers_empty():
    class FakePool:
        def get_graph(self, rid):
            return None
    pool = FakePool()
    results = map_api_consumers("no-api", ["consumer1"], pool)
    assert results == []


def test_single_repo_no_shared():
    G = _make_graph_no_shared()
    results = detect_shared_interfaces({"only": G})
    assert results == []


def test_detect_skips_non_class_nodes():
    G_a = nx.Graph()
    G_a.add_node("f1", label="helper", node_type="function", source_file="a.py")
    G_b = nx.Graph()
    G_b.add_node("f2", label="helper", node_type="function", source_file="b.py")
    results = detect_shared_interfaces({"A": G_a, "B": G_b})
    assert results == []


def test_detect_skips_empty_label():
    G_a = nx.Graph()
    G_a.add_node("e1", label="", node_type="class", source_file="a.py")
    G_b = nx.Graph()
    G_b.add_node("e2", label="", node_type="class", source_file="b.py")
    results = detect_shared_interfaces({"A": G_a, "B": G_b})
    assert results == []


def test_map_api_consumers_with_data():
    G_api = nx.Graph()
    G_api.add_node("r1", label="/api/users", node_type="route", source_file="routes.py")
    G_api.add_node("r2", label="/api/health", node_type="route", source_file="health.py")
    G_consumer = nx.Graph()
    G_consumer.add_node("c1", label="route handler", source_file="consumer.py")

    class FakePool:
        def get_graph(self, rid):
            if rid == "api":
                return G_api
            if rid == "consumer1":
                return G_consumer
            return None
    pool = FakePool()
    results = map_api_consumers("api", ["consumer1"], pool)
    assert len(results) >= 1


def test_map_api_consumers_api_not_found():
    class FakePool:
        def get_graph(self, rid):
            return None
    pool = FakePool()
    results = map_api_consumers("no-such-api", ["c1"], pool)
    assert results == []


def test_build_cross_repo_edges_missing_graph():
    class FakePool:
        def get_graph(self, rid):
            return None
    pool = FakePool()
    edges = build_cross_repo_edges("a", "b", pool)
    assert edges == []
