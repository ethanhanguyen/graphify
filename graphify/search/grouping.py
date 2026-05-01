from __future__ import annotations

from collections import defaultdict

import networkx as nx


def _edge_rel(graph: nx.Graph, u: str, v: str) -> str:
    data = graph.get_edge_data(u, v)
    if not data:
        return ""
    if isinstance(data, dict) and "relation" in data:
        return data.get("relation", "")
    for d in data.values():
        if isinstance(d, dict):
            return d.get("relation", "")
    return ""


def group_by_process(search_results: list[tuple[str, float]], graph: nx.Graph) -> dict:
    result_nodes = {nid for nid, _ in search_results}
    process_to_symbols: dict[str, list[str]] = defaultdict(list)
    symbol_to_score: dict[str, float] = dict(search_results)
    orphaned: list[tuple[str, float]] = []

    for nid, score in search_results:
        found = False
        for neighbor in graph.neighbors(nid):
            rel = _edge_rel(graph, nid, neighbor)
            if rel == "step_in_process":
                process_to_symbols[neighbor].append(nid)
                found = True
        if not found:
            orphaned.append((nid, score))

    processes = {}
    for proc_id, symbols in process_to_symbols.items():
        proc_data = graph.nodes[proc_id]
        proc_name = proc_data.get("label", proc_id)
        summary_text = proc_data.get("description", proc_data.get("docstring", ""))

        all_steps = [
            n for n in graph.neighbors(proc_id)
            if _edge_rel(graph, proc_id, n) == "step_in_process"
        ]
        total_steps = max(len(all_steps), 1)
        priority = len(symbols) / total_steps

        communities: set[int] = set()
        for sym_id in symbols:
            c = graph.nodes[sym_id].get("community")
            if c is not None:
                communities.add(int(c))

        processes[proc_id] = {
            "process_name": proc_name,
            "summary_text": summary_text,
            "symbols": symbols,
            "priority_score": round(priority, 4),
            "cross_community": len(communities) > 1,
            "communities": sorted(communities),
        }

    return {"processes": processes, "orphaned": orphaned}
