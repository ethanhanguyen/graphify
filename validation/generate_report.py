import json
import re
import subprocess
import statistics
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

VALIDATION_DIR = Path(__file__).resolve().parent
OUT_B = VALIDATION_DIR / 'out-baseline'
OUT_S = VALIDATION_DIR / 'out-speedai'
VENV_B = VALIDATION_DIR / '.venv-baseline'
VENV_S = VALIDATION_DIR / '.venv-speedai'

NUM_QUERIES = 10
NUM_PATHS = 5
NUM_EXPLAINS = 10
CLI_TIMEOUT = 60
NUM_WORKERS = 4

SKIP_QUERIES = '--skip-queries' in sys.argv

import networkx as nx
from networkx.readwrite import json_graph


def pct(a, b):
    if a == 0:
        return '+inf%' if b > 0 else '0%'
    return f'{((b - a) / a) * 100:+.0f}%'


def fmt(n):
    return f'{n:,}'


def mb(path):
    if not path.exists():
        return '?'
    return f'{path.stat().st_size / 1048576:.0f} MB'


def load_graph(path):
    data = json.loads(path.read_text())
    return json_graph.node_link_graph(data, edges='links')


def get_version(venv_path):
    try:
        r = subprocess.run(
            [str(venv_path / 'bin' / 'pip'), 'show', 'graphifyy'],
            capture_output=True, text=True,
        )
        for line in r.stdout.splitlines():
            if line.startswith('Version:'):
                return line.split(':')[1].strip()
    except Exception:
        pass
    return '?'


def extract_god_nodes(md_path):
    try:
        text = md_path.read_text()
        gods = []
        in_section = False
        for line in text.splitlines():
            if '## God Nodes' in line:
                in_section = True
                continue
            if in_section and line.startswith('#'):
                break
            if in_section and line.strip() and line[0].isdigit():
                parts = line.strip().split(' - ')
                if len(parts) >= 2:
                    name = parts[0].split(' ', 1)[1] if ' ' in parts[0] else parts[0]
                    gods.append((name, parts[1]))
                if len(gods) >= 10:
                    break
        return gods
    except Exception:
        return []


def extract_communities(md_path):
    try:
        for line in md_path.read_text().splitlines():
            m = re.search(r'(\d+)\s+communities', line)
            if m:
                return int(m.group(1))
    except Exception:
        pass
    return 0


def _score_nodes(G, terms):
    scored = []
    for nid, ndata in G.nodes(data=True):
        label = ndata.get('label', '').lower()
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
        return {'time_ms': 0, 'nodes': 0, 'edges': 0}
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
    return {'time_ms': round((time.perf_counter() - t0) * 1000, 2), 'nodes': len(visited), 'edges': len(edges_list)}


def run_path_bench(G, a, b):
    t0 = time.perf_counter()
    scored_a = _score_nodes(G, [t.lower() for t in a.split()])
    scored_b = _score_nodes(G, [t.lower() for t in b.split()])
    if not scored_a or not scored_b:
        return {'time_ms': 0, 'hops': -1}
    src, tgt = scored_a[0][1], scored_b[0][1]
    try:
        hops = len(nx.shortest_path(G, src, tgt)) - 1
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        hops = -1
    return {'time_ms': round((time.perf_counter() - t0) * 1000, 2), 'hops': hops}


def run_explain_bench(G, term):
    t0 = time.perf_counter()
    scored = _score_nodes(G, [t.lower() for t in term.split()])
    if not scored:
        return {'time_ms': 0, 'degree': 0, 'neighbors': 0}
    nid = scored[0][1]
    deg = G.degree(nid)
    n_neighbors = len(list(G.neighbors(nid)))
    return {'time_ms': round((time.perf_counter() - t0) * 1000, 2), 'degree': deg, 'neighbors': n_neighbors}


def _trunc(text, n):
    return text if len(text) <= n else text[:n] + '...'


# ── Target discovery ──────────────────────────────────────────────

def discover_targets(G_b, G_s):
    deg_b = {data.get('label', nid): G_b.degree(nid) for nid, data in G_b.nodes(data=True)}
    deg_s = {data.get('label', nid): G_s.degree(nid) for nid, data in G_s.nodes(data=True)}
    common = sorted(
        set(deg_b) & set(deg_s),
        key=lambda l: max(deg_b[l], deg_s[l]),
        reverse=True,
    )
    return common, deg_b, deg_s


