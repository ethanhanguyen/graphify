# PR 1: Fork + Baseline + Benchmark Suite

**Phase:** 1
**Stream:** A (Query Engine)
**Estimate:** 1-2 days
**Depends on:** Nothing

## What to Build

### 1. Fork Setup
- Verify `git clone` works, dev environment is ready
- Run full test suite: `pytest tests/ -q` — all must pass
- Run `pyproject.toml` build: `pip install -e .` or `uv pip install -e .`
- Verify `graphify --help` works after install

### 2. Benchmark Suite (`graphify/benchmark.py` — EXTEND existing)

Current `benchmark.py` only does token-reduction benchmarks. Add:

```python
def generate_bsbm_graph(num_nodes: int = 50000, seed: int = 42) -> nx.Graph:
    """Generate a BSBM-synthetic benchmark graph.
    Creates nodes with realistic label/community/file_type distributions
    and edges with relation types and confidence labels.
    
    Scale tiers (nodes, est. memory):
    - small:  50000   (~50 MB)
    - medium: 100000  (~100 MB)
    - large:  500000  (~500 MB)
    - xlarge: 1000000 (~1 GB)
    - huge:   5000000 (~5 GB, requires --scale huge)
    Returns a NetworkX graph ready for benchmarking."""

def benchmark_query_latency(G, num_queries: int = 100, depth: int = 4, mode: str = "bfs", seed: int = 42) -> dict:
    """Run num_queries random queries and measure:
    - avg/p50/p95/p99 latency (ms)
    - queries per second
    seed controls query selection for reproducibility.
    Returns dict with timing stats."""

def benchmark_pathfinding(G, num_pairs: int = 50, max_hops: int = 20) -> dict:
    """Run shortest_path between random node pairs.
    Measure: avg/p50/p95/p99 latency for 4-hop, 6-hop, 10-hop pairs."""

def benchmark_memory(G) -> dict:
    """Measure memory usage of graph structure.
    - NetworkX graph memory (nodes + edges)
    - Index overhead (% increase vs raw graph)
    - Total resident memory of Python process"""

def benchmark_scale(num_nodes_list: list[int] = [50000, 100000, 500000, 1000000]) -> list[dict]:
    """Run benchmark_query_latency at multiple graph sizes.
    Default excludes 5M (huge) — gated behind --scale huge CLI flag.
    Returns list of results dicts, one per size, with bytes_per_node and bytes_per_edge."""

def diff_benchmarks(prev: dict, curr: dict) -> dict:
    """Compare two benchmark results and return deltas.
    Example: {"phase": "2-indexing", "deltas": {"qps_50k": "+1087%", "p95_ms_50k": "-93%", "memory_mb": "+12%"}}
    Computes % change for each metric in short, medium, large, xlarge, huge tiers.
    Returns dict with phase label and per-metric percentage deltas."""

def run_full_benchmark(G, output_path: str = "graphify-out/benchmark.json",
                       seed: int = 42,
                       prev_benchmark_path: str | None = None) -> dict:
    """Run all benchmarks and write results to JSON.
    If prev_benchmark_path is given, diffs against it and appends delta entry
    to graphify-out/progressive.json.
    Returns full benchmark dict with timestamps and scale tier breakdown."""
```

### 3. Benchmark CLI Subcommand

Add to `graphify/__main__.py`:

```
graphify benchmark [--graph graphify-out/graph.json]
                   [--output graphify-out/benchmark.json]
                   [--seed 42]
                   [--compare graphify-out/benchmark_v1.json]
                   [--scale huge]
```

- `--seed`: Pins reproducibility (default 42)
- `--compare PATH`: Load previous benchmark, diff against it, append delta to `graphify-out/progressive.json`
- `--scale huge`: Include 5M-node tier (default: runs small-large, skips 5M)

Output format:
```json
{
  "phase": "1-baseline",
  "timestamp": "2026-04-29T10:00:00Z",
  "graph_stats": {"nodes": 50000, "edges": 125000, "communities": 42},
  "query_latency_ms": {
    "avg": 12.5, "p50": 10.2, "p95": 45.8, "p99": 89.3,
    "qps": 80
  },
  "pathfinding_ms": {
    "4hop_avg": 5.2, "6hop_avg": 18.7, "10hop_avg": 145.3
  },
  "memory_mb": {"graph": 45.2, "index_overhead": 0, "total": 52.1,
                "bytes_per_node": 948, "bytes_per_edge": 361},
  "scale": [
    {"nodes": 50000,  "qps": 80,  "p95_ms": 45.8, "bytes_per_node": 948, "bytes_per_edge": 361},
    {"nodes": 100000, "qps": 35,  "p95_ms": 98.2, "bytes_per_node": 912, "bytes_per_edge": 355},
    {"nodes": 500000, "qps": 12,  "p95_ms": 240,  "bytes_per_node": 890, "bytes_per_edge": 348},
    {"nodes": 1000000,"qps": 5,   "p95_ms": 680,  "bytes_per_node": 872, "bytes_per_edge": 342}
  ]
}
```

### 4. Tests (`tests/test_benchmark_query.py`)

