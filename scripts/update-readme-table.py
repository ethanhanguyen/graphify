#!/usr/bin/env python3
"""Regenerate the cumulative benchmark table in README.md from benchmarks/*.json.

Each benchmark JSON file under benchmarks/ corresponds to one PR row.
The table is cumulative: each row = all features up to that PR enabled.
Row 1 is the baseline (PR 1.1), row 2 is PR 1.2, etc.

The table is inserted between markers:
<!-- BENCHMARK_TABLE_START -->
<!-- BENCHMARK_TABLE_END -->
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = PROJECT_ROOT / "benchmarks"
README_PATH = PROJECT_ROOT / "README.md"

BENCHMARK_ORDER = [
    ("pr-1.1-baseline.json", "Baseline (PR 1.1)"),
    ("pr-1.2-schema-index.json", "+ Schema + Index (PR 1.2)"),
    ("pr-1.3-traversal.json", "+ Traversal (PR 1.3)"),
    ("pr-2.1-call-resolution.json", "+ Call Resolution (PR 2.1)"),
    ("pr-2.2-process-tracing.json", "+ Process Tracing (PR 2.2)"),
    ("pr-2.3-hybrid-search.json", "+ Hybrid Search (PR 2.3)"),
    ("pr-3.1-cache-agents.json", "+ Caching + Agents (PR 3.1)"),
    ("pr-3.2-multi-repo.json", "+ Multi-Repo (PR 3.2)"),
    ("pr-3.3-final.json", "Final (PR 3.3)"),
]

TABLE_START = "<!-- BENCHMARK_TABLE_START -->"
TABLE_END = "<!-- BENCHMARK_TABLE_END -->"

METRICS = [
    ("query_p50_ms", "query_graph p50"),
    ("path_p50_ms", "shortest_path p50"),
    ("call_resolution_pct", "Call Res %"),
    ("process_trace_pct", "Trace %"),
    ("ndcg_at_10", "NDCG@10"),
    ("memory_mb", "Memory (MB)"),
    ("nodes", "Nodes"),
    ("edges", "Edges"),
]


def fmt(val, key):
    if val is None:
        return "—"
    if "pct" in key or "ndcg" in key:
        return f"{val:.1f}"
    if "ms" in key:
        return f"{val:.1f}"
    if "memory" in key or "nodes" in key or "edges" in key:
        return f"{int(val):,}"
    return str(val)


def load_benchmarks():
    rows = []
    for fname, label in BENCHMARK_ORDER:
        path = BENCHMARKS_DIR / fname
        if path.exists():
            data = json.loads(path.read_text())
            rows.append((label, data))
    return rows


def build_table(rows):
    header = "| Configuration | " + " | ".join(m[1] for m in METRICS) + " |\n"
    sep = "|---|" + "|".join("---" for _ in METRICS) + "|\n"
    body = ""
    for label, data in rows:
        vals = [fmt(data.get(m[0]), m[0]) for m in METRICS]
        body += f"| {label} | " + " | ".join(vals) + " |\n"
    return header + sep + body


def main():
    if not Readme_PATH.exists():
        print(f"README.md not found at {README_PATH}", file=sys.stderr)
        sys.exit(1)

    rows = load_benchmarks()
    if not rows:
        print("No benchmark files found in benchmarks/", file=sys.stderr)
        sys.exit(1)

    table = build_table(rows)

    content = README_PATH.read_text()

    if TABLE_START not in content:
        content += f"\n\n{TABLE_START}\n{TABLE_END}\n"
        updated = content.replace(f"{TABLE_START}\n{TABLE_END}", f"{TABLE_START}\n{table}\n{TABLE_END}")
    else:
        pattern_start = content.index(TABLE_START)
        pattern_end = content.index(TABLE_END, pattern_start)
        updated = (
            content[: pattern_start + len(TABLE_START)]
            + "\n"
            + table
            + content[pattern_end:]
        )

    README_PATH.write_text(updated)
    print(f"Updated {README_PATH} with {len(rows)} benchmark rows")


if __name__ == "__main__":
    main()
