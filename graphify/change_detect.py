from __future__ import annotations

import subprocess
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import networkx as nx


@dataclass
class AffectedSymbol:
    name: str
    kind: str
    file: str
    changed_lines: list[tuple[int, int]]
    direct: bool


@dataclass
class AffectedProcess:
    process_name: str
    step_count: int
    affected_steps: list[int]
    affected_nodes: list[str]


@dataclass
class ChangeReport:
    summary: dict = field(default_factory=dict)
    changed_symbols: list[AffectedSymbol] = field(default_factory=list)
    affected_processes: list[AffectedProcess] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    risk_level: str = "LOW"


def detect_changes(graph: nx.Graph, changed_files: list[str] | None = None, changed_lines: dict[str, list[tuple[int, int]]] | None = None, scope: str = "all") -> ChangeReport:
    if changed_files is None or changed_lines is None:
        changed_files, changed_lines = _git_diff_changes()

    symbols = find_affected_symbols(graph, changed_files, changed_lines or {})
    processes = find_affected_processes(graph, symbols)

    total_affected = len(symbols)
    direct_count = sum(1 for s in symbols if s.direct)

    max_depth = 0
    for proc in processes:
        if proc.affected_steps:
            max_depth = max(max_depth, max(proc.affected_steps, default=0))

    risk = assess_risk(total_affected, len(processes), max_depth)

    summary = {
        "changed_files": len(changed_files),
        "affected_symbols": total_affected,
        "direct_changes": direct_count,
        "indirect_changes": total_affected - direct_count,
        "affected_processes": len(processes),
        "risk_level": risk,
    }

    report = ChangeReport(
        summary=summary,
        changed_symbols=symbols,
        affected_processes=processes,
        risk_level=risk,
    )
    report.recommendations = generate_recommendations(report)

    return report


def find_affected_symbols(graph: nx.Graph, changed_files: list[str], changed_lines: dict[str, list[tuple[int, int]]]) -> list[AffectedSymbol]:
    results: list[AffectedSymbol] = []
    changed_set = set(changed_files)

    for nid, ndata in graph.nodes(data=True):
        nfile = ndata.get("source_file", "")
        nlabel = ndata.get("label", "")
        nkind = ndata.get("node_type", ndata.get("file_type", "unknown"))
        src_loc_str = ndata.get("source_location", "0")
        line = 0
        try:
            m = re.search(r"(\d+)", str(src_loc_str))
            if m:
                line = int(m.group(1))
        except (ValueError, TypeError):
            pass

        if nfile in changed_set or _is_file_node_affected(nfile, changed_set):
            direct = nfile in changed_set
            line_ranges = changed_lines.get(nfile, []) if direct else []

            if not line_ranges or _line_in_ranges(line, line_ranges):
                results.append(AffectedSymbol(
                    name=nlabel,
                    kind=nkind,
                    file=nfile,
                    changed_lines=line_ranges,
                    direct=direct,
                ))

    return results


def find_affected_processes(graph: nx.Graph, affected_symbols: list[AffectedSymbol]) -> list[AffectedProcess]:
    if not affected_symbols:
        return []

    from graphify.processes import trace_changed_nodes

    affected_files = list({s.file for s in affected_symbols})
    processes = trace_changed_nodes(graph, affected_files)

    result: list[AffectedProcess] = []
    for proc in processes:
        affected_steps: list[int] = []
        affected_nodes: list[str] = []

        for i, step in enumerate(proc.steps):
            for sym in affected_symbols:
                if sym.file == step.file and sym.name.lower() in step.label.lower():
                    affected_steps.append(i)
                    affected_nodes.append(step.node_id)
                    break

        result.append(AffectedProcess(
            process_name=proc.name,
            step_count=proc.total_steps,
            affected_steps=affected_steps,
            affected_nodes=affected_nodes,
        ))

    return result


def assess_risk(affected_count: int, affected_process_count: int, max_depth: int) -> str:
    score = 0
    score += affected_count * 2
    score += affected_process_count * 5
    score += max_depth * 3

    if score >= 80 or affected_process_count >= 10:
        return "CRITICAL"
    if score >= 40 or affected_process_count >= 5:
        return "HIGH"
    if score >= 15 or affected_process_count >= 2:
        return "MEDIUM"
    return "LOW"


def generate_recommendations(change_report: ChangeReport) -> list[str]:
    recs: list[str] = []

    direct = change_report.summary.get("direct_changes", 0)
    indirect = change_report.summary.get("indirect_changes", 0)
    proc_count = change_report.summary.get("affected_processes", 0)
    risk = change_report.risk_level

    if risk == "CRITICAL":
        recs.append("Full regression test suite required before merge")
        recs.append("Notify all team leads of breaking change risk")
    elif risk == "HIGH":
        recs.append("Run integration tests for all affected processes")
        recs.append("Consider canary deployment or feature flag")

    if proc_count > 0:
        recs.append(f"Review {proc_count} affected process trace(s) for unintended side effects")

    if direct > 5:
        recs.append(f"Large change surface ({direct} symbols) - split into smaller PRs if possible")

    if indirect > direct:
        recs.append("Indirect changes exceed direct changes - check dependency hygiene")

    if not recs:
        recs.append("Low risk change - standard code review sufficient")

    return recs


def _git_diff_changes(compare_branch: str = "HEAD") -> tuple[list[str], dict[str, list[tuple[int, int]]]]:
    try:
        diff_output = subprocess.check_output(
            ["git", "diff", "--name-only", f"{compare_branch}^..{compare_branch}"],
            text=True, stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        try:
            diff_output = subprocess.check_output(
                ["git", "diff", "--name-only", "HEAD"],
                text=True, stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return [], {}

    files = [f.strip() for f in diff_output.strip().split("\n") if f.strip()]
    lines: dict[str, list[tuple[int, int]]] = {}

    for f in files:
        if not Path(f).exists():
            continue
        try:
            line_diff = subprocess.check_output(
                ["git", "diff", "-U0", "HEAD", "--", f],
                text=True, stderr=subprocess.DEVNULL,
            )
            ranges = _parse_diff_ranges(line_diff)
            if ranges:
                lines[f] = ranges
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue

    return files, lines


def _parse_diff_ranges(diff_text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    hunk_header = re.compile(r"^@@\s+\-\d+(?:,\d+)?\s+\+(\d+)(?:,(\d+))?\s+@@")
    for line in diff_text.split("\n"):
        m = hunk_header.match(line)
        if m:
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) else 1
            ranges.append((start, start + max(count, 1) - 1))
    return _merge_ranges(ranges)


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not ranges:
        return []
    sorted_ranges = sorted(ranges, key=lambda r: r[0])
    merged = [sorted_ranges[0]]
    for current in sorted_ranges[1:]:
        last = merged[-1]
        if current[0] <= last[1] + 1:
            merged[-1] = (last[0], max(last[1], current[1]))
        else:
            merged.append(current)
    return merged


def _is_file_node_affected(nfile: str, changed_set: set[str]) -> bool:
    if not nfile:
        return False
    for cf in changed_set:
        if cf.endswith(nfile) or nfile.endswith(cf):
            return True
        if cf.split("/")[-1] == nfile.split("/")[-1]:
            return True
    return False


def _line_in_ranges(line: int, ranges: list[tuple[int, int]]) -> bool:
    if not ranges:
        return True
    return any(start <= line <= end for start, end in ranges)
