"""
Query execution engine: runs CLI queries + internal networkx benchmarks
on both baseline and current graphs. Outputs query_results.json.
"""

import json
import re
import subprocess
import statistics
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph

NUM_QUERIES = 10
NUM_PATHS = 5
NUM_EXPLAINS = 10
CLI_TIMEOUT = 60
NUM_WORKERS = 4

_QUERY_TEMPLATES = [
    "how does {} work",
    "what is the purpose of {}",
    "explain how {} is used",
    "what role does {} play",
    "describe the function of {}",
]


def pct(a, b):
    if a == 0:
        return "+inf%" if b > 0 else "0%"
    return f"{((b - a) / a) * 100:+.0f}%"


def fmt(n):
    return f"{n:,}"


def mb(path):
    if not path.exists():
        return "?"
    return f"{path.stat().st_size / 1048576:.0f} MB"


def load_graph(path):
    data = json.loads(path.read_text())
    return json_graph.node_link_graph(data, edges="links")


def get_version(venv_path):
    try:
        r = subprocess.run(
            [str(venv_path / "bin" / "pip"), "show", "graphifyy"],
            capture_output=True, text=True,
        )
        for line in r.stdout.splitlines():
            if line.startswith("Version:"):
                return line.split(":")[1].strip()
    except Exception:
        pass
    return "?"


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
                if len(gods) >= 10:
                    break
        return gods
    except Exception:
        return []


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
    t0 = time.perf_counter()
    scored_a = _score_nodes(G, [t.lower() for t in a.split()])
    scored_b = _score_nodes(G, [t.lower() for t in b.split()])
    if not scored_a or not scored_b:
        return {"time_ms": 0, "hops": -1}
    src, tgt = scored_a[0][1], scored_b[0][1]
    try:
        hops = len(nx.shortest_path(G, src, tgt)) - 1
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        hops = -1
    return {"time_ms": round((time.perf_counter() - t0) * 1000, 2), "hops": hops}


def run_explain_bench(G, term):
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


def _trunc(text, n):
    return text if len(text) <= n else text[:n] + "..."


def discover_targets(G_b, G_s):
    deg_b = {data.get("label", nid): G_b.degree(nid) for nid, data in G_b.nodes(data=True)}
    deg_s = {data.get("label", nid): G_s.degree(nid) for nid, data in G_s.nodes(data=True)}
    common = sorted(
        set(deg_b) & set(deg_s),
        key=lambda l: max(deg_b[l], deg_s[l]),
        reverse=True,
    )
    return common, deg_b, deg_s


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


# ── CLI execution ─────────────────────────────────────────────────

def _run_cli(venv, cmd, *args):
    full = [str(venv / "bin" / "graphify")] + list(cmd) + list(args)
    try:
        r = subprocess.run(full, capture_output=True, text=True, timeout=CLI_TIMEOUT)
        out = r.stdout
        if r.returncode != 0:
            out += f"\n(exit {r.returncode})"
        if r.stderr:
            out = r.stderr.rstrip() + "\n" + out
        return out.strip()
    except subprocess.TimeoutExpired:
        return f"(timeout after {CLI_TIMEOUT}s)"
    except Exception as exc:
        return f"(error: {exc})"


def _parse_query_nodes(text):
    nodes = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("NODE "):
            label = s[5:].split(" src=")[0].strip()
            if label:
                nodes.append(label)
    return nodes


def _parse_explain_neighbors(text):
    """Parse all neighbor labels from categorized explain output.
    Handles: ← label [...] for incoming, → label [...] for outgoing,
    standalone label [...] for imports/other."""
    neighbors = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("← ") or s.startswith("→ "):
            label = s[2:].split(" [")[0].strip()
            if label:
                neighbors.append(label)
        elif (s.startswith("Node:") or s.startswith("ID:") or s.startswith("Source:")
              or s.startswith("Type:") or s.startswith("Community:") or s.startswith("Degree:")
              or s.startswith("Incoming") or s.startswith("Outgoing") or s.startswith("Imports")
              or s.startswith("Process") or s.startswith("Other") or s.startswith("...") or s == ""):
            continue
        elif " [" in s:
            label = s.split(" [")[0].strip()
            if label:
                neighbors.append(label)
    return neighbors


def _parse_explain_degree(text):
    degree = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("Degree:"):
            try:
                degree = int(s.split(":")[1].strip())
            except ValueError:
                pass
    if degree is None and "No node matching" in text:
        degree = -1
    return degree


def _parse_path_hops(text):
    for line in text.splitlines():
        s = line.strip()
        m = re.search(r"(\d+) hops?", s)
        if m:
            return int(m.group(1))
    return -1


def _run_pair(venv_b, venv_c, cmd, args_b, args_c):
    out_b = _run_cli(venv_b, cmd, *args_b)
    out_c = _run_cli(venv_c, cmd, *args_c)
    return out_b, out_c


