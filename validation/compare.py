"""Comprehensive comparison engine: structure, performance, quality, correctness."""

import json
import re
import statistics
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import ValidationConfig


def pct(a, b):
    if a == 0:
        return "+inf%" if b > 0 else "0%"
    return f"{((b - a) / a) * 100:+.0f}%"


def fmt(n):
    return f"{n:,}" if n is not None else "?"


def mb(path):
    if not path or not path.exists():
        return "?"
    return f"{path.stat().st_size / 1048576:.0f} MB"


def load_graph(path):
    if not path or not path.exists():
        return None
    try:
        import networkx as nx
        from networkx.readwrite import json_graph
        data = json.loads(path.read_text())
        return json_graph.node_link_graph(data, edges="links")
    except Exception:
        return None


def jaccard(set_a, set_b):
    if not set_a and not set_b:
        return 1.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union > 0 else 0.0


def median(vals):
    vals = [v for v in vals if v is not None]
    return round(statistics.median(vals), 1) if vals else 0


def avg(vals):
    vals = [v for v in vals if v is not None]
    return round(statistics.mean(vals), 1) if vals else 0


def extract_god_nodes(md_path):
    try:
        text = md_path.read_text()
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


def extract_communities(md_path):
    try:
        for line in md_path.read_text().splitlines():
            m = re.search(r"(\d+)\s+communities", line)
            if m:
                return int(m.group(1))
    except Exception:
        pass
    return 0


def discover_targets(G_b, G_c):
    deg_b = {data.get("label", nid): G_b.degree(nid) for nid, data in G_b.nodes(data=True)}
    deg_c = {data.get("label", nid): G_c.degree(nid) for nid, data in G_c.nodes(data=True)}
    common = sorted(
        set(deg_b) & set(deg_c),
        key=lambda l: max(deg_b[l], deg_c[l]),
        reverse=True,
    )
    return common, deg_b, deg_c


def _score_nodes(G, terms):
    scored = []
    for nid, ndata in G.nodes(data=True):
        label = ndata.get("label", "").lower()
        score = sum(1 for t in terms if t in label)
        if score > 0:
            scored.append((score, nid))
    scored.sort(reverse=True)
    return scored


def run_bfs_bench(G, question, depth=3):
    terms = [t.lower() for t in question.split() if len(t) > 2]
    import time
    t0 = time.perf_counter()
    scored = _score_nodes(G, terms)
    if not scored:
        return {"time_ms": 0, "nodes": 0, "edges": 0}
    start = [nid for _, nid in scored[:3]]
    visited = set(start)
    frontier = set(start)
    edges_list = []
    for _ in range(depth):
        nf = set()
        for n in frontier:
            for nb in G.neighbors(n):
                if nb not in visited:
                    nf.add(nb)
                    edges_list.append((n, nb))
        visited.update(nf)
        frontier = nf
    return {
        "time_ms": round((time.perf_counter() - t0) * 1000, 2),
        "nodes": len(visited),
        "edges": len(edges_list),
    }


def run_path_bench(G, a, b):
    import time
    t0 = time.perf_counter()
    scored_a = _score_nodes(G, [t.lower() for t in a.split()])
    scored_b = _score_nodes(G, [t.lower() for t in b.split()])
    if not scored_a or not scored_b:
        return {"time_ms": 0, "hops": -1}
    src, tgt = scored_a[0][1], scored_b[0][1]
    try:
        import networkx as nx
        hops = len(nx.shortest_path(G, src, tgt)) - 1
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        hops = -1
    return {"time_ms": round((time.perf_counter() - t0) * 1000, 2), "hops": hops}


def run_explain_bench(G, term):
    import time
    t0 = time.perf_counter()
    scored = _score_nodes(G, [t.lower() for t in term.split()])
    if not scored:
        return {"time_ms": 0, "degree": 0, "neighbors": 0}
    nid = scored[0][1]
    deg = G.degree(nid)
    n_neighbors = len(list(G.neighbors(nid)))
    return {
        "time_ms": round((time.perf_counter() - t0) * 1000, 2),
        "degree": deg,
        "neighbors": n_neighbors,
    }


_QUERY_TEMPLATES = [
    "how does {} work",
    "what is the purpose of {}",
    "explain how {} is used",
    "what role does {} play",
    "describe the function of {}",
]

NUM_QUERIES = 10
NUM_PATHS = 5
NUM_EXPLAINS = 10


