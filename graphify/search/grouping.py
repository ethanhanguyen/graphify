"""Process-grouped search results — organizes hybrid search hits by process membership."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GroupedSearchResult:
    process_id: str
    process_name: str
    summary: str
    priority: float
    symbol_count: int
    process_type: str
    step_count: int
    definitions: list[dict] = field(default_factory=list)
    references: list[dict] = field(default_factory=list)


def group_results_by_process(
    ranked_results: list[tuple[str, float]],
    G,
    processes: list,
) -> list[GroupedSearchResult]:
    result_node_ids = dict(ranked_results)
    grouped: list[GroupedSearchResult] = []

    for proc in processes:
        step_node_ids = {s.node_id for s in proc.steps}
        matching = sorted(
            [(nid, result_node_ids[nid]) for nid in result_node_ids if nid in step_node_ids],
            key=lambda x: x[1],
            reverse=True,
        )
        if not matching:
            continue

        avg_score = sum(s for _, s in matching) / len(matching)
        density = len(matching) / max(1, len(proc.steps))
        priority = avg_score * density

        definitions: list[dict] = []
        references: list[dict] = []
        for nid, score in matching[:3]:
            nd = G.nodes.get(nid, {})
            entry = {
                "name": nd.get("label", nid),
                "type": nd.get("node_type", nd.get("file_type", "unknown")),
                "file": nd.get("source_file", ""),
                "confidence": str(score),
            }
            definitions.append(entry)

        grouped.append(GroupedSearchResult(
            process_id=proc.id,
            process_name=proc.name,
            summary=f"{proc.name}: {proc.entry_point.kind} with {len(proc.steps)} steps",
            priority=round(priority, 4),
            symbol_count=len(matching),
            process_type=proc.entry_point.kind,
            step_count=len(proc.steps),
            definitions=definitions,
            references=references,
        ))

    grouped.sort(key=lambda g: g.priority, reverse=True)
    return grouped


def format_grouped_results(grouped: list[GroupedSearchResult]) -> str:
    if not grouped:
        return "No matching processes found."

    lines = [f"processes: ({len(grouped)} found)"]
    for g in grouped:
        lines.append(
            f"  - {g.process_name} [{g.process_type}] "
            f"priority={g.priority} symbols={g.symbol_count}/{g.step_count}"
        )

    all_defs: list[dict] = []
    for g in grouped:
        all_defs.extend(g.definitions)
    all_defs = all_defs[:10]

    if all_defs:
        lines.append("definitions:")
        for d in all_defs:
            lines.append(f"  - {d['name']} [{d['type']}] {d['file']}")

    lines.append(f"total_results: {len(grouped)}")
    return "\n".join(lines)