_QUERY_TEMPLATES = [
    "how does {} work",
    "what is the purpose of {}",
    "explain how {} is used",
    "what role does {} play",
    "describe the function of {}",
]


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
    full = [str(venv / 'bin' / 'graphify')] + list(cmd) + list(args)
    try:
        r = subprocess.run(full, capture_output=True, text=True, timeout=CLI_TIMEOUT)
        out = r.stdout
        if r.returncode != 0:
            out += f'\n(exit {r.returncode})'
        if r.stderr:
            out = r.stderr.rstrip() + '\n' + out
        return out.strip()
    except subprocess.TimeoutExpired:
        return f'(timeout after {CLI_TIMEOUT}s)'
    except Exception as exc:
        return f'(error: {exc})'


def _run_pair(venv_b, venv_s, cmd, args_b, args_s):
    out_b = _run_cli(venv_b, cmd, *args_b)
    out_s = _run_cli(venv_s, cmd, *args_s)
    return out_b, out_s


def _run_batch(label, items, make_args):
    results = []
    total = len(items)
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as ex:
        futures = {}
        for i, item in enumerate(items):
            args_b, args_s, target_label = make_args(item)
            fut = ex.submit(_run_pair, VENV_B, VENV_S, [label], args_b, args_s)
            futures[fut] = (i, target_label)
            print(f'  [{i+1}/{total}] {label} {_trunc(str(target_label), 60)}')

        for fut in as_completed(futures):
            i, target_label = futures[fut]
            out_b, out_s = fut.result()
            results.append({
                'idx': i, 'label': target_label, 'b': out_b, 's': out_s,
                'b_lines': out_b.count('\n') + 1, 's_lines': out_s.count('\n') + 1,
                'b_words': len(out_b.split()), 's_words': len(out_s.split()),
                'b_err': 'error' in out_b.lower()[:200] or 'traceback' in out_b.lower()[:200],
                's_err': 'error' in out_s.lower()[:200] or 'traceback' in out_s.lower()[:200],
            })

    results.sort(key=lambda r: r['idx'])
    return results


def run_all_queries(queries, paths, explains):
    results = {'query': [], 'path': [], 'explain': []}

    results['query'] = _run_batch(
        'query', queries,
        lambda q: (
            (q, '--graph', str(OUT_B / 'graph.json')),
            (q, '--graph', str(OUT_S / 'graph.json')),
            q,
        ),
    )

    results['path'] = _run_batch(
        'path', paths,
        lambda p: (
            (p[0], p[1], '--graph', str(OUT_B / 'graph.json')),
            (p[0], p[1], '--graph', str(OUT_S / 'graph.json')),
            f'{p[0]} -> {p[1]}',
        ),
    )

    results['explain'] = _run_batch(
        'explain', explains,
        lambda label: (
            (label, '--graph', str(OUT_B / 'graph.json')),
            (label, '--graph', str(OUT_S / 'graph.json')),
            label,
        ),
    )

    return results


# ── File helpers ──────────────────────────────────────────────────

def read_response(path):
    try:
        return path.read_text()
    except Exception:
        return ''


def parse_query_response(text):
    nodes, edges = [], []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('NODE '):
            label = s[5:].split(' src=')[0].strip()
            if label:
                nodes.append(label)
        elif s.startswith('EDGE '):
            src = s[5:].split(' --')[0].strip()
            if src:
                edges.append(src)
    return nodes, edges


def parse_path_response(text):
    hops = None
    path_lines = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('Shortest path '):
            m = re.search(r'\((\d+) hops?\)', s)
            if m:
                hops = int(m.group(1))
            path_lines.append(s)
        elif s.startswith('No path found'):
            path_lines.append(s)
        elif path_lines and (line.startswith('  ') or s == ''):
            path_lines.append(line)
        elif 'error' in s.lower():
            path_lines.append(s)
    return hops, path_lines


def parse_explain_response(text):
    degree = None
    conn_count = None
    neighbors = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith('Degree:'):
            try:
                degree = int(s.split(':')[1].strip())
            except ValueError:
                pass
        elif s.startswith('Connections'):
            m = re.search(r'\((\d+)\)', s)
            if m:
                conn_count = int(m.group(1))
        elif s.startswith('--> '):
            label = s[4:].split(' [')[0].strip()
            neighbors.append(label)
    if degree is None and 'No node matching' in text:
        degree = -1
        conn_count = -1
    return degree, conn_count, neighbors


def jaccard(set_a, set_b):
    if not set_a and not set_b:
        return 1.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union > 0 else 0.0


def median_or_zero(vals):
    return round(statistics.median(vals), 1) if vals else 0


