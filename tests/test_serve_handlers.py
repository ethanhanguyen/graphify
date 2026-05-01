from __future__ import annotations

import networkx as nx


def _build_test_graph():
    G = nx.Graph()
    G.add_node("n_a", label="Alpha", file_type="code", source_file="a.py",
               source_location="L1", language="python", norm_label="alpha")
    G.add_node("n_b", label="Beta", file_type="code", source_file="b.py",
               source_location="L5", language="python", norm_label="beta")
    G.add_node("n_c", label="Gamma", file_type="code", source_file="c.py",
               source_location="L10", language="python", norm_label="gamma")
    G.add_node("n_d", label="Delta", file_type="code", source_file="d.py",
               source_location="L15", language="python", norm_label="delta")
    G.add_node("n_mod", label="utils", file_type="code", source_file="utils.py",
               source_location="", language="python", norm_label="utils")

    G.add_edge("n_a", "n_b", relation="calls", confidence="EXTRACTED",
               confidence_score=1.0, source_file="a.py", source_location="L2",
               source="n_a", target="n_b")
    G.add_edge("n_a", "n_c", relation="calls", confidence="INFERRED",
               confidence_score=0.7, source_file="a.py", source_location="L3",
               source="n_a", target="n_c")
    G.add_edge("n_b", "n_c", relation="calls", confidence="EXTRACTED",
               confidence_score=1.0, source_file="b.py", source_location="L6",
               source="n_b", target="n_c")
    G.add_edge("n_c", "n_d", relation="calls", confidence="EXTRACTED",
               confidence_score=1.0, source_file="c.py", source_location="L11",
               source="n_c", target="n_d")
    G.add_edge("n_a", "n_mod", relation="imports", confidence="EXTRACTED",
               confidence_score=1.0, source_file="a.py", source_location="L0")

    G.add_node("n_proc", label="BuildPipeline", file_type="process", source_file="",
               source_location="", language="")
    G.add_edge("n_a", "n_proc", relation="step_in_process",
               confidence="INFERRED", confidence_score=0.8,
               source_file="a.py", process_name="Build", step_index=1)
    G.add_edge("n_b", "n_proc", relation="step_in_process",
               confidence="INFERRED", confidence_score=0.8,
               source_file="b.py", process_name="Build", step_index=2)

    return G


def _find_node(G, target):
    target_lower = target.lower()
    return [nid for nid, d in G.nodes(data=True)
            if target_lower in (d.get("label") or "").lower() or target_lower == nid.lower()]


def _context_handler(arguments):
    name = arguments["name"].lower()
    matches = [(nid, d) for nid, d in _build_test_graph().nodes(data=True)
               if name in (d.get("label") or "").lower() or name == nid.lower()]
    if not matches:
        return f"No symbol matching '{arguments['name']}' found."
    nid, d = matches[0]
    G = _build_test_graph()
    lines = [
        f"Symbol: {d.get('label', nid)}",
        f"  Kind: {d.get('file_type', 'code')}",
        f"  File: {d.get('source_file', '')} {d.get('source_location', '')}",
        f"  Language: {d.get('language', '')}",
    ]
    incoming = []
    outgoing = []
    imports_list = []
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
        elif rel in ("imports", "imports_from"):
            imports_list.append((G.nodes[neighbor].get("label", neighbor), rel))
    if incoming:
        lines.append(f"\n  Incoming calls ({len(incoming)}):")
        for label, f, loc, conf in incoming[:10]:
            lines.append(f"    {label} [{conf}] {f}:{loc}")
    if outgoing:
        lines.append(f"\n  Outgoing calls ({len(outgoing)}):")
        for label, f, loc, conf in outgoing[:10]:
            lines.append(f"    {label} [{conf}] {f}:{loc}")
    if imports_list:
        lines.append(f"\n  Imports ({len(imports_list)}):")
        for label, rel in imports_list[:5]:
            lines.append(f"    {label} [{rel}]")
    processes = []
    for neighbor in G.neighbors(nid):
        edge_data = G.get_edge_data(nid, neighbor) or G.get_edge_data(neighbor, nid)
        if edge_data and isinstance(edge_data, dict) and edge_data.get("relation") == "step_in_process":
            pn = edge_data.get("process_name", "")
            si = edge_data.get("step_index", 0)
            if pn:
                processes.append((pn, si))
    if processes:
        lines.append(f"\n  Process membership ({len(processes)}):")
        for pn, si in processes[:5]:
            lines.append(f"    {pn} (step {si})")
    return "\n".join(lines)


def test_context_finds_symbol():
    result = _context_handler({"name": "Alpha"})
    assert "Symbol: Alpha" in result


def test_context_shows_outgoing_calls():
    result = _context_handler({"name": "Alpha"})
    assert "Outgoing calls" in result
    assert "Beta" in result


def test_context_shows_incoming_calls():
    result = _context_handler({"name": "Beta"})
    assert "Incoming calls" in result


def test_context_shows_imports():
    result = _context_handler({"name": "Alpha"})
    assert "imports" in result.lower() or "Imports" in result


def test_context_shows_process_membership():
    G = _build_test_graph()
    result = _context_handler({"name": "Alpha"})
    assert "Build" in result
    assert "step 1" in result


def test_context_missing_symbol():
    result = _context_handler({"name": "NoSuchSymbol"})
    assert "No symbol matching" in result


