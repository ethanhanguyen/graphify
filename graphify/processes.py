"""Process tracing engine — entry point detection, execution tracing, change impact analysis."""
from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx


@dataclass
class EntryPoint:
    node_id: str
    label: str
    kind: str
    route: str | None = None
    method: str | None = None
    score: float = 0.0
    file: str = ""


@dataclass
class ProcessStep:
    node_id: str
    step_index: int
    call_chain: list[str]
    file: str = ""
    line: str = ""
    is_branching: bool = False


@dataclass
class Process:
    id: str
    name: str
    entry_point: EntryPoint
    steps: list[ProcessStep]
    confidence: float
    total_calls: int
    unique_files: int


def _is_calls_edge(G: nx.Graph, u: str, v: str) -> bool:
    data = G.edges.get((u, v))
    if data is None:
        return False
    rel = data.get("relation", data.get("edge_type", ""))
    if isinstance(rel, str):
        return rel.lower() in ("calls", "step_in_process")
    return False


def _get_edge_confidence(G: nx.Graph, u: str, v: str) -> float:
    data = G.edges.get((u, v))
    if data is None:
        return 0.5
    return float(data.get("confidence_score", 0.7))


def detect_entry_points(G: nx.Graph) -> list[EntryPoint]:
    entries: list[EntryPoint] = []

    for nid, data in G.nodes(data=True):
        label = data.get("label", nid)
        source_file = data.get("source_file", "")

        has_route = False
        route_path = None
        http_method = None

        for neighbor in G.neighbors(nid):
            edge_data = G.edges.get((nid, neighbor)) or G.edges.get((neighbor, nid), {})
            rel = edge_data.get("relation", edge_data.get("edge_type", ""))
            if isinstance(rel, str) and rel.lower() == "handles_route":
                has_route = True
                route_path = edge_data.get("route") or data.get("route")
                http_method = edge_data.get("method") or data.get("method")
                break

        if has_route or "route" in (data.get("node_type", "") or "").lower():
            entries.append(EntryPoint(
                node_id=nid, label=label, kind="route_handler",
                route=route_path, method=http_method, score=10.0,
                file=source_file,
            ))
            continue

        label_lower = label.lower()
        source_lower = source_file.lower()

        if label_lower == "main()" or "__main__" in source_lower or label_lower == "main":
            entries.append(EntryPoint(
                node_id=nid, label=label, kind="cli_main", score=7.0, file=source_file,
            ))
            continue

        if label_lower.startswith("test_") or label_lower.endswith("test"):
            entries.append(EntryPoint(
                node_id=nid, label=label, kind="test", score=3.0, file=source_file,
            ))
            continue

        if "middleware" in label_lower:
            entries.append(EntryPoint(
                node_id=nid, label=label, kind="middleware", score=5.0, file=source_file,
            ))
            continue

        if any(kw in label_lower for kw in ("cron", "schedule", "job")):
            entries.append(EntryPoint(
                node_id=nid, label=label, kind="cron", score=6.0, file=source_file,
            ))
            continue

        is_exported = data.get("is_exported", False)
        degree = G.degree(nid)
        visibility = data.get("visibility", "public")
        if degree > 5 and (is_exported or visibility == "public"):
            entries.append(EntryPoint(
                node_id=nid, label=label, kind="library_export", score=1.0, file=source_file,
            ))

    entries.sort(key=lambda e: e.score, reverse=True)
    return entries


def trace_process(G: nx.Graph, entry: EntryPoint, max_depth: int = 20) -> Process:
    visited: set[str] = set()
    frontier: deque[str] = deque([entry.node_id])
    parent: dict[str, str | None] = {entry.node_id: None}
    depth: dict[str, int] = {entry.node_id: 0}
    confidences: list[float] = []

    while frontier:
        current = frontier.popleft()
        if current in visited:
            continue
        visited.add(current)

        current_depth = depth[current]
        if current_depth >= max_depth:
            continue

        outgoing_calls = []
        for neighbor in G.neighbors(current):
            if neighbor in visited:
                continue
            edge_data = G.edges.get((current, neighbor))
            if edge_data is None:
                continue
            rel = edge_data.get("relation", edge_data.get("edge_type", ""))
            if not (isinstance(rel, str) and rel.lower() == "calls"):
                continue
            outgoing_calls.append(neighbor)

        for neighbor in outgoing_calls:
            if neighbor not in parent:
                parent[neighbor] = current
                depth[neighbor] = current_depth + 1
                frontier.append(neighbor)
                confidences.append(_get_edge_confidence(G, current, neighbor))

    steps: list[ProcessStep] = []
    unique_files: set[str] = set()
    call_count = 0

    step_nodes = sorted(visited, key=lambda n: depth.get(n, 0))
    for i, nid in enumerate(step_nodes):
        data = G.nodes.get(nid, {})
        source_file = data.get("source_file", "")
        source_location = data.get("source_location", "")

        chain: list[str] = []
        cur = nid
        while cur is not None:
            chain.append(G.nodes.get(cur, {}).get("label", cur))
            cur = parent.get(cur)
        chain.reverse()

        outgoing = 0
        for nb in G.neighbors(nid):
            ed = G.edges.get((nid, nb))
            if ed:
                r = ed.get("relation", ed.get("edge_type", ""))
                if isinstance(r, str) and r.lower() == "calls":
                    outgoing += 1

        steps.append(ProcessStep(
            node_id=nid,
            step_index=i,
            call_chain=chain,
            file=source_file,
            line=source_location,
            is_branching=outgoing > 1,
        ))
        if source_file:
            unique_files.add(source_file)
        if nid != entry.node_id:
            call_count += 1

    avg_confidence = sum(confidences) / len(confidences) if confidences else 1.0

    return Process(
        id=f"process_{entry.node_id}",
        name=entry.label,
        entry_point=entry,
        steps=steps,
        confidence=round(avg_confidence, 4),
        total_calls=call_count,
        unique_files=len(unique_files),
    )