def avg_or_zero(vals):
    return round(statistics.mean(vals), 1) if vals else 0


# ── Main ──────────────────────────────────────────────────────────

gb = OUT_B / 'graph.json'
gs = OUT_S / 'graph.json'
G_b = load_graph(gb) if gb.exists() else nx.Graph()
G_s = load_graph(gs) if gs.exists() else nx.Graph()

ver_b = get_version(VENV_B) if VENV_B.exists() else '?'
ver_s = get_version(VENV_S) if VENV_S.exists() else '?'

nodes_b, edges_b = G_b.number_of_nodes(), G_b.number_of_edges()
nodes_s, edges_s = G_s.number_of_nodes(), G_s.number_of_edges()
size_b, size_s = mb(gb), mb(gs)
bpn_b = int(gb.stat().st_size / max(nodes_b, 1)) if gb.exists() else 0
bpn_s = int(gs.stat().st_size / max(nodes_s, 1)) if gs.exists() else 0

com_b = extract_communities(OUT_B / 'GRAPH_REPORT.md')
com_s = extract_communities(OUT_S / 'GRAPH_REPORT.md')
gods_b = extract_god_nodes(OUT_B / 'GRAPH_REPORT.md')
gods_s = extract_god_nodes(OUT_S / 'GRAPH_REPORT.md')

common_labels, deg_b_map, deg_s_map = discover_targets(G_b, G_s)
queries, paths, explains = generate_targets(common_labels)

if not SKIP_QUERIES:
    print(f'Targets: {len(queries)} queries, {len(paths)} paths, {len(explains)} explains')
    print(f'Common labels found: {len(common_labels)}')
    print(f'Running CLI queries (parallel)...')
    t0 = time.perf_counter()
    cli_results = run_all_queries(queries, paths, explains)
    print(f'  CLI queries completed in {time.perf_counter() - t0:.1f}s')

    q_results = cli_results['query']
    p_results = cli_results['path']
    e_results = cli_results['explain']
else:
    q_results = p_results = e_results = []
    print('Skipping CLI queries (--skip-queries)')

# ── Internal timing benchmarks (scale up) ─────────────────────────

q_timings_b, q_timings_s = [], []
p_timings_b, p_timings_s = [], []
e_timings_b, e_timings_s = [], []

for i, q in enumerate(queries):
    rb = run_bfs_bench(G_b, q)
    rs = run_bfs_bench(G_s, q)
    q_timings_b.append(rb)
    q_timings_s.append(rs)

for i, (a, b) in enumerate(paths):
    rb = run_path_bench(G_b, a, b)
    rs = run_path_bench(G_s, a, b)
    p_timings_b.append(rb)
    p_timings_s.append(rs)

for i, label in enumerate(explains):
    rb = run_explain_bench(G_b, label)
    rs = run_explain_bench(G_s, label)
    e_timings_b.append(rb)
    e_timings_s.append(rs)

# ── Aggregate stats ───────────────────────────────────────────────

def _ms_vals(timings):
    return [t['time_ms'] for t in timings]

q_ms_b, q_ms_s = _ms_vals(q_timings_b), _ms_vals(q_timings_s)
p_ms_b, p_ms_s = _ms_vals(p_timings_b), _ms_vals(p_timings_s)
e_ms_b, e_ms_s = _ms_vals(e_timings_b), _ms_vals(e_timings_s)


def _time_row(ms_b, ms_s):
    return f'{median_or_zero(ms_b)}ms / avg {avg_or_zero(ms_b)}ms | {median_or_zero(ms_s)}ms / avg {avg_or_zero(ms_s)}ms'


def _jaccard_from_cli(results, parser):
    """Compute avg Jaccard overlap for CLI query/explain results."""
    scores = []
    for r in results:
        nodes_b = parser(r['b'])
        nodes_s = parser(r['s'])
        if isinstance(nodes_b, tuple):
            nodes_b = nodes_b[0]
        if isinstance(nodes_s, tuple):
            nodes_s = nodes_s[0]
        scores.append(jaccard(set(nodes_b), set(nodes_s)))
    return scores


# ── Render report ────────────────────────────────────────────────
today = time.strftime('%Y-%m-%d')


