import networkx as nx
from graphify.query_planner import (
    select_start_nodes_by_degree,
    order_frontier_by_confidence,
    reorder_frontier_at_hop,
)


def _make_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node("n1", label="high_degree")
    G.add_node("n2", label="low_degree")
    G.add_node("n3", label="medium_degree")
    G.add_node("n4", label="target")
    G.add_node("n5", label="other")
    G.add_edge("n1", "n4", relation="calls", confidence="EXTRACTED")
    G.add_edge("n1", "n3", relation="imports", confidence="EXTRACTED")
    G.add_edge("n1", "n5", relation="uses", confidence="AMBIGUOUS")
    G.add_edge("n2", "n4", relation="calls", confidence="EXTRACTED")
    return G


def test_select_lowest_degree_start():
    G = _make_graph()
    candidates = ["n1", "n2", "n3"]
    result = select_start_nodes_by_degree(G, candidates)
    assert result == "n2"


def test_select_empty_candidates():
    G = _make_graph()
    result = select_start_nodes_by_degree(G, [])
    assert result == ""


def test_reorder_by_confidence_extracted_first():
    G = _make_graph()
    frontier = ["n4", "n5", "n3"]
    result = order_frontier_by_confidence(G, frontier, preference="extracted")
    n4_index = result.index("n4")
    n5_index = result.index("n5")
    assert n4_index < n5_index


def test_reorder_by_confidence_all():
    G = _make_graph()
    frontier = ["n4", "n3"]
    result = order_frontier_by_confidence(G, frontier, preference="all")
    assert len(result) == 2
    assert "n3" in result
    assert "n4" in result


def test_reorder_frontier_at_hops():
    G = _make_graph()
    frontier = {"n4", "n3", "n5"}
    visited: set[str] = set()
    result = reorder_frontier_at_hop(G, frontier, visited)
    assert len(result) == 3
    assert result[0] != result[1]


def test_reorder_frontier_at_hops_excludes_visited():
    G = _make_graph()
    frontier = {"n4", "n3"}
    visited = {"n4"}
    result = reorder_frontier_at_hop(G, frontier, visited)
    assert len(result) == 1
    assert "n3" in result
    assert "n4" not in result


def test_reorder_frontier_empty():
    G = _make_graph()
    result = reorder_frontier_at_hop(G, {"n4"}, {"n4"})
    assert result == []