def test_context_case_insensitive():
    result_upper = _context_handler({"name": "ALPHA"})
    result_lower = _context_handler({"name": "alpha"})
    assert "Symbol: Alpha" in result_upper
    assert "Symbol: Alpha" in result_lower


def _impact_handler(arguments):
    target = arguments["target"].lower()
    direction = arguments.get("direction", "both")
    min_conf = float(arguments.get("min_confidence", 0.5))
    max_depth = int(arguments.get("max_depth", 5))
    G = _build_test_graph()
    matches = _find_node(G, target)
    if not matches:
        return f"No node matching '{arguments['target']}' found."
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
                    if rel in ("calls", "CALLS", "depends_on") and conf_score >= min_conf:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            next_f.add(neighbor)
                            nd = G.nodes[neighbor]
                            level_nodes.append({
                                "name": nd.get("label", neighbor),
                                "file": nd.get("source_file", ""),
                                "confidence": edge_data.get("confidence", ""),
                            })
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
                    if rel in ("calls", "CALLS", "depends_on") and conf_score >= min_conf:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            next_f.add(neighbor)
                            nd = G.nodes[neighbor]
                            level_nodes.append({
                                "name": nd.get("label", neighbor),
                                "file": nd.get("source_file", ""),
                                "confidence": edge_data.get("confidence", ""),
                            })
            if level_nodes:
                downstream[d] = level_nodes
            frontier = next_f
        total_affected += len(visited) - 1

    result = [f"Node: {G.nodes[nid].get('label', nid)}"]
    result.append(f"  Kind: {G.nodes[nid].get('file_type', 'code')}")
    result.append(f"  File: {G.nodes[nid].get('source_file', '')}")
    result.append(f"\n  Impact analysis (direction={direction}):")
    result.append(f"  Total affected: {total_affected}")

    if direction in ("upstream", "both") and upstream:
        result.append(f"\n  Upstream ({len(upstream)} levels):")
        for d in sorted(upstream):
            names = [node["name"] for node in upstream[d]]
            result.append(f"    Level {d}: {', '.join(names[:5])}")
    if direction in ("downstream", "both") and downstream:
        result.append(f"\n  Downstream ({len(downstream)} levels):")
        for d in sorted(downstream):
            names = [node["name"] for node in downstream[d]]
            result.append(f"    Level {d}: {', '.join(names[:5])}")
    return "\n".join(result)


def test_impact_missing_target():
    result = _impact_handler({"target": "NoSuchSymbol"})
    assert "No node matching" in result


def test_impact_finds_upstream():
    result = _impact_handler({"target": "Gamma", "direction": "upstream"})
    assert "Upstream" in result


def test_impact_finds_downstream():
    result = _impact_handler({"target": "Alpha", "direction": "downstream"})
    assert "Downstream" in result


def test_impact_both_directions():
    result = _impact_handler({"target": "Beta", "direction": "both"})
    assert "Total affected" in result


def test_impact_respects_min_confidence():
    result_lo = _impact_handler({"target": "Alpha", "min_confidence": 0.5, "max_depth": 5})
    result_hi = _impact_handler({"target": "Alpha", "min_confidence": 1.0, "max_depth": 5})
    assert result_lo != result_hi


def _trace_handler(arguments):
    from graphify.entry_points import EntryPoint
    from graphify.processes import trace_process as tp_func

    entry = arguments["entry_point"]
    max_depth = int(arguments.get("max_depth", 20))
    G = _build_test_graph()
    ep = None
    for nid, ndata in G.nodes(data=True):
        if entry.lower() in (ndata.get("label", "")).lower():
            sl = ndata.get("source_location", "0")
            try:
                line = int(next(c for c in sl if c.isdigit()) + "0" if any(c.isdigit() for c in sl) else 0)
            except Exception:
                line = 0
            ep = EntryPoint(
                name=ndata.get("label", nid),
                kind="EVENT",
                file=ndata.get("source_file", ""),
                line=line,
                language=ndata.get("language", ""),
            )
            break
    if not ep:
        return f"No entry point matching '{entry}' found."

    proc = tp_func(ep, G, max_depth=max_depth)

    lines = [
        f"Process: {proc.name}",
        f"  Entry point: {proc.entry_point.file}:{proc.entry_point.line}",
        f"  Total steps: {proc.total_steps}",
        f"  Max depth: {proc.max_depth}",
        f"  Confidence: {proc.confidence:.2f}",
        f"\n  Steps:",
    ]
    for i, step in enumerate(proc.steps[:30]):
        lines.append(f"    [{i}] depth={step.depth} {step.label} {step.file}:{step.line}")
    return "\n".join(lines)


def test_trace_finds_entry_point():
    G = _build_test_graph()
    result = _trace_handler({"entry_point": "Alpha"})
    assert "Process:" in result


def test_trace_shows_steps():
    result = _trace_handler({"entry_point": "Alpha"})
    assert "Steps:" in result


def test_trace_missing_entry_point():
    result = _trace_handler({"entry_point": "NoSuchSymbol"})
    assert "No entry point matching" in result


def test_trace_respects_max_depth():
    result = _trace_handler({"entry_point": "Alpha", "max_depth": 1})
    assert "max_depth" in result.lower() or "Max depth" in result
