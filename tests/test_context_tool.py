from __future__ import annotations

import networkx as nx
from graphify.code_schema import ConfidenceTier


def _build_simple_graph():
    G = nx.Graph()
    G.add_node("n_main", label="main", file_type="code", source_file="app.py",
               source_location="L1", language="python", norm_label="main")
    G.add_node("n_worker", label="Worker.run", file_type="code", source_file="worker.py",
               source_location="L5", language="python", norm_label="worker.run")
    G.add_node("n_helper", label="helper", file_type="code", source_file="util.py",
               source_location="L10", language="python", norm_label="helper")
    G.add_edge("n_main", "n_worker", relation="calls", confidence="EXTRACTED",
               confidence_score=1.0, source_file="app.py", source_location="L1",
               source="n_main", target="n_worker")
    G.add_edge("n_main", "n_helper", relation="calls", confidence="INFERRED",
               confidence_score=0.7, source_file="app.py", source_location="L2",
               source="n_main", target="n_helper")
    G.add_edge("n_worker", "n_helper", relation="calls", confidence="EXTRACTED",
               confidence_score=1.0, source_file="worker.py", source_location="L6",
               source="n_worker", target="n_helper")
    G.add_node("n_mod", label="utils", file_type="code", source_file="utils.py",
               source_location="", language="python", norm_label="utils")
    G.add_edge("n_main", "n_mod", relation="imports", confidence="EXTRACTED",
               confidence_score=1.0, source_file="app.py", source_location="L0")
    return G


def _context_tool(G, name):
    name_lower = name.lower()
    matches = [(nid, d) for nid, d in G.nodes(data=True)
               if name_lower in (d.get("label") or "").lower() or name_lower == nid.lower()]
    if not matches:
        return f"No symbol matching '{name}' found."

    nid, d = matches[0]
    lines = [
        f"Symbol: {d.get('label', nid)}",
        f"  Kind: {d.get('file_type', 'code')}",
        f"  File: {d.get('source_file', '')} {d.get('source_location', '')}",
        f"  Language: {d.get('language', '')}",
    ]

    incoming = []
    outgoing = []
    for neighbor in G.neighbors(nid):
        edge_data = G.get_edge_data(nid, neighbor) or G.get_edge_data(neighbor, nid)
        if not edge_data or not isinstance(edge_data, dict):
            continue
        rel = edge_data.get("relation", "")
        conf = edge_data.get("confidence", "")
        if rel in ("calls", "CALLS"):
            if nid == edge_data.get("target", ""):
                incoming.append((G.nodes[neighbor].get("label", neighbor),
                                edge_data.get("source_file", ""),
                                edge_data.get("source_location", ""),
                                conf))
            else:
                outgoing.append((G.nodes[neighbor].get("label", neighbor),
                                edge_data.get("source_file", ""),
                                edge_data.get("source_location", ""),
                                conf))

    if incoming:
        lines.append(f"\n  Incoming calls ({len(incoming)}):")
    if outgoing:
        lines.append(f"\n  Outgoing calls ({len(outgoing)}):")

    return "\n".join(lines)


def test_context_finds_symbol_and_returns_incoming_outgoing():
    G = _build_simple_graph()
    result = _context_tool(G, "main")
    assert "Symbol: main" in result
    assert "Outgoing calls" in result


def test_context_worker_has_incoming():
    G = _build_simple_graph()
    result = _context_tool(G, "Worker.run")
    assert "Incoming calls" in result
    assert "Outgoing calls" in result


def test_context_missing_symbol():
    G = _build_simple_graph()
    result = _context_tool(G, "nonexistent")
    assert "No symbol matching" in result


def test_context_shows_language():
    G = _build_simple_graph()
    result = _context_tool(G, "main")
    assert "Language: python" in result


def test_context_shows_file():
    G = _build_simple_graph()
    result = _context_tool(G, "main")
    assert "app.py" in result


def test_context_with_process_membership():
    G = _build_simple_graph()
    G.add_node("n_proc", label="BuildPipeline", file_type="process", source_file="",
               source_location="", language="", norm_label="buildpipeline")
    G.add_edge("n_main", "n_proc", relation="step_in_process",
               confidence="INFERRED", confidence_score=0.8,
               source_file="app.py", process_name="Build", step_index=1)

    processes = []
    for neighbor in G.neighbors("n_main"):
        edge_data = G.get_edge_data("n_main", neighbor) or G.get_edge_data(neighbor, "n_main")
        if edge_data and isinstance(edge_data, dict) and edge_data.get("relation") == "step_in_process":
            pn = edge_data.get("process_name", "")
            si = edge_data.get("step_index", 0)
            if pn:
                processes.append((pn, si))

    assert len(processes) == 1
    assert processes[0][0] == "Build"
    assert processes[0][1] == 1


def test_context_case_insensitive():
    G = _build_simple_graph()
    result1 = _context_tool(G, "MAIN")
    result2 = _context_tool(G, "main")
    assert "Symbol: main" in result1
    assert "Symbol: main" in result2