def build_processes(G: nx.Graph) -> list[Process]:
    entries = detect_entry_points(G)
    top_n = min(50, len(entries))
    processes: list[Process] = []
    for entry in entries[:top_n]:
        proc = trace_process(G, entry, max_depth=20)
        processes.append(proc)
    return processes


def _jaccard(a: set[str], b: set[str]) -> float:
    union = len(a | b)
    if union == 0:
        return 1.0
    return len(a & b) / union


def cluster_processes(processes: list[Process]) -> list[list[Process]]:
    if not processes:
        return []

    step_sets = [{s.node_id for s in p.steps} for p in processes]
    clusters: list[list[int]] = []
    assigned: set[int] = set()

    for i in range(len(processes)):
        if i in assigned:
            continue
        cluster = [i]
        assigned.add(i)
        for j in range(i + 1, len(processes)):
            if j in assigned:
                continue
            if _jaccard(step_sets[i], step_sets[j]) > 0.9:
                cluster.append(j)
                assigned.add(j)
        clusters.append(cluster)

    return [[processes[i] for i in c] for c in clusters]


def detect_changes(
    G: nx.Graph,
    processes: list[Process],
    changed_files: list[str] | None = None,
) -> dict:
    if changed_files is None:
        return {
            "summary": {
                "changed_count": 0,
                "affected_count": 0,
                "changed_files": [],
                "risk_level": "LOW",
            },
            "changed_symbols": [],
            "affected_processes": [],
            "recommendations": [],
        }

    changed_files_set = set(changed_files)
    changed_nodes: list[dict] = []
    for nid, data in G.nodes(data=True):
        sf = data.get("source_file", "")
        if sf in changed_files_set:
            changed_nodes.append({
                "name": data.get("label", nid),
                "kind": data.get("node_type", data.get("file_type", "unknown")),
                "file": sf,
                "changed_lines": data.get("source_location", ""),
            })

    changed_nids = {cn["name"] for cn in changed_nodes}
    affected = []
    for proc in processes:
        affected_steps = [
            i for i, s in enumerate(proc.steps)
            if s.file in changed_files_set
        ]
        if affected_steps:
            affected.append({
                "name": proc.name,
                "step_count": len(proc.steps),
                "affected_steps": affected_steps,
            })

    affected_count = len(changed_nodes)
    affected_proc_count = len(affected)
    risk = assess_risk(affected_count, affected_proc_count)

    recommendations = []
    if risk == "HIGH":
        recommendations.append({
            "action": "Add integration tests for all affected processes",
            "reason": f"High risk: {affected_proc_count} processes affected by {affected_count} symbol changes",
        })
        recommendations.append({
            "action": "Deploy with feature flag or canary",
            "reason": "Wide blast radius warrants gradual rollout",
        })
    elif risk == "MEDIUM":
        recommendations.append({
            "action": "Add unit tests for changed symbols",
            "reason": f"Medium risk: {affected_proc_count} processes affected",
        })
    else:
        recommendations.append({
            "action": "Proceed with standard CI",
            "reason": "Low risk: changes are isolated",
        })

    return {
        "summary": {
            "changed_count": len(changed_files),
            "affected_count": affected_count,
            "changed_files": list(changed_files),
            "risk_level": risk,
        },
        "changed_symbols": changed_nodes,
        "affected_processes": affected,
        "recommendations": recommendations,
    }


def assess_risk(affected_count: int, affected_processes: int) -> str:
    if affected_count > 20 or affected_processes > 10:
        return "HIGH"
    elif affected_count > 5 or affected_processes > 3:
        return "MEDIUM"
    return "LOW"


def write_processes_json(
    processes: list[Process],
    output_path: str = "graphify-out/processes.json",
) -> None:
    out = Path(output_path)
    payload = []
    for proc in processes:
        payload.append({
            "id": proc.id,
            "name": proc.name,
            "entry_point": {
                "node_id": proc.entry_point.node_id,
                "label": proc.entry_point.label,
                "kind": proc.entry_point.kind,
                "route": proc.entry_point.route,
                "method": proc.entry_point.method,
                "score": proc.entry_point.score,
                "file": proc.entry_point.file,
            },
            "confidence": proc.confidence,
            "total_calls": proc.total_calls,
            "unique_files": proc.unique_files,
            "steps": [
                {
                    "node_id": s.node_id,
                    "step_index": s.step_index,
                    "call_chain": s.call_chain,
                    "file": s.file,
                    "line": s.line,
                    "is_branching": s.is_branching,
                }
                for s in proc.steps
            ],
        })
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