report = f'''# Graphify Apple-to-Apple: VSCode Full Stress Test

**Corpus:** microsoft/vscode (shallow clone)  
**Versions:** Baseline (safishamsi {ver_b}) vs Current ({ver_s})  
**Mode:** AST-only (no semantic LLM extraction -- structural pipeline only)  
**Targets:** {len(common_labels)} common labels auto-discovered across both graphs  
**Date:** {today}

---

## Build Comparison

| Metric | Baseline ({ver_b}) | Current ({ver_s}) | Delta |
|---|---|---|---|
| Nodes in graph | {fmt(nodes_b)} | {fmt(nodes_s)} | {pct(nodes_b, nodes_s)} |
| Edges in graph | {fmt(edges_b)} | {fmt(edges_s)} | {pct(edges_b, edges_s)} |
| Communities | {fmt(com_b)} | {fmt(com_s)} | {pct(com_b, com_s)} |
| graph.json size | {size_b} | {size_s} | {pct(gb.stat().st_size, gs.stat().st_size) if gb.exists() and gs.exists() else '?'} |
| Bytes per node | {fmt(bpn_b)} | {fmt(bpn_s)} | {pct(bpn_b, bpn_s)} |
| Common labels | {len(common_labels)} | {len(common_labels)} | |

---

## Legend

- **B** = Baseline (safishamsi/graphify), **S** = Current (local fork)
- **W** = Winner — which version performed faster or found a shorter path
- **n** = nodes, **e** = edges — subgraph size returned by BFS traversal
- **hops** = edge count on the shortest path between two nodes (−1 = no path found)
- **deg** = node degree (number of direct edges), **conn** = connection count reported by `graphify explain`
- **Latency** = wall-clock time measured by internal networkx benchmarks (not CLI overhead)
- All timing values are **median** unless labeled **avg**

---

## Query Performance (Internal Timing, {len(queries)} queries)

| Metric | Baseline (median / avg) | Current (median / avg) |
|---|---|---|
| BFS latency | {_time_row(q_ms_b, q_ms_s)} | |
| Subgraph nodes (median) | {fmt(int(median_or_zero([t['nodes'] for t in q_timings_b]))) if q_timings_b else '0'} | {fmt(int(median_or_zero([t['nodes'] for t in q_timings_s]))) if q_timings_s else '0'} |
| Subgraph edges (median) | {fmt(int(median_or_zero([t['edges'] for t in q_timings_b]))) if q_timings_b else '0'} | {fmt(int(median_or_zero([t['edges'] for t in q_timings_s]))) if q_timings_s else '0'} |

### Per-query detail (BFS)

| # | Query | Baseline | Current | W |
|---|---|---|---|---|
'''

for i, q in enumerate(queries):
    rb, rs = q_timings_b[i], q_timings_s[i]
    winner = 'B' if rb['time_ms'] < rs['time_ms'] else 'S'
    report += f'| {i+1} | `{_trunc(q, 55)}` | {rb["time_ms"]}ms ({fmt(rb["nodes"])}n/{fmt(rb["edges"])}e) | {rs["time_ms"]}ms ({fmt(rs["nodes"])}n/{fmt(rs["edges"])}e) | {winner} |\n'

report += f'''
### Shortest Path ({len(paths)} pairs)

| Metric | Baseline (median / avg) | Current (median / avg) |
|---|---|---|
| Path latency | {_time_row(p_ms_b, p_ms_s)} | |
| Hops (median) | {int(median_or_zero([t['hops'] for t in p_timings_b])) if p_timings_b else 0} | {int(median_or_zero([t['hops'] for t in p_timings_s])) if p_timings_s else 0} |

| # | Source → Target | B hops | B ms | S hops | S ms | W |
|---|---|---|---|---|---|---|
'''

for i, (a, b_label) in enumerate(paths):
    rb, rs = p_timings_b[i], p_timings_s[i]
    winner = 'B' if rb['hops'] > 0 and (rs['hops'] < 0 or rb['hops'] <= rs['hops']) else 'S'
    report += f'| {i+1} | `{_trunc(a, 25)}` → `{_trunc(b_label, 25)}` | {rb["hops"]} | {rb["time_ms"]}ms | {rs["hops"]} | {rs["time_ms"]}ms | {winner} |\n'

report += f'''
### Node Explain ({len(explains)} targets)

| Metric | Baseline (median / avg) | Current (median / avg) |
|---|---|---|
| Latency | {_time_row(e_ms_b, e_ms_s)} | |
| Degree (median) | {int(median_or_zero([t['degree'] for t in e_timings_b])) if e_timings_b else 0} | {int(median_or_zero([t['degree'] for t in e_timings_s])) if e_timings_s else 0} |
| Neighbors (median) | {fmt(int(median_or_zero([t['neighbors'] for t in e_timings_b]))) if e_timings_b else '0'} | {fmt(int(median_or_zero([t['neighbors'] for t in e_timings_s]))) if e_timings_s else '0'} |

'''