```python
# tests/test_benchmark_query.py

from graphify.benchmark import (
    generate_bsbm_graph,
    benchmark_query_latency,
    benchmark_pathfinding,
    benchmark_memory,
)

def test_generate_bsbm_graph_creates_nodes():
    G = generate_bsbm_graph(num_nodes=1000)
    assert G.number_of_nodes() == 1000
    assert G.number_of_edges() > 0

def test_generate_bsbm_graph_has_communities():
    G = generate_bsbm_graph(num_nodes=1000)
    # At least some nodes should have community attribute
    communities = set()
    for _, data in G.nodes(data=True):
        if data.get("community") is not None:
            communities.add(data["community"])
    assert len(communities) > 0

def test_benchmark_query_latency_runs():
    G = generate_bsbm_graph(num_nodes=500)
    result = benchmark_query_latency(G, num_queries=10, depth=3)
    assert "avg" in result
    assert result["avg"] > 0

def test_benchmark_pathfinding_runs():
    G = generate_bsbm_graph(num_nodes=500)
    result = benchmark_pathfinding(G, num_pairs=5)
    assert "4hop_avg" in result

def test_benchmark_memory_runs():
    G = generate_bsbm_graph(num_nodes=500)
    result = benchmark_memory(G)
    assert result["graph"] > 0
```

## Files Changed/Created

| File | Action | Purpose |
|------|--------|---------|
| `graphify/benchmark.py` | **Extend** | Add BSBM generator, latency/pathfinding/memory benchmarks |
| `graphify/__main__.py` | **Extend** | Add `graphify benchmark` subcommand |
| `tests/test_benchmark_query.py` | **New** | Tests for benchmark functions |
| `pyproject.toml` | **Verify** | Confirm test dependencies available |

## Compatibility
- No changes to existing APIs
- No changes to MCP tools
- `graph.json` format unchanged

## Verification
```bash
pytest tests/test_benchmark_query.py tests/test_benchmark.py -q
pytest tests/ -q  # all existing tests still pass
graphify benchmark --help  # CLI works
pytest tests/test_benchmark_query.py --cov=graphify.benchmark --cov-report=term  # coverage >= 90%
```

### Commit

```bash
git add -A && git commit -m "feat(phase-1): fork baseline + benchmark suite"
```

---

## Code Review Checklist

Before merging this PR, verify:
- [ ] All tests pass: `pytest tests/ -q`
- [ ] Test coverage >= 90% for `graphify/benchmark.py`: `pytest tests/test_benchmark_query.py --cov=graphify.benchmark --cov-report=term`
- [ ] `graphify benchmark` runs on a real graph and produces valid JSON at `graphify-out/benchmark.json`
- [ ] Output includes `phase: "1-baseline"` field, `bytes_per_node`, `bytes_per_edge`
- [ ] BSBM generator produces graphs at 50K, 100K, 500K, 1M, 5M nodes
- [ ] `--compare` flag diffs correctly and writes `progressive.json`
- [ ] `--scale huge` gates 5M tier correctly
- [ ] No changes to existing MCP tools or APIs
- [ ] At least 1 other developer reviewed

---

## Prompt (paste into AI coding agent)

```
You are implementing Phase 1 of the Graphify fork enhancement plan.

Repository: ~/graphify
Branch: feat/phase-1-baseline

TASK: Extend the benchmark module and add a benchmark CLI subcommand.

1. Extend graphify/benchmark.py with these functions:
   - generate_bsbm_graph(num_nodes=50000, seed=42): Generate a BSBM-synthetic benchmark graph with realistic label/community/file_type distributions and edges with relation types (calls, imports, uses) and confidence labels (EXTRACTED, INFERRED, AMBIGUOUS). Supports scale tiers from 50K to 5M nodes. Nodes should have community IDs (0-41 for 50k nodes), source_file paths (e.g. "src/module_{id}.py"), and labels.
   - benchmark_query_latency(G, num_queries=100, depth=4, mode="bfs", seed=42): Run random BFS queries and return {avg, p50, p95, p99, qps} dict. seed makes query selection reproducible.
   - benchmark_pathfinding(G, num_pairs=50, seed=42): Run shortest_path between random node pairs and return {4hop_avg, 6hop_avg, 10hop_avg}.
   - benchmark_memory(G): Measure memory of graph + process. Return {graph, total, bytes_per_node, bytes_per_edge} in MB.
   - benchmark_scale(num_nodes_list=[50000, 100000, 500000, 1000000]): Run benchmark_query_latency at multiple sizes. Returns list with bytes_per_node/bytes_per_edge normalization. 5M gated behind --scale huge.
   - diff_benchmarks(prev, curr) → dict: Compare two benchmark JSONs, compute % deltas per metric, return {"phase": "...", "deltas": {...}}.
   - run_full_benchmark(G, output_path, seed=42, prev_benchmark_path=None): Run all benchmarks, write results JSON. If prev_benchmark_path given, diffs and appends to progressive.json. Writes phase="1-baseline" field.

2. Add a `graphify benchmark` CLI subcommand in __main__.py that:
   - Accepts --graph, --output, --seed, --compare, and --scale arguments
   - Loads the graph from --graph path (default: graphify-out/graph.json)
   - Runs run_full_benchmark() with given seed
   - If --compare PATH is given: loads previous benchmark, diffs, appends delta to graphify-out/progressive.json
   - If --scale huge is given: includes 5M-node tier (default skips it)
   - Prints a summary table with all scale tiers

3. Create tests/test_benchmark_query.py with tests covering generate_bsbm_graph, benchmark_query_latency, benchmark_pathfinding, benchmark_memory.

4. Run `pytest tests/ -q` to verify nothing is broken. Run `graphify benchmark` on a real graph to verify CLI works. Run `graphify benchmark --scale huge` to test the 5M tier gates. Confirm `graphify-out/progressive.json` is written when `--compare` is used.

5. Commit: `git add -A && git commit -m "feat(phase-1): fork baseline + benchmark suite"`

Use existing code patterns from graphify/benchmark.py and __main__.py. Match the code style exactly. No new dependencies needed.
```
