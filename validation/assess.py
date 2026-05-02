"""
Assessment engine: generates ASSESSMENT.md (human) + metrics.json (CI-gatable).
Reads graph outputs + query_results.json, identifies progress/regressions.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

VALIDATION_DIR = Path(__file__).resolve().parent

METRIC_THRESHOLDS = {
    "nodes_count":          (True,  5, 15),
    "edges_count":          (True,  5, 15),
    "communities_count":    (True,  50, 75),
    "bytes_per_node":       (False, 10, 25),
    "graph_size_mb":        (False, 10, 25),
    "query_bfs_ms_p50":     (False, 50, 100),
    "query_bfs_ms_avg":     (False, 50, 100),
    "path_ms_p50":          (False, 15, 40),
    "path_ms_avg":          (False, 15, 40),
    "explain_ms_p50":       (False, 15, 40),
    "explain_ms_avg":       (False, 15, 40),
    "build_time_s":         (False, 20, 50),
    "cli_query_jaccard":    (True,  10, 25),
    "cli_explain_jaccard":  (True,  10, 25),
    "cli_error_rate":       (False, 10, 30),
    "path_reachability":    (True,  15, 30),
    "degree_parity":        (True,  10, 25),
    "target_hit_rate":      (True,  10, 25),
}


def _try_float(v, default=None):
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def median(vals):
    vals = [v for v in vals if v is not None]
    return round(statistics.median(vals), 1) if vals else 0


def avg(vals):
    vals = [v for v in vals if v is not None]
    return round(statistics.mean(vals), 1) if vals else 0


def fmt(n):
    if n is None:
        return "?"
    if isinstance(n, float):
        return f"{n:.1f}"
    return f"{n:,}"


def jaccard(set_a, set_b):
    if not set_a and not set_b:
        return 1.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union > 0 else 0.0


def load_graph_meta(path):
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        from networkx.readwrite import json_graph
        G = json_graph.node_link_graph(data, edges="links")
        return G
    except Exception:
        return None


def extract_report_meta(report_path):
    try:
        text = report_path.read_text()
        nodes_m = re.search(r"(\d[\d,]*) nodes", text)
        edges_m = re.search(r"(\d[\d,]*) edges", text)
        communities_m = re.search(r"(\d+)\s+communities", text)
        return {
            "nodes": int(nodes_m.group(1).replace(",", "")) if nodes_m else None,
            "edges": int(edges_m.group(1).replace(",", "")) if edges_m else None,
            "communities": int(communities_m.group(1)) if communities_m else None,
        }
    except Exception:
        return {}


def extract_god_nodes(report_path):
    try:
        text = report_path.read_text()
        gods = []
        in_section = False
        for line in text.splitlines():
            if "## God Nodes" in line:
                in_section = True
                continue
            if in_section and line.startswith("#"):
                break
            if in_section and line.strip() and line[0].isdigit():
                parts = line.strip().split(" - ")
                if len(parts) >= 2:
                    name = parts[0].split(" ", 1)[1] if " " in parts[0] else parts[0]
                    gods.append((name, parts[1]))
        return gods
    except Exception:
        return []


def collect_metrics(out_b, out_c, query_results):
    metrics = {}

    G_b = load_graph_meta(out_b / "graph.json")
    G_c = load_graph_meta(out_c / "graph.json")

    if G_b:
        metrics["b_nodes"] = G_b.number_of_nodes()
        metrics["b_edges"] = G_b.number_of_edges()
    if G_c:
        metrics["c_nodes"] = G_c.number_of_nodes()
        metrics["c_edges"] = G_c.number_of_edges()

    for prefix, p in [("b", out_b / "graph.json"), ("c", out_c / "graph.json")]:
        if p.exists():
            sz = p.stat().st_size
            metrics[f"{prefix}_graph_size_mb"] = round(sz / 1048576, 1)
    for prefix, G, p in [("b", G_b, out_b / "graph.json"), ("c", G_c, out_c / "graph.json")]:
        if G and p.exists():
            metrics[f"{prefix}_bytes_per_node"] = p.stat().st_size // max(G.number_of_nodes(), 1)

    for prefix, p in [("b", out_b / "build_time.txt"), ("c", out_c / "build_time.txt")]:
        if p.exists():
            metrics[f"{prefix}_build_time_s"] = _try_float(p.read_text().strip())

    for prefix, p in [("b", out_b / "GRAPH_REPORT.md"), ("c", out_c / "GRAPH_REPORT.md")]:
        meta = extract_report_meta(p)
        metrics[f"{prefix}_communities"] = meta.get("communities")
        gods = extract_god_nodes(p)
        metrics[f"{prefix}_god_nodes"] = len(gods)

    # Internal benchmarks
    if query_results:
        bench_map = {
            "query": "bench_query",
            "path": "bench_path",
            "explain": "bench_explain",
        }
        for cat, key in bench_map.items():
            bench = query_results.get(key, [])
            if bench:
                b_ms = [e["b"]["time_ms"] for e in bench]
                c_ms = [e["c"]["time_ms"] for e in bench]
                if b_ms:
                    metrics[f"b_{cat}_ms_p50"] = median(b_ms)
                    metrics[f"b_{cat}_ms_avg"] = avg(b_ms)
                if c_ms:
                    metrics[f"c_{cat}_ms_p50"] = median(c_ms)
                    metrics[f"c_{cat}_ms_avg"] = avg(c_ms)

        # Error rates from CLI results
        for cat in ("query", "path", "explain"):
            results = query_results.get(cat, [])
            if results:
                b_err = sum(1 for r in results if r.get("b_err"))
                c_err = sum(1 for r in results if r.get("c_err"))
                metrics[f"b_{cat}_errors"] = b_err
                metrics[f"c_{cat}_errors"] = c_err

        # Jaccard overlap
        results = query_results.get("query", [])
        if results:
            jaccs = []
            for r in results:
                b_nodes = set(r.get("b_nodes", []))
                c_nodes = set(r.get("c_nodes", []))
                if b_nodes or c_nodes:
                    jaccs.append(jaccard(b_nodes, c_nodes))
            if jaccs:
                metrics["jaccard_query_vals"] = jaccs
                metrics["cli_query_jaccard"] = round(median(jaccs), 3)

        results = query_results.get("explain", [])
        if results:
            jaccs = []
            for r in results:
                b_n = set(r.get("b_neighbors", []))
                c_n = set(r.get("c_neighbors", []))
                if b_n or c_n:
                    jaccs.append(jaccard(b_n, c_n))
            if jaccs:
                metrics["jaccard_explain_vals"] = jaccs
                metrics["cli_explain_jaccard"] = round(median(jaccs), 3)

        # CLI error rate
        total_cli = 0
        total_err = 0
        for cat in ("query", "path", "explain"):
            results = query_results.get(cat, [])
            for r in results:
                total_cli += 1
                if r.get("c_err"):
                    total_err += 1
        if total_cli > 0:
            metrics["cli_error_rate"] = round((total_err / total_cli) * 100, 1)

        # Path reachability
        results = query_results.get("path", [])
        if results:
            b_reach = sum(1 for r in results if r.get("b_hops", -1) > 0)
            c_reach = sum(1 for r in results if r.get("c_hops", -1) > 0)
            total = len(results) or 1
            metrics["b_path_reachability"] = round((b_reach / total) * 100, 1)
            metrics["path_reachability"] = round((c_reach / total) * 100, 1)

        # Degree parity
        results = query_results.get("explain", [])
        if results:
            diffs = []
            for r in results:
                bd = r.get("b_deg")
                cd = r.get("c_deg")
                if bd is not None and cd is not None and bd > 0 and cd > 0:
                    diffs.append(abs(bd - cd) / max(bd, cd))
            if diffs:
                metrics["degree_parity"] = round(100 - (median(diffs) * 100), 1)

        # Target hit rate: does the query return the node it asked about?
        results = query_results.get("query", [])
        if results:
            b_hits = 0
            c_hits = 0
            for r in results:
                label = r.get("label", "")
                target = label
                for tmpl_prefix, tmpl_suffix in [
                    ("how does ", " work"),
                    ("what is the purpose of ", ""),
                    ("explain how ", " is used"),
                    ("what role does ", " play"),
                    ("describe the function of ", ""),
                ]:
                    if label.startswith(tmpl_prefix) and (not tmpl_suffix or label.endswith(tmpl_suffix)):
                        target = label[len(tmpl_prefix):]
                        if tmpl_suffix:
                            target = target[:-len(tmpl_suffix)]
                        break
                b_nodes = r.get("b_nodes", [])
                c_nodes = r.get("c_nodes", [])
                if any(target in n for n in b_nodes):
                    b_hits += 1
                if any(target in n for n in c_nodes):
                    c_hits += 1
            total = len(results) or 1
            metrics["b_target_hit_rate"] = round((b_hits / total) * 100, 1)
            metrics["target_hit_rate"] = round((c_hits / total) * 100, 1)

    return metrics


def assess_metrics(metrics):
    verdicts = {}
    for name, (higher_is_better, warn_pct, fail_pct) in METRIC_THRESHOLDS.items():
        if name.startswith("query_bfs"):
            b_val = metrics.get("b_query_ms_p50")
            c_val = metrics.get("c_query_ms_p50")
        elif name.startswith("query_bfs_ms_avg"):
            b_val = metrics.get("b_query_ms_avg")
            c_val = metrics.get("c_query_ms_avg")
        elif name.startswith("path_ms_p50"):
            b_val = metrics.get("b_path_ms_p50")
            c_val = metrics.get("c_path_ms_p50")
        elif name.startswith("path_ms_avg"):
            b_val = metrics.get("b_path_ms_avg")
            c_val = metrics.get("c_path_ms_avg")
        elif name.startswith("explain_ms_p50"):
            b_val = metrics.get("b_explain_ms_p50")
            c_val = metrics.get("c_explain_ms_p50")
        elif name.startswith("explain_ms_avg"):
            b_val = metrics.get("b_explain_ms_avg")
            c_val = metrics.get("c_explain_ms_avg")
        elif name == "nodes_count":
            b_val = metrics.get("b_nodes")
            c_val = metrics.get("c_nodes")
        elif name == "edges_count":
            b_val = metrics.get("b_edges")
            c_val = metrics.get("c_edges")
        elif name == "communities_count":
            b_val = metrics.get("b_communities")
            c_val = metrics.get("c_communities")
        elif name == "bytes_per_node":
            b_val = metrics.get("b_bytes_per_node")
            c_val = metrics.get("c_bytes_per_node")
        elif name == "graph_size_mb":
            b_val = metrics.get("b_graph_size_mb")
            c_val = metrics.get("c_graph_size_mb")
        elif name == "build_time_s":
            b_val = metrics.get("b_build_time_s")
            c_val = metrics.get("c_build_time_s")
        elif name == "cli_query_jaccard":
            b_val, c_val = None, metrics.get("cli_query_jaccard")
        elif name == "cli_explain_jaccard":
            b_val, c_val = None, metrics.get("cli_explain_jaccard")
        elif name == "cli_error_rate":
            b_val, c_val = None, metrics.get("cli_error_rate")
        elif name == "path_reachability":
            b_val = metrics.get("b_path_reachability")
            c_val = metrics.get("path_reachability")
        elif name == "degree_parity":
            b_val, c_val = None, metrics.get("degree_parity")
        elif name == "target_hit_rate":
            b_val = metrics.get("b_target_hit_rate")
            c_val = metrics.get("target_hit_rate")
        else:
            continue

        if b_val is None and c_val is None:
            continue

        b_val = b_val or 0
        c_val = c_val or 0

        if b_val == 0 and c_val == 0:
            continue

        if b_val != 0:
            delta_pct = ((c_val - b_val) / abs(b_val)) * 100
        else:
            delta_pct = 0

        if higher_is_better:
            is_worse = c_val < b_val
        else:
            is_worse = c_val > b_val

        if not is_worse:
            verdict = "pass"
        else:
            abs_pct = abs(delta_pct)
            if abs_pct >= fail_pct:
                verdict = "fail"
            elif abs_pct >= warn_pct:
                verdict = "warn"
            else:
                verdict = "pass"

        verdicts[name] = (verdict, delta_pct, b_val, c_val)

    return verdicts


def _recommendation(name, delta_pct):
    recs = {
        "nodes_count": ("Check `extract.py` for tree-sitter query coverage. Missing nodes suggest parser gaps.", ""),
        "edges_count": ("Inspect `build.py` edge construction logic. Fewer edges may indicate relationship resolution bug.", ""),
        "communities_count": ("Review `cluster.py` Leiden parameters. Different community count suggests structural change.", ""),
        "bytes_per_node": ("Check JSON serialization. Growth may indicate unpruned node attributes.", ""),
        "graph_size_mb": ("Run `ls -la` on graph.json. Growth without node count change suggests bloated metadata.", ""),
        "query_bfs_ms_p50": ("Profile BFS latency. Check search modules for unnecessary graph copies.", ""),
        "path_ms_p50": ("Profile shortest_path. Check if graph is rebuilt/loaded lazily on each call.", ""),
        "explain_ms_p50": ("Profile explain node resolution. Check for full graph traversal in context().", ""),
        "build_time_s": ("Profile `graphify update`. Check for repeated file I/O in extract pipeline.", ""),
        "cli_query_jaccard": ("Query result divergence. Check if node labels or scoring changed in search/hybrid.py.", ""),
        "cli_explain_jaccard": ("Check explain neighbor traversal logic. Jaccard drop means different subgraph returned.", ""),
        "cli_error_rate": ("More CLI errors. Check CLI argument parsing or file I/O timeout handling.", ""),
        "path_reachability": ("Paths lost. Check if graph connectivity changed (edge pruning, node removal).", ""),
        "degree_parity": ("Node degree divergence. Check edge construction for recently changed modules.", ""),
        "target_hit_rate": ("Query target presence dropped. Check if query scorer changed or edge model lost relevant connections.", ""),
    }
    rec = recs.get(name, ("Investigate recent changes in graphify/ core modules.", ""))
    return rec[0]


def generate_assessment(run_dir, out_b, out_c, query_results, prev_metrics=None):
    metrics = collect_metrics(out_b, out_c, query_results)

    metrics_path = run_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, default=str))

    verdicts = assess_metrics(metrics)

    lines = []
    lines.append("# Validation Assessment")
    lines.append("")
    lines.append(f"**Run:** `{run_dir.name}`")
    lines.append(f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}")
    if "b_nodes" in metrics and "c_nodes" in metrics:
        lines.append(f"**Baseline:** {fmt(metrics['b_nodes'])} nodes, {fmt(metrics['b_edges'])} edges")
        lines.append(f"**Current:**  {fmt(metrics['c_nodes'])} nodes, {fmt(metrics['c_edges'])} edges")
    lines.append("")

    n_pass = sum(1 for v, _, _, _ in verdicts.values() if v == "pass")
    n_warn = sum(1 for v, _, _, _ in verdicts.values() if v == "warn")
    n_fail = sum(1 for v, _, _, _ in verdicts.values() if v == "fail")
    overall = "FAIL" if n_fail > 0 else "WARN" if n_warn > 0 else "PASS"

    lines.append("## Summary")
    lines.append(f"- **PASS:** {n_pass}")
    lines.append(f"- **WARN:** {n_warn}")
    lines.append(f"- **FAIL:** {n_fail}")
    lines.append(f"- **Overall:** **{overall}**")
    lines.append("")

    lines.append("## Detailed Verdicts")
    lines.append("")
    lines.append("| Metric | Baseline | Current | Delta % | Verdict |")
    lines.append("|--------|----------|---------|---------|---------|")
    for name, (verdict, delta_pct, b_val, c_val) in sorted(verdicts.items()):
        sign = "+" if delta_pct >= 0 else ""
        emoji = {"pass": "✓", "warn": "⚠", "fail": "✗"}.get(verdict, "?")
        b_s = f"{b_val:.1f}" if isinstance(b_val, float) else fmt(b_val)
        c_s = f"{c_val:.1f}" if isinstance(c_val, float) else fmt(c_val)
        lines.append(f"| {name} | {b_s} | {c_s} | {sign}{delta_pct:.1f}% | {emoji} {verdict} |")
    lines.append("")

    regressions = sorted(
        [(n, v, d, bv, cv) for n, (v, d, bv, cv) in verdicts.items() if v in ("warn", "fail")],
        key=lambda r: abs(r[2]), reverse=True,
    )
    improvements = sorted(
        [(n, d, bv, cv) for n, (v, d, bv, cv) in verdicts.items()
         if v == "pass" and (
             (d > 0 and METRIC_THRESHOLDS.get(n, (None,))[0]) or
             (d < 0 and not METRIC_THRESHOLDS.get(n, (None,))[0])
         )],
        key=lambda i: abs(i[1]), reverse=True,
    )

    if regressions:
        lines.append("## Top Regressions")
        lines.append("")
        for name, verdict, delta_pct, b_val, c_val in regressions[:5]:
            lines.append(f"- **{name}**: {fmt(b_val)} → {fmt(c_val)} ({delta_pct:+.1f}%) [{verdict.upper()}]")
        lines.append("")

    if improvements:
        lines.append("## Top Improvements")
        lines.append("")
        for name, delta_pct, b_val, c_val in improvements[:5]:
            lines.append(f"- **{name}**: {fmt(b_val)} → {fmt(c_val)} ({delta_pct:+.1f}%)")
        lines.append("")

    lines.append("## What's Best Next")
    lines.append("")

    if regressions:
        for name, verdict, delta_pct, b_val, c_val in regressions[:3]:
            rec = _recommendation(name, delta_pct)
            lines.append(f"- **{name}** ({delta_pct:+.1f}%): {rec}")
    else:
        lines.append("No regressions detected. Consider:")
        lines.append("- Running on additional corpora (python, go, rust) for language-specific coverage")
        lines.append("- Increasing query count for higher statistical confidence")
        lines.append("- Adding semantic/embedding-based benchmark targets")
    lines.append("")

    lines.append("---")
    lines.append(f"*Generated by assess.py at {time.strftime('%Y-%m-%d %H:%M:%S')}*")

    assess_path = run_dir / "ASSESSMENT.md"
    assess_path.write_text("\n".join(lines))

    return metrics, verdicts


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--against", type=Path)
    args = ap.parse_args()

    run_dir = args.run_dir
    out_b = run_dir / "out-baseline"
    out_c = run_dir / "out-current"

    query_results = {}
    qr_path = run_dir / "query_results.json"
    if qr_path.exists():
        query_results = json.loads(qr_path.read_text())

    prev_metrics = {}
    if args.against:
        am_path = args.against / "metrics.json"
        if am_path.exists():
            prev_metrics = json.loads(am_path.read_text())

    metrics, verdicts = generate_assessment(run_dir, out_b, out_c, query_results, prev_metrics)
    print(f"  Assessment: {run_dir / 'ASSESSMENT.md'}")
    print(f"  Metrics:    {run_dir / 'metrics.json'}")

    n_fail = sum(1 for _, (v, _, _, _) in verdicts.items() if v == "fail")
    if n_fail > 0:
        print(f"  {n_fail} metrics FAILED thresholds")
        sys.exit(1)


if __name__ == "__main__":
    main()