if e_results:
    j_scores = _jaccard_from_cli(e_results, lambda t: parse_explain_response(t)[2])
    report += f'| CLI neighbor Jaccard (median) | | {round(median_or_zero(j_scores), 2)} |\n'
    report += '\n'

if e_results:
    report += '| # | Label | B deg | S deg | B conn | S conn |\n'
    report += '|---|---|---|---|---|---|\n'
    for r in e_results:
        db, _, nb = parse_explain_response(r['b'])
        ds, _, ns = parse_explain_response(r['s'])
        report += f'| {r["idx"]+1} | `{_trunc(r["label"], 30)}` | {db if db is not None else "?"} | {ds if ds is not None else "?"} | {nb[:3] if nb else "—"} | {ns[:3] if ns else "—"} |\n'

report += f'''
---

## CLI Query Response Summary

{len(q_results)} queries, {len(p_results)} paths, {len(explains)} explains run against each version.
'''

if CLI_TIMEOUT and q_results:
    b_errs = sum(1 for r in q_results if r['b_err'])
    s_errs = sum(1 for r in q_results if r['s_err'])
    b_lines = [r['b_lines'] for r in q_results]
    s_lines = [r['s_lines'] for r in q_results]
    report += f'''
| Dimension | Baseline | Current |
|---|---|---|
| Query errors | {b_errs}/{len(q_results)} | {s_errs}/{len(q_results)} |
| Median output lines | {int(median_or_zero(b_lines))} | {int(median_or_zero(s_lines))} |
| Path errors | {sum(1 for r in p_results if r["b_err"])}/{len(p_results)} | {sum(1 for r in p_results if r["s_err"])}/{len(p_results)} |
| Explain errors | {sum(1 for r in e_results if r["b_err"])}/{len(explains)} | {sum(1 for r in e_results if r["s_err"])}/{len(explains)} |
'''

report += f'''
---

## God Nodes (top 10)

### Baseline
```
{chr(10).join(f'{i+1}. {n} - {e}' for i, (n, e) in enumerate(gods_b)) if gods_b else '_No god nodes extracted_'}
```

### Current
```
{chr(10).join(f'{i+1}. {n} - {e}' for i, (n, e) in enumerate(gods_s)) if gods_s else '_No god nodes extracted_'}
```

---

## Summary

| Dimension | Winner | Margin |
|---|---|---|
| **Edge density** | {'Baseline' if edges_b > edges_s else 'Current'} | {pct(edges_b, edges_s)} edges |
| **Storage efficiency** | {'Baseline' if bpn_b < bpn_s else 'Current'} | {size_b} vs {size_s} |
| **BFS latency (median)** | {'Baseline' if median_or_zero(q_ms_b) < median_or_zero(q_ms_s) else 'Current'} | {median_or_zero(q_ms_b)}ms vs {median_or_zero(q_ms_s)}ms |
| **Path latency (median)** | {'Baseline' if median_or_zero(p_ms_b) < median_or_zero(p_ms_s) else 'Current'} | {median_or_zero(p_ms_b)}ms vs {median_or_zero(p_ms_s)}ms |
| **Graph nodes** | {'Baseline' if nodes_b > nodes_s else 'Current'} | {fmt(nodes_b)} vs {fmt(nodes_s)} |
| **Common labels** | | {len(common_labels)} shared across versions |

---

## Target Labels Used

{len(common_labels)} labels appear in both graphs. Top 20 by degree:

| # | Label | Baseline | Current |
|---|---|---|---|
'''

for i, label in enumerate(common_labels[:20]):
    report += f'| {i+1} | `{_trunc(label, 45)}` | {fmt(deg_b_map.get(label, 0))} | {fmt(deg_s_map.get(label, 0))} |\n'

report += f'''
---

## How to Re-run

```bash
cd {VALIDATION_DIR} && ./run.sh
```

Custom corpus:
```bash
./run.sh --corpus https://github.com/torvalds/linux
./run.sh --corpus /path/to/local/repo
```

Full setup guide: `{VALIDATION_DIR}/README.md`
'''

out = VALIDATION_DIR / 'COMPARISON.md'
out.write_text(report)
print(f'Report written: {out}')
print(f'  Baseline: {fmt(nodes_b)} nodes, {fmt(edges_b)} edges')
print(f'  Current:  {fmt(nodes_s)} nodes, {fmt(edges_s)} edges')
print(f'  Common labels: {len(common_labels)}')