def run_all_queries(venv_b, venv_c, out_b, out_c, queries, paths, explains):
    results = {}

    # Query
    print("  Running query commands...")
    results["query"] = []
    total = len(queries)
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as ex:
        futures = {}
        for i, q in enumerate(queries):
            args_b = (q, "--graph", str(out_b / "graph.json"))
            args_c = (q, "--graph", str(out_c / "graph.json"))
            fut = ex.submit(_run_pair, venv_b, venv_c, ["query"], args_b, args_c)
            futures[fut] = (i, q)
            print(f"    [{i+1}/{total}] query `{_trunc(q, 50)}`")

        for fut in as_completed(futures):
            i, q_label = futures[fut]
            out_b_str, out_c_str = fut.result()
            results["query"].append({
                "idx": i,
                "label": q_label,
                "b_out": out_b_str,
                "c_out": out_c_str,
                "b_err": "error" in out_b_str.lower()[:200] or "traceback" in out_b_str.lower()[:200],
                "c_err": "error" in out_c_str.lower()[:200] or "traceback" in out_c_str.lower()[:200],
                "b_nodes": _parse_query_nodes(out_b_str),
                "c_nodes": _parse_query_nodes(out_c_str),
            })

    results["query"].sort(key=lambda r: r["idx"])

    # Path
    print("  Running path commands...")
    results["path"] = []
    total = len(paths)
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as ex:
        futures = {}
        for i, (a, b) in enumerate(paths):
            args_b = (a, b, "--graph", str(out_b / "graph.json"))
            args_c = (a, b, "--graph", str(out_c / "graph.json"))
            fut = ex.submit(_run_pair, venv_b, venv_c, ["path"], args_b, args_c)
            futures[fut] = (i, f"{a} -> {b}")
            print(f"    [{i+1}/{total}] path `{_trunc(a, 25)}` → `{_trunc(b, 25)}`")

        for fut in as_completed(futures):
            i, p_label = futures[fut]
            out_b_str, out_c_str = fut.result()
            results["path"].append({
                "idx": i,
                "label": p_label,
                "b_out": out_b_str,
                "c_out": out_c_str,
                "b_err": "error" in out_b_str.lower()[:200] or "traceback" in out_b_str.lower()[:200],
                "c_err": "error" in out_c_str.lower()[:200] or "traceback" in out_c_str.lower()[:200],
                "b_hops": _parse_path_hops(out_b_str),
                "c_hops": _parse_path_hops(out_c_str),
            })

    results["path"].sort(key=lambda r: r["idx"])

    # Explain
    print("  Running explain commands...")
    results["explain"] = []
    total = len(explains)
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as ex:
        futures = {}
        for i, label in enumerate(explains):
            args_b = (label, "--graph", str(out_b / "graph.json"))
            args_c = (label, "--graph", str(out_c / "graph.json"))
            fut = ex.submit(_run_pair, venv_b, venv_c, ["explain"], args_b, args_c)
            futures[fut] = (i, label)
            print(f"    [{i+1}/{total}] explain `{_trunc(label, 50)}`")

        for fut in as_completed(futures):
            i, e_label = futures[fut]
            out_b_str, out_c_str = fut.result()
            b_deg = _parse_explain_degree(out_b_str)
            c_deg = _parse_explain_degree(out_c_str)
            results["explain"].append({
                "idx": i,
                "label": e_label,
                "b_out": out_b_str,
                "c_out": out_c_str,
                "b_err": "error" in out_b_str.lower()[:200] or "traceback" in out_b_str.lower()[:200],
                "c_err": "error" in out_c_str.lower()[:200] or "traceback" in out_c_str.lower()[:200],
                "b_deg": b_deg,
                "c_deg": c_deg,
                "b_neighbors": _parse_explain_neighbors(out_b_str),
                "c_neighbors": _parse_explain_neighbors(out_c_str),
            })

    results["explain"].sort(key=lambda r: r["idx"])

    return results


# ── Main ──────────────────────────────────────────────────────────

def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--out-b", required=True, type=Path)
    ap.add_argument("--out-c", required=True, type=Path)
    ap.add_argument("--venv-b", required=True, type=Path)
    ap.add_argument("--venv-c", required=True, type=Path)
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--skip-queries", action="store_true")
    args = ap.parse_args()

    gb = args.out_b / "graph.json"
    gc = args.out_c / "graph.json"

    [p.exists() or sys.exit(f"graph not found: {p}") for p in (gb, gc)]

    G_b = load_graph(gb)
    G_c = load_graph(gc)

    common_labels, deg_b_map, deg_c_map = discover_targets(G_b, G_c)
    queries, paths, explains = generate_targets(common_labels)

    print(f"Targets: {len(queries)} queries, {len(paths)} paths, {len(explains)} explains")
    print(f"Common labels: {len(common_labels)}")

    if args.skip_queries:
        print("Skipping CLI queries (--skip-queries)")
        query_results = {"query": [], "path": [], "explain": []}
    else:
        print("Running CLI queries (parallel)...")
        t0 = time.perf_counter()
        query_results = run_all_queries(
            args.venv_b, args.venv_c,
            args.out_b, args.out_c,
            queries, paths, explains,
        )
        print(f"  CLI queries completed in {time.perf_counter() - t0:.1f}s")

    # Internal timing benchmarks
    print("Running internal benchmarks...")
    t0 = time.perf_counter()

    for q in queries:
        rb = run_bfs_bench(G_b, q)
        rs = run_bfs_bench(G_c, q)
        query_results.setdefault("bench_query", []).append({"b": rb, "c": rs})

    for a, b in paths:
        rb = run_path_bench(G_b, a, b)
        rs = run_path_bench(G_c, a, b)
        query_results.setdefault("bench_path", []).append({"b": rb, "c": rs})

    for label in explains:
        rb = run_explain_bench(G_b, label)
        rs = run_explain_bench(G_c, label)
        query_results.setdefault("bench_explain", []).append({"b": rb, "c": rs})

    print(f"  Internal benchmarks completed in {time.perf_counter() - t0:.1f}s")

    # Add meta
    query_results["meta"] = {
        "common_labels_count": len(common_labels),
        "common_labels": common_labels[:50],
        "deg_b": {k: deg_b_map.get(k, 0) for k in common_labels[:50]},
        "deg_c": {k: deg_c_map.get(k, 0) for k in common_labels[:50]},
    }

    # Save
    qr_path = args.run_dir / "query_results.json"
    qr_path.write_text(json.dumps(query_results, indent=2, default=str))
    print(f"Query results saved: {qr_path}")


if __name__ == "__main__":
    main()