def generate_targets(common_labels):
    queries = []
    for i, label in enumerate(common_labels[:NUM_QUERIES]):
        tmpl = _QUERY_TEMPLATES[i % len(_QUERY_TEMPLATES)]
        queries.append(tmpl.format(label))

    paths = []
    top = common_labels[:NUM_PATHS * 2]
    for i in range(0, len(top), 2):
        if i + 1 < len(top):
            paths.append((top[i], top[i + 1]))

    explains = common_labels[:NUM_EXPLAINS]
    return queries, paths, explains


def compare_structure(out_b, out_c):
    """Compare graph structure: nodes, edges, communities, god nodes, size."""
    G_b = load_graph(out_b / "graph.json")
    G_c = load_graph(out_c / "graph.json")

    if not G_b or not G_c:
        return {"error": "Graphs could not be loaded"}

    return {
        "nodes": (G_b.number_of_nodes(), G_c.number_of_nodes()),
        "edges": (G_b.number_of_edges(), G_c.number_of_edges()),
        "edge_density": (
            round(G_b.number_of_edges() / max(G_b.number_of_nodes(), 1), 3),
            round(G_c.number_of_edges() / max(G_c.number_of_nodes(), 1), 3),
        ),
        "communities": (
            extract_communities(out_b / "GRAPH_REPORT.md"),
            extract_communities(out_c / "GRAPH_REPORT.md"),
        ),
        "god_nodes": (
            extract_god_nodes(out_b / "GRAPH_REPORT.md"),
            extract_god_nodes(out_c / "GRAPH_REPORT.md"),
        ),
        "size_mb": (
            mb(out_b / "graph.json"),
            mb(out_c / "graph.json"),
        ),
    }


def compare_performance(query_results):
    """Extract performance metrics from benchmark data."""
    perf = {}

    bench_map = {
        "query": "bench_query",
        "path": "bench_path",
        "explain": "bench_explain",
    }
    for cat, key in bench_map.items():
        bench = query_results.get(key, [])
        if not bench:
            continue
        b_ms = [e["b"]["time_ms"] for e in bench]
        c_ms = [e["c"]["time_ms"] for e in bench]
        perf[f"{cat}_median"] = (median(b_ms), median(c_ms))
        perf[f"{cat}_avg"] = (avg(b_ms), avg(c_ms))

    return perf


def compare_quality(query_results):
    """Compute Jaccard, error rates, degree parity from CLI results."""
    quality = {}

    for cat in ("query", "path", "explain"):
        results = query_results.get(cat, [])
        if not results:
            continue
        b_err = sum(1 for r in results if r.get("b_err"))
        c_err = sum(1 for r in results if r.get("c_err"))
        quality[f"{cat}_errors"] = (b_err, c_err)

    if "query" in query_results:
        jq_b, jq_c = [], []
        for r in query_results["query"]:
            b_nodes = r.get("b_nodes", [])
            c_nodes = r.get("c_nodes", [])
            if b_nodes or c_nodes:
                jq_b.append(set(b_nodes))
                jq_c.append(set(c_nodes))
        if jq_b and jq_c:
            jacc = [jaccard(a, b) for a, b in zip(jq_b, jq_c)]
            quality["query_jaccard"] = jacc

    if "explain" in query_results:
        je_b, je_c = [], []
        for r in query_results["explain"]:
            b_neighbors = r.get("b_neighbors", [])
            c_neighbors = r.get("c_neighbors", [])
            if b_neighbors or c_neighbors:
                je_b.append(set(b_neighbors))
                je_c.append(set(c_neighbors))
        if je_b and je_c:
            jacc = [jaccard(a, b) for a, b in zip(je_b, je_c)]
            quality["explain_jaccard"] = jacc

    return quality


def compare_correctness_from_query(query_results):
    """Extract path reachability from CLI results."""
    results = query_results.get("path", [])
    if not results:
        return {}
    b_reach = sum(1 for r in results if r.get("b_hops", -1) > 0)
    c_reach = sum(1 for r in results if r.get("c_hops", -1) > 0)
    return {
        "path_reachability": (b_reach, c_reach, len(results)),
    }


def compare_correctness(G_b, G_c, common_labels, query_results):
    """Compare path reachability and degree parity."""
    correctness = {"reachable_both": 0, "reachable_neither": 0, "b_only": 0, "c_only": 0,
                   "degree_diffs": []}

    for label in common_labels[:50]:
        matches_b = [nid for nid, nd in G_b.nodes(data=True) if nd.get("label") == label]
        matches_c = [nid for nid, nd in G_c.nodes(data=True) if nd.get("label") == label]
        if matches_b and matches_c:
            deg_b = G_b.degree(matches_b[0])
            deg_c = G_c.degree(matches_c[0])
            correctness["degree_diffs"].append(abs(deg_b - deg_c))

    rc = compare_correctness_from_query(query_results)
    if rc:
        correctness["path_reachability"] = rc["path_reachability"]

    return correctness


