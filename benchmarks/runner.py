#!/usr/bin/env python3
"""Benchmark runner for graphify — records structured results to benchmarks/*.json.

After each PR, run this to capture the current state of all metrics:
    python benchmarks/runner.py --pr pr-1.2-schema-index

This generates benchmarks/pr-1.2-schema-index.json with query performance,
code intelligence accuracy, index performance, and coverage numbers.
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = PROJECT_ROOT / "benchmarks"
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures"


def _run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def measure_query_perf(graph_path: Path, scale: int = 100) -> dict:
    """Run BFS query benchmarks on the graph."""
    import networkx as nx
    from networkx.readwrite import json_graph

    G = json_graph.node_link_graph(json.loads(graph_path.read_text()), edges="links")
    labels = [d.get("label", nid) for nid, d in G.nodes(data=True)]
    labels = [l for l in labels if l][:10]

    timings = []
    for label in labels:
        t0 = time.perf_counter()
        terms = [t.lower() for t in label.split() if len(t) > 2]
        scored = [(sum(1 for t in terms if t in d.get("label", "").lower()), nid)
                  for nid, d in G.nodes(data=True)]
        scored.sort(reverse=True)
        start = [nid for _, nid in scored[:3]]
        if start:
            visited = set(start)
            frontier = set(start)
            for _ in range(3):
                nf = set()
                for n in frontier:
                    nf.update(nb for nb in G.neighbors(n) if nb not in visited)
                visited.update(nf)
                frontier = nf
        timings.append((time.perf_counter() - t0) * 1000)

    if not timings:
        return {}
    return {
        "query_graph_p50": round(statistics.median(timings), 1),
        "query_graph_p95": round(sorted(timings)[int(len(timings) * 0.95)], 1),
        "query_graph_avg": round(statistics.mean(timings), 1),
    }


def measure_path_perf(graph_path: Path) -> dict:
    import networkx as nx
    from networkx.readwrite import json_graph

    G = json_graph.node_link_graph(json.loads(graph_path.read_text()), edges="links")
    nodes = list(G.nodes())
    pairs = [(nodes[i], nodes[(i + 1) % len(nodes)]) for i in range(min(5, len(nodes)))]

    timings = []
    for src, tgt in pairs:
        t0 = time.perf_counter()
        try:
            nx.shortest_path(G, src, tgt)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            pass
        timings.append((time.perf_counter() - t0) * 1000)

    if not timings:
        return {}
    return {
        "shortest_path_p50": round(statistics.median(timings), 1),
        "shortest_path_avg": round(statistics.mean(timings), 1),
    }


def measure_coverage() -> dict:
    """Run pytest --cov and parse coverage."""
    result = _run(
        ["python", "-m", "pytest", "tests/", "-q", "--cov=graphify", "--cov-report=json", "-p", "no:warnings"],
        timeout=120,
    )
    cov_path = PROJECT_ROOT / "coverage.json"
    if cov_path.exists():
        data = json.loads(cov_path.read_text())
        totals = data.get("totals", {})
        return {
            "line_coverage_pct": round(totals.get("percent_covered", 0), 1),
            "branch_coverage_pct": 0,
        }
    return {"line_coverage_pct": 0, "branch_coverage_pct": 0}


def measure_graph_stats(graph_path: Path) -> dict:
    data = json.loads(graph_path.read_text())
    nodes = data.get("nodes", [])
    edges = data.get("links", [])
    file_size = graph_path.stat().st_size / (1024 * 1024)
    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "memory_mb": round(file_size, 1),
    }


def main():
    pr_name = None
    for i, arg in enumerate(sys.argv):
        if arg == "--pr" and i + 1 < len(sys.argv):
            pr_name = sys.argv[i + 1]

    if not pr_name:
        print("Usage: python benchmarks/runner.py --pr <pr-name>", file=sys.stderr)
        sys.exit(1)

    # Build the fixture graph
    print("Building fixture graph...")
    _run(["python", "-m", "graphify", "update", str(FIXTURE_DIR)], timeout=60)
    graph_path = FIXTURE_DIR / "graphify-out" / "graph.json"
    if not graph_path.exists():
        print("graph.json not produced", file=sys.stderr)
        sys.exit(1)

    results = {}
    results["pr"] = pr_name
    results["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    print("Measuring query performance...")
    results.update(measure_query_perf(graph_path))

    print("Measuring path performance...")
    results.update(measure_path_perf(graph_path))

    print("Measuring graph stats...")
    results.update(measure_graph_stats(graph_path))

    print("Measuring coverage...")
    results.update(measure_coverage())

    BENCHMARKS_DIR.mkdir(exist_ok=True)
    out_path = BENCHMARKS_DIR / f"{pr_name}.json"
    out_path.write_text(json.dumps(results, indent=2))

    # Also maintain latest snapshot
    latest_path = BENCHMARKS_DIR / "latest.json"
    latest_path.write_text(json.dumps(results, indent=2))

    print(f"Results: {out_path}")
    for k, v in sorted(results.items()):
        if k not in ("pr", "timestamp"):
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
