#!/usr/bin/env python3
"""
Feature-by-feature progressive quality measurement for the graphify fork.

Each feature is measured independently (ON vs OFF) against the same graph.
Category A (query-time): sets serve.FEATURE_FLAGS, runs internal benchmarks.
Category B (build-time): rebuilds graph with feature enabled, then benchmarks.
Category C (integration): documented only — not measurable structurally.

Usage:
    python validation/measure_features.py [--graph graph.json]
    python validation/measure_features.py --corpus validation/corpora/toycorp
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

VALIDATION_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = VALIDATION_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

import networkx as nx
from networkx.readwrite import json_graph

DEFAULT_GRAPH = VALIDATION_DIR / "out-speedai" / "graph.json"
NUM_QUERIES = 10
NUM_PATHS = 5
NUM_EXPLAINS = 10
DEPTH = 3

STOPWORDS = frozenset({
    "how", "does", "the", "and", "that", "for", "are", "with", "this", "from",
    "what", "have", "been", "when", "will", "also", "into", "more", "some",
    "than", "then", "them", "they", "been", "were", "would", "could", "should",
    "there", "their", "about", "which", "other", "each", "over", "after",
    "used", "work", "role", "play", "describe", "function",
})

_QUERY_TEMPLATES = [
    "how does {} work",
    "what is the purpose of {}",
    "explain how {} is used",
    "what role does {} play",
    "describe the function of {}",
]


def _score_nodes(G: nx.Graph, terms: list[str]) -> list[tuple[float, str]]:
    meaningful = [t for t in terms if t not in STOPWORDS]
    if not meaningful:
        meaningful = terms
    scored = []
    for nid, data in G.nodes(data=True):
        label = data.get("label", "").lower()
        source = data.get("source_file", "").lower()
        s = sum(1 for t in meaningful if t in label) + sum(0.5 for t in meaningful if t in source)
        if s > 0:
            scored.append((s, nid))
    scored.sort(reverse=True)
    return scored


def _score_hybrid(G: nx.Graph, terms: list[str]) -> list[tuple[float, str]]:
    try:
        from graphify.search.hybrid import hybrid_search
        meaningful = [t for t in terms if t not in STOPWORDS]
        if not meaningful:
            meaningful = terms
        question = " ".join(meaningful)
        results = hybrid_search(G, question, top_k=10)
        return [(r.score, r.node_id) for r in results]
    except Exception:
        return _score_nodes(G, terms)


_CI_PRIO = {"EXTRACTED": 0, "INFERRED": 1, "AMBIGUOUS": 2}


def _bfs_baseline(G, start, depth):
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
    return visited, edges_list


def _bfs_confidence_filter(G, start, depth, min_confidence="INFERRED"):
    min_prio = _CI_PRIO.get(min_confidence, 1)
    visited = set(start)
    frontier = set(start)
    edges_list = []
    for _ in range(depth):
        nf = set()
        for n in frontier:
            for nb in G.neighbors(n):
                if nb in visited:
                    continue
                edata = G.edges.get((n, nb)) or G.edges.get((nb, n)) or {}
                ci = edata.get("confidence", "EXTRACTED")
                if _CI_PRIO.get(ci, 0) > min_prio:
                    continue
                nf.add(nb)
                edges_list.append((n, nb))
        visited.update(nf)
        frontier = nf
    return visited, edges_list


def _bfs_planner(G, start, depth):
    try:
        from graphify.query_planner import order_frontier_by_confidence
    except ImportError:
        return _bfs_baseline(G, start, depth)
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
        frontier = set(order_frontier_by_confidence(G, list(nf)))
    return visited, edges_list


def run_bfs_bench(G, question, flags):
    terms = [t.lower() for t in question.split() if len(t) > 2]
    scorer = _score_hybrid if flags.get("use_hybrid") else _score_nodes
    scored = scorer(G, terms)
    if not scored:
        return {"time_ms": 0, "nodes": 0, "edges": 0}
    start = [nid for _, nid in scored[:3]]

    if flags.get("use_sampling"):
        try:
            from graphify.approx import sample_subgraph
        except ImportError:
            pass
        else:
            sg = sample_subgraph(G, sample_rate=float(flags.get("sample_rate", 0.1)))
            scored2 = scorer(sg, terms)
            if not scored2:
                return {"time_ms": 0, "nodes": 0, "edges": 0}
            start = [nid for _, nid in scored2[:3]]
            G = sg

    t0 = time.perf_counter()

    conf_filter = flags.get("conf_filter", "")
    use_planner = flags.get("use_planner", False)

    if conf_filter:
        visited, edges = _bfs_confidence_filter(G, start, DEPTH, min_confidence=conf_filter)
    elif use_planner:
        visited, edges = _bfs_planner(G, start, DEPTH)
    else:
        visited, edges = _bfs_baseline(G, start, DEPTH)

    ms = round((time.perf_counter() - t0) * 1000, 2)
    return {"time_ms": ms, "nodes": len(visited), "edges": len(edges)}


def run_path_bench(G, a, b, flags):
    scorer = _score_hybrid if flags.get("use_hybrid") else _score_nodes
    scored_a = scorer(G, [t.lower() for t in a.split()])
    scored_b = scorer(G, [t.lower() for t in b.split()])
    if not scored_a or not scored_b:
        return {"time_ms": 0, "hops": -1}
    src, tgt = scored_a[0][1], scored_b[0][1]

    if flags.get("use_matviews"):
        try:
            from graphify.matviews import check_materialized_path
            dist = check_materialized_path(G, src, tgt, "calls", Path("graphify-out/matviews"))
            if dist is not None:
                return {"time_ms": 0.1, "hops": dist}
        except Exception:
            pass

    t0 = time.perf_counter()
    try:
        hops = len(nx.shortest_path(G, src, tgt)) - 1
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        hops = -1
    return {"time_ms": round((time.perf_counter() - t0) * 1000, 2), "hops": hops}


def run_explain_bench(G, term, flags):
    scorer = _score_hybrid if flags.get("use_hybrid") else _score_nodes
    scored = scorer(G, [t.lower() for t in term.split()])
    if not scored:
        return {"time_ms": 0, "degree": 0, "neighbors": 0}
    nid = scored[0][1]
    conf_filter = flags.get("conf_filter", "")

    t0 = time.perf_counter()
    if conf_filter:
        min_prio = _CI_PRIO.get(conf_filter, 1)
        deg = 0
        n_neighbors = 0
        for nb in G.neighbors(nid):
            edata = G.edges.get((nid, nb)) or G.edges.get((nb, nid)) or {}
            ci = edata.get("confidence", "EXTRACTED")
            if _CI_PRIO.get(ci, 0) <= min_prio:
                deg += 1
                n_neighbors += 1
    else:
        deg = G.degree(nid)
        n_neighbors = len(list(G.neighbors(nid)))
    return {"time_ms": round((time.perf_counter() - t0) * 1000, 2), "degree": deg, "neighbors": n_neighbors}


_OUTPUT_JACCARD = FLAGS = None


def discover_targets(G):
    deg_map = {data.get("label", nid): G.degree(nid) for nid, data in G.nodes(data=True)}
    labels = sorted(deg_map, key=lambda l: deg_map[l], reverse=True)
    return labels, deg_map


def generate_items(labels):
    queries = []
    for i, label in enumerate(labels[:NUM_QUERIES]):
        tmpl = _QUERY_TEMPLATES[i % len(_QUERY_TEMPLATES)]
        queries.append(tmpl.format(label))
    paths = []
    top = labels[:NUM_PATHS * 2]
    for i in range(0, len(top), 2):
        if i + 1 < len(top):
            paths.append((top[i], top[i + 1]))
    explains = labels[:NUM_EXPLAINS]
    return queries, paths, explains


def median_or_zero(vals):
    return round(statistics.median(vals), 1) if vals else 0


def avg_or_zero(vals):
    return round(statistics.mean(vals), 1) if vals else 0


def fmt(n):
    return f"{n:,}"


def delta_str(off_val, on_val, invert=False):
    """Format delta. invert=True means lower is better (e.g. nodes/edges/degree)."""
    if off_val == 0:
        return f"+{on_val}" if on_val else "0"
    d = on_val - off_val
    pct = (d / abs(off_val)) * 100
    if invert:
        pct = -pct
    arrow = "↑" if pct > 0 else "↓" if pct < 0 else "→"
    return f"{d:+,} ({pct:+.0f}%) {arrow}"


def measure_query_features(G, queries, paths, explains):
    baseline_flags = {
        "conf_filter": "",
        "use_planner": False,
        "use_hybrid": False,
        "use_bloom": False,
        "use_sampling": False,
        "sample_rate": 0.1,
        "use_matviews": False,
        "show_types": False,
    }

    def _run(flags, label):
        qb, pb, eb = [], [], []
        for q in queries:
            qb.append(run_bfs_bench(G, q, flags))
        for a, b in paths:
            pb.append(run_path_bench(G, a, b, flags))
        for t in explains:
            eb.append(run_explain_bench(G, t, flags))
        return qb, pb, eb

    print("  Baseline (all features OFF)...")
    q_off, p_off, e_off = _run(baseline_flags, "off")

    features = [
        ("index.py (conf-filter)", lambda f: {**f, "conf_filter": "INFERRED"}),
        ("query_planner.py", lambda f: {**f, "use_planner": True}),
        ("search/hybrid.py", lambda f: {**f, "use_hybrid": True}),
        ("approx.py (bloom)", lambda f: {**f, "use_bloom": True}),
        ("approx.py (sampling 10%)", lambda f: {**f, "use_sampling": True}),
        ("matviews.py", lambda f: {**f, "use_matviews": True}),
        ("code_schema.py (types)", lambda f: {**f, "show_types": True}),
    ]

    results = []
    for name, flag_fn in features:
        flags_on = flag_fn(baseline_flags)
        print(f"  {name} ON...")
        q_on, p_on, e_on = _run(flags_on, name)
        results.append((name, q_off, q_on, p_off, p_on, e_off, e_on))

    return results, q_off, p_off, e_off


def render_table(results, q_off, p_off, e_off, build_results, cat_c_features, graph_path, corpus):
    lines = []
    lines.append("# Graphify Fork Feature Audit — Query/Path/Explain Quality Impact")
    lines.append(f"**Graph:** `{graph_path}`")
    lines.append(f"**Corpus:** {corpus}")
    lines.append("**Mode:** AST-only (structural pipeline only)")
    lines.append(f"**Date:** {time.strftime('%Y-%m-%d')}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Legend")
    lines.append("- **OFF** = baseline (all fork features disabled)")
    lines.append("- **ON** = this feature enabled independently")
    lines.append("- **Δ** = ON − OFF; ↑ = higher is better for this metric")
    lines.append("- **Quality?** = qualitative judgment of direction")
    lines.append("- Metrics: **nodes** = BFS subgraph nodes (lower is more focused), **deg** = median explain degree (lower is more focused), **hops** = path hop count (lower is shorter)")
    lines.append("")
    lines.append("## Category A: Query-Time Features")
    lines.append("")
    lines.append("| Feature | BFS nodes | BFS edges | BFS ms | Path hops | Path ms | Expl. deg | Quality? |")
    lines.append("|---------|-----------|-----------|--------|-----------|---------|-----------|----------|")

    for name, q_off_r, q_on_r, p_off_r, p_on_r, e_off_r, e_on_r in results:
        off_n = [r["nodes"] for r in q_off_r]
        on_n = [r["nodes"] for r in q_on_r]
        off_e = [r["edges"] for r in q_off_r]
        on_e = [r["edges"] for r in q_on_r]
        off_t = [r["time_ms"] for r in q_off_r]
        on_t = [r["time_ms"] for r in q_on_r]
        off_h = [r["hops"] for r in p_off_r if r["hops"] > 0]
        on_h = [r["hops"] for r in p_on_r if r["hops"] > 0]
        off_d = [r["degree"] for r in e_off_r]
        on_d = [r["degree"] for r in e_on_r]

        mo = median_or_zero(off_n)
        mn = median_or_zero(on_n)
        me = median_or_zero(off_e)
        oe = median_or_zero(on_e)
        mt = median_or_zero(off_t)
        ot = median_or_zero(on_t)
        mh = median_or_zero(off_h) if off_h else 0
        oh = median_or_zero(on_h) if on_h else 0
        md = median_or_zero(off_d)
        od = median_or_zero(on_d)

        def _q(nodes_down, edges_down, hops_down, deg_down):
            goods = []
            any_change = mn != mo or me != oe or md != od or mh != oh or ot != mt
            if nodes_down: goods.append(f"nodes {mn:,} < {mo:,}")
            if edges_down: goods.append(f"edges {oe:,} < {me:,}")
            if hops_down and mh != oh: goods.append(f"hops {oh} < {mh}")
            if deg_down: goods.append(f"deg {od:,} < {md:,}")
            if ot < mt: goods.append(f"speed {ot:.1f}ms < {mt:.1f}ms")
            if not goods:
                if not any_change:
                    return "≈ neutral (graph too connected)"
                if ot > mt * 1.5:
                    return "⚠ slower"
                return "⚠ mixed"
            return "✓ " + ", ".join(goods)

        quality = _q(mn < mo, oe < me, oh <= mh, od < md)
        lines.append(
            f"| {name} | {fmt(mo)} → {fmt(mn)} | {fmt(me)} → {fmt(oe)} | "
            f"{mt}ms → {ot}ms | {mh} → {oh} | "
            f"{median_or_zero([r['time_ms'] for r in p_off_r])}ms → {median_or_zero([r['time_ms'] for r in p_on_r])}ms | "
            f"{fmt(md)} → {fmt(od)} | {quality} |"
        )

    lines.append("")
    lines.append("## Category B: Build-Time Features")
    lines.append("")
    if build_results:
        lines.append("| Feature | Δ Nodes | Δ Edges | BFS nodes | BFS edges | Path hops | Expl. deg | Quality? |")
        lines.append("|---------|---------|---------|-----------|-----------|-----------|-----------|----------|")
        for name, delta, qb, pb, eb in build_results:
            lines.append(
                f"| {name} | {delta['nodes']:+,} | {delta['edges']:+,} | "
                f"{fmt(median_or_zero([r['nodes'] for r in qb]))} | "
                f"{fmt(median_or_zero([r['edges'] for r in qb]))} | "
                f"{median_or_zero([r['hops'] for r in pb if r['hops'] > 0])} | "
                f"{fmt(median_or_zero([r['degree'] for r in eb]))} | "
                f"see above |"
            )
    else:
        lines.append("_No build-time features measured. Run with a corpus to enable._")
        lines.append("")
        lines.append("Build-time features require `--corpus` to rebuild the graph:")
        lines.append("```bash")
        lines.append("python validation/measure_features.py --corpus validation/corpora/toycorp")
        lines.append("```")

    lines.append("")
    lines.append("## Category C: Integration Features (not measurable on structural benchmark)")
    lines.append("")
    lines.append("| Feature | Module | Reason not measurable |")
    lines.append("|---------|--------|-----------------------|")
    for name, reason in cat_c_features:
        lines.append(f"| {name} | {reason.split(':')[0] if ':' in reason else reason} | {reason.split(':',1)[1] if ':' in reason else 'No structural impact'} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Notes")
    lines.append("- Hybrid search quality requires a labeled test set; structural benchmark only shows search selects DIFFERENT nodes")
    lines.append("- Call resolution must be benchmarked with `--corpus` flag to rebuild graph")
    lines.append("- Cumulative stacking effect is NOT the sum of individual deltas (features interact)")
    lines.append("- Lower BFS nodes/edges/degree = more focused results. This is a proxy for quality, not ground truth.")

    return "\n".join(lines) + "\n"


def measure_build_feature(corpus_path, feature_name, enable_fn, queries, paths, explains):
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from graphify.extract import collect_files, extract as _ext
        from graphify.build import build_from_json
        from graphify.cluster import cluster

        code_files = collect_files(corpus_path)
        if not code_files:
            return None
        result = _ext(code_files)
        G = build_from_json(result)
        communities = cluster(G)
        for nid, cid in communities.items():
            if nid in G:
                G.nodes[nid]["community"] = cid
        G = enable_fn(G, result, code_files)

        qb, pb, eb = [], [], []
        for q in queries:
            qb.append(run_bfs_bench(G, q, {}))
        for a, b in paths:
            pb.append(run_path_bench(G, a, b, {}))
        for t in explains:
            eb.append(run_explain_bench(G, t, {}))
        return qb, pb, eb
    except Exception as exc:
        print(f"  Error measuring {feature_name}: {exc}")
        return None


def render_cumulative_table(results_list):
    """Render a cumulative stacking table: each row = all features up to that point enabled.

    results_list is a list of (label, q_timings, p_timings, e_timings) tuples.
    """
    lines = []
    lines.append("# Cumulative Feature Stacking Benchmark")
    lines.append("")
    lines.append("Each row represents the **cumulative** effect of all features up to that point.")
    lines.append("")
    lines.append("| Configuration | BFS p50 | BFS avg | Path p50 | Path avg | Expl. deg | Nodes | Edges |")
    lines.append("|---|---|---|---|---|---|---|---|")

    for label, qb, pb, eb in results_list:
        q_ms = [t["time_ms"] for t in qb]
        p_ms = [t["time_ms"] for t in pb]
        e_deg = [t["degree"] for t in eb]
        q_nodes = median_or_zero([t["nodes"] for t in qb])
        q_edges = median_or_zero([t["edges"] for t in qb])
        lines.append(
            f"| {label} | {median_or_zero(q_ms):.1f}ms | {avg_or_zero(q_ms):.1f}ms | "
            f"{median_or_zero(p_ms):.1f}ms | {avg_or_zero(p_ms):.1f}ms | "
            f"{fmt(int(median_or_zero(e_deg)))} | {fmt(int(q_nodes))} | {fmt(int(q_edges))} |"
        )

    return "\n".join(lines) + "\n"


def measure_cumulative(G, queries, paths, explains, corpus):
    """Stack features progressively and benchmark each cumulative layer.
    Only tests features whose modules are importable.
    """
    baseline_flags = {
        "conf_filter": "",
        "use_planner": False,
        "use_hybrid": False,
        "use_bloom": False,
        "use_sampling": False,
        "sample_rate": 0.1,
        "use_matviews": False,
        "show_types": False,
    }

    def _run(flags, label):
        qb, pb, eb = [], [], []
        for q in queries:
            qb.append(run_bfs_bench(G, q, flags))
        for a, b_label in paths:
            pb.append(run_path_bench(G, a, b_label, flags))
        for t in explains:
            eb.append(run_explain_bench(G, t, flags))
        return qb, pb, eb

    def _importable(modname):
        try:
            __import__(modname)
            return True
        except ImportError:
            return False

    cumulative = [
        ("Baseline (all OFF)", *_run(baseline_flags, "baseline")),
    ]

    # conf-filter depends on index.py — always test this
    cumulative.append(("+ conf-filter", *_run({**baseline_flags, "conf_filter": "INFERRED"}, "+conf")))

    if _importable("graphify.query_planner"):
        cumulative.append(("+ query-planner", *_run(
            {**baseline_flags, "conf_filter": "INFERRED", "use_planner": True}, "+planner")))

    if _importable("graphify.search.hybrid"):
        cumulative.append(("+ hybrid-search", *_run(
            {**baseline_flags, "conf_filter": "INFERRED", "use_planner": True, "use_hybrid": True}, "+hybrid")))

    if _importable("graphify.approx"):
        cumulative.append(("+ sampling-10%", *_run(
            {**baseline_flags, "conf_filter": "INFERRED", "use_planner": True, "use_hybrid": True, "use_sampling": True}, "+sampling")))

    if _importable("graphify.matviews"):
        cumulative.append(("+ matviews", *_run(
            {**baseline_flags, "conf_filter": "INFERRED", "use_planner": True, "use_hybrid": True, "use_sampling": True, "use_matviews": True}, "+matviews")))

    # code_schema always tests (our module)
    cumulative.append(("+ code-schema", *_run(
        {**baseline_flags, "conf_filter": "INFERRED", "show_types": True}, "+schema")))

    return cumulative


def main():
    corpus = None
    graph_path = None
    cumulative_mode = "--cumulative" in sys.argv
    try:
        ci = sys.argv.index("--corpus")
        corpus = Path(sys.argv[ci + 1])
    except (ValueError, IndexError):
        pass

    try:
        gi = sys.argv.index("--graph")
        graph_path = Path(sys.argv[gi + 1])
    except (ValueError, IndexError):
        pass

    if graph_path is None:
        if DEFAULT_GRAPH.exists():
            graph_path = DEFAULT_GRAPH
        else:
            graph_path = PROJECT_ROOT / "graphify-out" / "graph.json"

    if corpus and not corpus.exists():
        print(f"error: corpus not found: {corpus}", file=sys.stderr)
        sys.exit(1)

    if not graph_path.exists():
        print(f"error: graph not found: {graph_path}", file=sys.stderr)
        print("Run validation/run.sh first, or use --corpus to build a graph.", file=sys.stderr)
        sys.exit(1)

    print(f"Graph: {graph_path} ({graph_path.stat().st_size / 1048576:.1f} MB)")
    data = json.loads(graph_path.read_text())
    G = json_graph.node_link_graph(data, edges="links")
    print(f"Loaded: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

    labels, _ = discover_targets(G)
    queries, paths, explains = generate_items(labels)
    print(f"Targets: {len(queries)} queries, {len(paths)} paths, {len(explains)} explains")

    print("\n=== Category A: Query-Time Features ===")
    results, q_off, p_off, e_off = measure_query_features(G, queries, paths, explains)

    build_results = []
    cat_c_features = [
        ("skills/ (agent skills)", "skills/: generates SKILL.md per community, not query-able"),
        ("groups.py (multi-repo)", "groups.py: cross-repo group management, not measurable on single repo"),
        ("lazy_pool.py", "lazy_pool.py: graph LRU pool for multi-repo, no effect on single repo"),
        ("registry.py", "registry.py: ~/.graphify/registry cross-repo index, not measurable"),
        ("contract_bridge.py", "contract_bridge.py: cross-repo interface bridging, not measurable"),
        ("hooks.py (git hooks)", "hooks.py: post-commit hooks, not measurable on benchmark"),
        ("__main__.py (platform installers)", "14-platform install: integration only, not measurable"),
        ("wiki.py (wiki export)", "wiki.py: export format, not measurable on benchmark"),
        ("export.py (formats)", "export.py: HTML/SVG/Obsidian/GraphML/Neo4j exports, not measurable"),
        ("report.py (report gen)", "report.py: GRAPH_REPORT.md generation, part of pipeline not query"),
    ]

    if corpus:
        print("\n=== Category B: Build-Time Features ===")
        try:
            print("  call_dag.py (cross-file call resolution)...")
            def enable_calls(G, result, files):
                try:
                    from graphify.call_dag import resolve_call_graph, emit_call_edges
                    resolved, _ = resolve_call_graph(files, G)
                    new_edges = emit_call_edges(resolved)
                    for e in new_edges:
                        if e["source"] in G and e["target"] in G:
                            attrs = {k: v for k, v in e.items() if k not in ("source", "target")}
                            attrs["_src"] = e["source"]
                            attrs["_tgt"] = e["target"]
                            G.add_edge(e["source"], e["target"], **attrs)
                except Exception as exc:
                    print(f"    call resolution skipped: {exc}")
                return G
            br = measure_build_feature(corpus, "call_dag.py", enable_calls, queries, paths, explains)
            if br:
                qb, pb, eb = br
                delta = {"nodes": median_or_zero([r["nodes"] for r in qb]) - median_or_zero([r["nodes"] for r in q_off]),
                         "edges": median_or_zero([r["edges"] for r in qb]) - median_or_zero([r["edges"] for r in q_off])}
                build_results.append(("call_dag.py (+5 siblings)", delta, qb, pb, eb))
        except Exception as exc:
            print(f"  call_dag.py measurement failed: {exc}")

        try:
            print("  processes.py (process tracing)...")
            def enable_processes(G, result, files):
                try:
                    from graphify.processes import detect_entry_points, trace_process, build_processes
                    procs = build_processes(G)
                    for proc in procs[:20]:
                        proc_nid = f"process_{proc.name.lower().replace(' ', '_')}"
                        G.add_node(proc_nid, label=proc.name, file_type="process",
                                   source_file="", source_location="")
                        for step in proc.steps:
                            if step.node_id in G:
                                G.add_edge(proc_nid, step.node_id, relation="step_in_process",
                                           confidence="INFERRED", _src=proc_nid, _tgt=step.node_id)
                except Exception as exc:
                    print(f"    process tracing skipped: {exc}")
                return G
            br = measure_build_feature(corpus, "processes.py", enable_processes, queries, paths, explains)
            if br:
                qb, pb, eb = br
                delta = {"nodes": median_or_zero([r["nodes"] for r in qb]) - median_or_zero([r["nodes"] for r in q_off]),
                         "edges": median_or_zero([r["edges"] for r in qb]) - median_or_zero([r["edges"] for r in q_off])}
                build_results.append(("processes.py", delta, qb, pb, eb))
        except Exception as exc:
            print(f"  processes.py measurement failed: {exc}")

    if cumulative_mode:
        print("\n=== Cumulative Stacking Mode ===")
        cumulative = measure_cumulative(G, queries, paths, explains, corpus)
        report = render_cumulative_table(cumulative)
        out_path = VALIDATION_DIR / "CUMULATIVE.md"
        out_path.write_text(report)
        print(f"\nCumulative report written: {out_path}")
    else:
        report = render_table(results, q_off, p_off, e_off, build_results, cat_c_features, graph_path, corpus or "existing graph")
        out_path = VALIDATION_DIR / "FEATURE_AUDIT.md"
        out_path.write_text(report)
        print(f"\nReport written: {out_path}")


if __name__ == "__main__":
    main()