def render_report(run_dir, structure, performance, quality, correctness,
                  common_labels, deg_b_map, deg_c_map,
                  gods_b, gods_c):
    """Generate COMPARISON.md."""
    lines = []
    lines.append("# Graphify Apple-to-Apple: Comprehensive Comparison")
    lines.append(f"**Run:** {run_dir.name}")
    lines.append("")

    lines.append("## Structure")
    lines.append("")
    lines.append("| Metric | Baseline | Current | Delta |")
    lines.append("|--------|----------|---------|-------|")
    s = structure
    lines.append(f"| Nodes | {fmt(s['nodes'][0])} | {fmt(s['nodes'][1])} | {pct(s['nodes'][0], s['nodes'][1])} |")
    lines.append(f"| Edges | {fmt(s['edges'][0])} | {fmt(s['edges'][1])} | {pct(s['edges'][0], s['edges'][1])} |")
    lines.append(f"| Edge density | {s['edge_density'][0]} | {s['edge_density'][1]} | |")
    lines.append(f"| Communities | {s['communities'][0]} | {s['communities'][1]} | {pct(s['communities'][0] or 0, s['communities'][1] or 0)} |")
    lines.append(f"| graph.json size | {s['size_mb'][0]} | {s['size_mb'][1]} | |")
    lines.append(f"| Common labels | {len(common_labels)} | | |")
    lines.append("")

    if performance:
        lines.append("## Performance")
        lines.append("")
        lines.append("| Metric | Baseline | Current | Delta |")
        lines.append("|--------|----------|---------|-------|")
        for label, (b, c) in sorted(performance.items()):
            lines.append(f"| {label} | {b}ms | {c}ms | {pct(b, c)} |")
        lines.append("")

    if quality:
        lines.append("## Quality")
        lines.append("")
        for label, val in quality.items():
            if isinstance(val, list):
                lines.append(f"- **{label}** (Jaccard median): {median(val):.3f}")
            else:
                lines.append(f"- **{label}**: {val[0]} → {val[1]}")
        lines.append("")

    lines.append("## God Nodes")
    lines.append("")
    lines.append("### Baseline (top 10)")
    for i, (name, desc) in enumerate(gods_b[:10]):
        lines.append(f"{i+1}. {name} - {desc}")
    lines.append("")
    lines.append("### Current (top 10)")
    for i, (name, desc) in enumerate(gods_c[:10]):
        lines.append(f"{i+1}. {name} - {desc}")
    lines.append("")

    lines.append("## Common Labels (top 20 by max degree)")
    lines.append("")
    lines.append("| # | Label | Baseline deg | Current deg |")
    lines.append("|---|---|---|---|")
    for i, label in enumerate(common_labels[:20]):
        db = deg_b_map.get(label, 0)
        dc = deg_c_map.get(label, 0)
        lines.append(f"| {i+1} | `{label[:45]}` | {fmt(db)} | {fmt(dc)} |")
    lines.append("")

    lines.append("---")
    lines.append(f"*Generated at {run_dir.name}*")

    report_path = run_dir / "COMPARISON.md"
    report_path.write_text("\n".join(lines))
    return report_path


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--out-b", required=True, type=Path)
    ap.add_argument("--out-c", required=True, type=Path)
    ap.add_argument("--against", type=Path)
    ap.add_argument("--structure-only", action="store_true")
    args = ap.parse_args()

    run_dir = args.run_dir

    G_b = load_graph(args.out_b / "graph.json")
    G_c = load_graph(args.out_c / "graph.json")

    if not G_b or not G_c:
        print("ERROR: Cannot load graphs for comparison")
        return

    structure = compare_structure(args.out_b, args.out_c)
    common_labels, deg_b_map, deg_c_map = discover_targets(G_b, G_c)

    gods_b = extract_god_nodes(args.out_b / "GRAPH_REPORT.md")
    gods_c = extract_god_nodes(args.out_c / "GRAPH_REPORT.md")

    query_results = {}
    qr_path = args.run_dir / "query_results.json"
    if qr_path.exists():
        query_results = json.loads(qr_path.read_text())

    performance = compare_performance(query_results)
    quality = compare_quality(query_results)
    correctness = compare_correctness(G_b, G_c, common_labels, query_results)

    report_path = render_report(
        run_dir, structure, performance, quality, correctness,
        common_labels, deg_b_map, deg_c_map, gods_b, gods_c,
    )
    print(f"  Report: {report_path}")


if __name__ == "__main__":
    main()
