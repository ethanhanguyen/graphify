#!/usr/bin/env python3
"""VSCode-level benchmark — runs graphify CLI queries/paths/explains and records timing.

Usage:
    python benchmarks/vscode-bench.py --graph .tmp/vscode/graphify-out/graph.json
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


def _run_cli(args, timeout=120):
    t0 = time.perf_counter()
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
    return {
        "elapsed_ms": round(elapsed_ms, 1),
        "output_lines": len(lines),
        "stdout_preview": result.stdout[:500],
        "stderr": result.stderr[:500],
        "rc": result.returncode,
        "hops": _extract_hops(lines),
    }


def _extract_hops(lines):
    for line in lines:
        if "hops" in line.lower():
            try:
                parts = line.split()
                for i, p in enumerate(parts):
                    if "hops" in p.lower().replace(")", ""):
                        return int(parts[i - 1].strip("("))
            except (ValueError, IndexError):
                pass
    return None


def _extract_degree(lines):
    for line in lines:
        if "degree" in line.lower() or "edges" in line.lower():
            try:
                parts = line.split()
                for i, p in enumerate(parts):
                    if any(w in p.lower() for w in ("degree", "edges")) and i > 0:
                        return int(parts[i - 1])
            except (ValueError, IndexError):
                pass
    return None


def main():
    graph_path = None
    for i, arg in enumerate(sys.argv):
        if arg == "--graph" and i + 1 < len(sys.argv):
            graph_path = Path(sys.argv[i + 1])

    if not graph_path or not graph_path.exists():
        graph_path = PROJECT_ROOT / ".tmp" / "vscode" / "graphify-out" / "graph.json"
        if not graph_path.exists():
            print("Usage: python benchmarks/vscode-bench.py --graph <path>", file=sys.stderr)
            sys.exit(1)

    graph_arg = str(graph_path.resolve())

    # ── Query benchmarks ──
    queries = [
        ("architecture", "how does lifecycle.ts work"),
        ("architecture", "what is the purpose of localize()"),
        ("architecture", "explain how uri.ts is used"),
        ("architecture", "what role does event.ts play"),
        ("dependency", "how does instantiation.ts work"),
        ("dependency", "show dependencies of extensions.ts"),
        ("callgraph", "what calls ICommandService"),
        ("callgraph", "how does workbench contribute to editor services"),
        ("startup", "trace the startup process from main.ts"),
        ("cross-module", "what is the relationship between textModel and editor"),
        ("cross-module", "how does notebook support interact with the editor"),
        ("cross-module", "what connects terminal to the renderer"),
        ("search", "how are keybindings resolved"),
        ("search", "what is the file system provider API"),
        ("statusbar", "how is the status bar implemented"),
    ]

    query_results = []
    print("=== QUERY BENCHMARKS ===")
    for category, q in queries:
        print(f"  [{category}] {q[:60]}...", end=" ", flush=True)
        r = _run_cli(
            ["python3", "-m", "graphify", "query", q, "--graph", graph_arg, "--budget", "2000"],
            timeout=120,
        )
        query_results.append({"category": category, "question": q, **r})
        status = "OK" if r["rc"] == 0 else f"FAIL({r['rc']})"
        print(f"{r['elapsed_ms']}ms, {r['output_lines']} lines [{status}]")

    # ── Path benchmarks ──
    paths = [
        ("lifecycle.ts", "localize()"),
        ("uri.ts", "event.ts"),
        ("instantiation.ts", "IInstantiationService"),
        ("workbench.ts", "editorWorkerService"),
        ("main.ts", "createEditor"),
        ("commandService", "keybindingService"),
        ("textModel", "editor"),
        ("notebook", "cell"),
    ]

    path_results = []
    print("\n=== PATH BENCHMARKS ===")
    for src, tgt in paths:
        print(f"  {src} -> {tgt}...", end=" ", flush=True)
        r = _run_cli(
            ["python3", "-m", "graphify", "path", src, tgt, "--graph", graph_arg],
            timeout=120,
        )
        r["source"] = src
        r["target"] = tgt
        path_results.append(r)
        status = "OK" if r["rc"] == 0 else f"FAIL({r['rc']})"
        hops_str = f"{r['hops']} hops" if r["hops"] else "?"
        print(f"{r['elapsed_ms']}ms, {hops_str} [{status}]")

    # ── Explain benchmarks ──
    explains = [
        "localize()",
        "IInstantiationService",
        "uri.ts",
        "event.ts",
        "CommandCenter",
        "lifecycle.ts",
        "extensions.ts",
        "workbench.ts",
        "textModel",
        "ILanguageService",
    ]

    explain_results = []
    print("\n=== EXPLAIN BENCHMARKS ===")
    for target in explains:
        print(f"  {target}...", end=" ", flush=True)
        r = _run_cli(
            ["python3", "-m", "graphify", "explain", target, "--graph", graph_arg],
            timeout=120,
        )
        r["target"] = target
        explain_results.append(r)
        status = "OK" if r["rc"] == 0 else f"FAIL({r['rc']})"
        deg = r.get("degree", "?")
        print(f"{r['elapsed_ms']}ms, {r['output_lines']} lines [{status}]")

    # ── Processes benchmarks ──
    proc_results = []
    print("\n=== PROCESSES BENCHMARKS ===")
    print("  processes list...", end=" ", flush=True)
    r = _run_cli(
        ["python3", "-m", "graphify", "processes", str(graph_path.parent.parent), "list", "--graph", graph_arg],
        timeout=120,
    )
    proc_results.append({"name": "list", **r})
    print(f"{r['elapsed_ms']}ms [{r['rc']}]")

    # ── Graph stats ──
    graph_stats = {"file_size_mb": round(graph_path.stat().st_size / (1024 * 1024), 1)}
    try:
        with open(graph_path) as f:
            g = json.load(f)
        graph_stats["nodes"] = len(g.get("nodes", []))
        graph_stats["edges"] = len(g.get("links", []))
        graph_stats["schema_version"] = g.get("graph", {}).get("schema_version", "?")
    except Exception as e:
        graph_stats["error"] = str(e)

    # ── Summary ──
    q_times = [r["elapsed_ms"] for r in query_results if r["rc"] == 0]
    p_times = [r["elapsed_ms"] for r in path_results if r["rc"] == 0]
    e_times = [r["elapsed_ms"] for r in explain_results if r["rc"] == 0]

    summary = {
        "query_p50": round(statistics.median(q_times), 1) if q_times else None,
        "query_p95": round(sorted(q_times)[int(len(q_times) * 0.95)], 1) if q_times else None,
        "query_avg": round(statistics.mean(q_times), 1) if q_times else None,
        "query_errors": sum(1 for r in query_results if r["rc"] != 0),
        "query_total": len(query_results),
        "path_p50": round(statistics.median(p_times), 1) if p_times else None,
        "path_p95": round(sorted(p_times)[int(len(p_times) * 0.95)], 1) if p_times else None,
        "path_avg": round(statistics.mean(p_times), 1) if p_times else None,
        "path_errors": sum(1 for r in path_results if r["rc"] != 0),
        "path_total": len(path_results),
        "path_hops_p50": round(statistics.median([r["hops"] for r in path_results if r["hops"] is not None]), 1) if [r["hops"] for r in path_results if r["hops"] is not None] else None,
        "explain_p50": round(statistics.median(e_times), 1) if e_times else None,
        "explain_p95": round(sorted(e_times)[int(len(e_times) * 0.95)], 1) if e_times else None,
        "explain_avg": round(statistics.mean(e_times), 1) if e_times else None,
        "explain_errors": sum(1 for r in explain_results if r["rc"] != 0),
        "explain_total": len(explain_results),
    }

    output = {
        "benchmark": "vscode-swebench",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "graph": graph_stats,
        "summary": summary,
        "queries": query_results,
        "paths": path_results,
        "explains": explain_results,
        "processes": proc_results,
    }

    out_path = BENCHMARKS_DIR / "vscode-swebench.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\nResults saved to {out_path}")
    print(f"\n=== SUMMARY ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
