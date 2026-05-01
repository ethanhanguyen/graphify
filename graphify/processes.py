from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
import networkx as nx

if TYPE_CHECKING:
    from graphify.entry_points import EntryPoint


@dataclass
class ProcessStep:
    node_id: str
    label: str
    file: str
    line: int
    depth: int
    callers: list[str] = field(default_factory=list)
    callees: list[str] = field(default_factory=list)


@dataclass
class Process:
    name: str
    entry_point: EntryPoint
    steps: list[ProcessStep] = field(default_factory=list)
    total_steps: int = 0
    max_depth: int = 0
    language: str = ""
    framework: str = ""
    confidence: float = 1.0
    cyclomatic_complexity: int = 0
    external_touches: int = 0


def trace_process(entry_point: EntryPoint, graph: nx.Graph, max_depth: int = 20,
                  max_nodes: int = 1000, file_to_nodes: dict[str, list[tuple[str, str]]] | None = None) -> Process:
    start_ids = _find_node_ids(graph, entry_point, file_to_nodes)
    if not start_ids:
        return Process(
            name=entry_point.name,
            entry_point=entry_point,
            language=entry_point.language,
            framework=entry_point.framework,
        )

    visited: dict[str, int] = {}
    parent: dict[str, str] = {}
    order: list[str] = []
    queue: deque[tuple[str, int]] = deque()
    # Collect callees/callers during BFS to avoid re-scanning neighbors later
    node_callees: dict[str, list[str]] = {}
    node_callers: dict[str, list[str]] = {}

    for sid in start_ids:
        queue.append((sid, 0))
        visited[sid] = 0

    while queue and len(order) < max_nodes:
        node_id, depth = queue.popleft()
        if depth > max_depth:
            continue

        order.append(node_id)

        for neighbor in graph.neighbors(node_id):
            edge_data = graph.get_edge_data(node_id, neighbor)
            if edge_data is None:
                continue
            if isinstance(graph, nx.MultiGraph):
                edge_data = next(iter(edge_data.values()), {})
            relation = edge_data.get("relation", "") if isinstance(edge_data, dict) else ""

            if relation not in ("calls", "CALLS"):
                continue

            # Track callee (node_id -> neighbor direction)
            node_callees.setdefault(node_id, []).append(neighbor)
            # Track caller (neighbor -> node_id direction, since edge is undirected)
            node_callers.setdefault(neighbor, []).append(node_id)

            if neighbor not in visited:
                visited[neighbor] = depth + 1
                parent[neighbor] = node_id
                queue.append((neighbor, depth + 1))

    steps: list[ProcessStep] = []
    for nid in order:
        ndata = graph.nodes[nid]
        label = ndata.get("label", nid)
        src_file = ndata.get("source_file", "")
        src_loc_str = ndata.get("source_location", "0")
        line = 0
        try:
            m = re.search(r"(\d+)", str(src_loc_str))
            if m:
                line = int(m.group(1))
        except (ValueError, TypeError):
            pass

        callees = node_callees.get(nid, [])
        callers = node_callers.get(nid, [])

        steps.append(ProcessStep(
            node_id=nid,
            label=label,
            file=src_file,
            line=line,
            depth=visited.get(nid, 0),
            callers=callers,
            callees=callees,
        ))

    branches = sum(1 for s in steps if len(s.callees) > 1)
    complexity = branches + 1

    external_files: set[str] = set()
    for s in steps:
        if s.file and s.file != entry_point.file:
            external_files.add(s.file)
    external_touches = len(external_files)

    return Process(
        name=entry_point.name,
        entry_point=entry_point,
        steps=steps,
        total_steps=len(steps),
        max_depth=max((visited.get(n, 0) for n in order), default=0),
        language=entry_point.language,
        framework=entry_point.framework,
        cyclomatic_complexity=complexity,
        external_touches=external_touches,
    )


