from __future__ import annotations

import networkx as nx


def _build_impact_graph():
    G = nx.Graph()
    G.add_node("n_a", label="EntryPoint", file_type="code", source_file="a.py",
               source_location="L1", norm_label="entrypoint")
    G.add_node("n_b", label="Service", file_type="code", source_file="b.py",
               source_location="L5", norm_label="service")
    G.add_node("n_c", label="Repository", file_type="code", source_file="c.py",
               source_location="L10", norm_label="repository")
    G.add_node("n_d", label="Database", file_type="code", source_file="d.py",
               source_location="L15", norm_label="database")
    G.add_node("n_e", label="Logger", file_type="code", source_file="e.py",
               source_location="L20", norm_label="logger")
    G.add_node("n_f", label="Config", file_type="code", source_file="f.py",
               source_location="L25", norm_label="config")

    G.add_edge("n_a", "n_b", relation="calls", confidence="EXTRACTED",
               confidence_score=1.0, source_file="a.py")
    G.add_edge("n_a", "n_f", relation="calls", confidence="EXTRACTED",
               confidence_score=1.0, source_file="a.py")
    G.add_edge("n_b", "n_c", relation="calls", confidence="EXTRACTED",
               confidence_score=1.0, source_file="b.py")
    G.add_edge("n_c", "n_d", relation="calls", confidence="EXTRACTED",
               confidence_score=1.0, source_file="c.py")
    G.add_edge("n_b", "n_e", relation="calls", confidence="INFERRED",
               confidence_score=0.7, source_file="b.py")
    G.add_edge("n_d", "n_e", relation="calls", confidence="INFERRED",
               confidence_score=0.7, source_file="d.py")

    G.add_edge("n_a", "n_b", relation="depends_on", confidence="EXTRACTED",
               confidence_score=1.0, source_file="a.py")
    G.add_edge("n_b", "n_c", relation="depends_on", confidence="EXTRACTED",
               confidence_score=1.0, source_file="b.py")
    G.add_edge("n_c", "n_d", relation="depends_on", confidence="EXTRACTED",
               confidence_score=1.0, source_file="c.py")

    return G


def _impact_tool(G, target, direction="both", min_confidence=0.5, max_depth=5):
    target_lower = target.lower()
    matches = [nid for nid, d in G.nodes(data=True)
               if target_lower in (d.get("label") or "").lower() or target_lower == nid.lower()]
    if not matches:
        return "not_found", None, None, 0, "N/A"

    nid = matches[0]
    upstream = {}
    downstream = {}
    total_affected = 0

    if direction in ("upstream", "both"):
        visited = {nid}
        frontier = {nid}
        for d in range(1, max_depth + 1):
            next_f = set()
            level_nodes = []
            for node in frontier:
                for neighbor in G.neighbors(node):
                    edge_data = G.get_edge_data(neighbor, node)
                    if not edge_data or not isinstance(edge_data, dict):
                        continue
                    rel = edge_data.get("relation", "")
                    conf_score = edge_data.get("confidence_score", 0)
                    if rel in ("calls", "CALLS", "depends_on") and conf_score >= min_confidence:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            next_f.add(neighbor)
                            nd = G.nodes[neighbor]
                            level_nodes.append(nd.get("label", neighbor))
            if level_nodes:
                upstream[d] = level_nodes
            frontier = next_f
        total_affected += len(visited) - 1

    if direction in ("downstream", "both"):
        visited = {nid}
        frontier = {nid}
        for d in range(1, max_depth + 1):
            next_f = set()
            level_nodes = []
            for node in frontier:
                for neighbor in G.neighbors(node):
                    edge_data = G.get_edge_data(node, neighbor)
                    if not edge_data or not isinstance(edge_data, dict):
                        continue
                    rel = edge_data.get("relation", "")
                    conf_score = edge_data.get("confidence_score", 0)
                    if rel in ("calls", "CALLS", "depends_on") and conf_score >= min_confidence:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            next_f.add(neighbor)
                            nd = G.nodes[neighbor]
                            level_nodes.append(nd.get("label", neighbor))
            if level_nodes:
                downstream[d] = level_nodes
            frontier = next_f
        total_affected += len(visited) - 1

    if total_affected > 50 and max_depth > 3:
        risk = "CRITICAL"
    elif total_affected > 10:
        risk = "HIGH"
    elif total_affected > 5:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    return nid, upstream, downstream, total_affected, risk


def test_impact_missing_target():
    G = _build_impact_graph()
    nid, upstream, downstream, total, risk = _impact_tool(G, "no_such_symbol")
    assert nid == "not_found"


def test_impact_upstream_analysis():
    G = _build_impact_graph()
    nid, upstream, downstream, total, risk = _impact_tool(G, "Database", direction="upstream")
    assert nid == "n_d"
    assert upstream
    assert 1 in upstream
    assert len(upstream.get(1, [])) > 0


def test_impact_downstream_analysis():
    G = _build_impact_graph()
    nid, upstream, downstream, total, risk = _impact_tool(G, "EntryPoint", direction="downstream")
    assert nid == "n_a"
    assert downstream
    assert 1 in downstream


def test_impact_both_directions():
    G = _build_impact_graph()
    nid, upstream, downstream, total, risk = _impact_tool(G, "Service", direction="both")
    assert nid == "n_b"
    assert upstream
    assert downstream
    assert total > 0


def test_impact_risk_low():
    G = nx.Graph()
    G.add_node("n_x", label="Isolated", file_type="code", source_file="", norm_label="isolated")
    G.add_node("n_y", label="OnlyFriend", file_type="code", source_file="", norm_label="onlyfriend")
    G.add_edge("n_x", "n_y", relation="calls", confidence="EXTRACTED",
               confidence_score=1.0, source_file="")
    nid, upstream, downstream, total, risk = _impact_tool(G, "Isolated", direction="both")
    assert risk == "LOW"


def test_impact_risk_high():
    G = nx.Graph()
    for i in range(20):
        G.add_node(f"n_{i}", label=f"Node{i}", file_type="code", source_file="", norm_label=f"node{i}")
    center = "n_0"
    for i in range(1, 20):
        G.add_edge(center, f"n_{i}", relation="calls", confidence="EXTRACTED",
                   confidence_score=1.0, source_file="")
    nid, upstream, downstream, total, risk = _impact_tool(G, "Node0", direction="both")
    assert risk == "HIGH"


def test_impact_risk_medium():
    G = nx.Graph()
    for i in range(5):
        G.add_node(f"n_{i}", label=f"Node{i}", file_type="code", source_file="", norm_label=f"node{i}")
    center = "n_2"
    for i in range(5):
        if i != 2:
            G.add_edge(center, f"n_{i}", relation="calls", confidence="EXTRACTED",
                       confidence_score=1.0, source_file="")
    nid, upstream, downstream, total, risk = _impact_tool(G, "Node2", direction="both")
    assert 5 < total <= 10
    assert risk == "MEDIUM"


def test_impact_min_confidence_filtering():
    G = _build_impact_graph()
    nid1, up1, down1, total1, risk1 = _impact_tool(G, "Service", direction="downstream", min_confidence=1.0)
    nid2, up2, down2, total2, risk2 = _impact_tool(G, "Service", direction="downstream", min_confidence=0.5)
    assert total1 <= total2


def test_impact_depth_limit():
    G = _build_impact_graph()
    nid1, up1, down1, total1, risk1 = _impact_tool(G, "EntryPoint", direction="downstream", max_depth=1)
    nid2, up2, down2, total2, risk2 = _impact_tool(G, "EntryPoint", direction="downstream", max_depth=5)
    assert total1 <= total2