def trace_all_entry_points(entry_points: list[EntryPoint], graph: nx.Graph) -> list[Process]:
    # Pre-build file->nodes map once instead of O(N) scan per entry point
    file_to_nodes: dict[str, list[tuple[str, str]]] = {}
    for nid, ndata in graph.nodes(data=True):
        nfile = ndata.get("source_file", "")
        if nfile:
            file_to_nodes.setdefault(nfile, []).append((nid, ndata.get("label", "")))

    processes: list[Process] = []
    for ep in entry_points:
        p = trace_process(ep, graph, file_to_nodes=file_to_nodes)
        if p.total_steps > 0:
            processes.append(p)
    return sorted(processes, key=lambda p: p.total_steps, reverse=True)


def trace_changed_nodes(graph: nx.Graph, changed_files: list[str]) -> list[Process]:
    from graphify.entry_points import EntryPoint

    changed_ids: set[str] = set()
    for nid, ndata in graph.nodes(data=True):
        nfile = ndata.get("source_file", "")
        if nfile in changed_files:
            changed_ids.add(nid)

    attached_ids: set[str] = set()
    for nid in changed_ids:
        for neighbor in graph.neighbors(nid):
            edge_data = graph.get_edge_data(nid, neighbor)
            if edge_data is None:
                continue
            if isinstance(graph, nx.MultiGraph):
                edge_data = next(iter(edge_data.values()), {})
            if isinstance(edge_data, dict) and edge_data.get("relation", "") in ("calls", "CALLS"):
                attached_ids.add(neighbor)
            edge_data_rev = graph.get_edge_data(neighbor, nid)
            if edge_data_rev is None:
                continue
            if isinstance(graph, nx.MultiGraph):
                edge_data_rev = next(iter(edge_data_rev.values()), {})
            if isinstance(edge_data_rev, dict) and edge_data_rev.get("relation", "") in ("calls", "CALLS"):
                attached_ids.add(neighbor)

    root_ids: set[str] = set()
    for nid in changed_ids | attached_ids:
        ndata = graph.nodes[nid]
        nfile = ndata.get("source_file", "")
        nlabel = ndata.get("label", "")
        if nid in changed_ids and _is_root_node(graph, nid):
            root_ids.add(nid)
        elif nid in attached_ids:
            root_ids.add(nid)

    processes: list[Process] = []
    for rid in root_ids:
        ndata = graph.nodes[rid]
        src_loc_str = ndata.get("source_location", "0")
        line = 0
        try:
            import re
            m = re.search(r"(\d+)", str(src_loc_str))
            if m:
                line = int(m.group(1))
        except (ValueError, TypeError):
            pass

        ep = EntryPoint(
            name=ndata.get("label", rid),
            kind="EVENT",
            file=ndata.get("source_file", ""),
            line=line,
            language=ndata.get("language", ""),
        )
        p = trace_process(ep, graph)
        if p.total_steps > 0:
            processes.append(p)

    return sorted(processes, key=lambda p: p.total_steps, reverse=True)


def _find_node_ids(graph: nx.Graph, ep: EntryPoint,
                   file_to_nodes: dict[str, list[tuple[str, str]]] | None = None) -> list[str]:
    if file_to_nodes:
        entries = file_to_nodes.get(ep.file, [])
        ids = [nid for nid, label in entries if ep.name.lower() in label.lower()]
        if not ids:
            ids = [nid for nid, _ in entries]
        return ids
    # Fallback for callers that don't pass file_to_nodes
    ids: list[str] = []
    for nid, ndata in graph.nodes(data=True):
        nfile = ndata.get("source_file", "")
        nlabel = ndata.get("label", "")
        if nfile == ep.file:
            if ep.name.lower() in nlabel.lower():
                ids.append(nid)
    if not ids:
        for nid, ndata in graph.nodes(data=True):
            nfile = ndata.get("source_file", "")
            if nfile == ep.file:
                ids.append(nid)
    return ids


def _is_root_node(graph: nx.Graph, node_id: str) -> bool:
    for neighbor in graph.neighbors(node_id):
        edge_data = graph.get_edge_data(neighbor, node_id)
        if edge_data is None:
            continue
        if isinstance(graph, nx.MultiGraph):
            edge_data = next(iter(edge_data.values()), {})
        if isinstance(edge_data, dict) and edge_data.get("relation", "") in ("calls", "CALLS"):
            return False
    return True
