# PR 4: Approximate Methods + Final Benchmark

**Phases:** 6-7
**Stream:** A (Query Engine)  
**Estimate:** 4-6 days
**Depends on:** Phase 4-5 (cache + matviews)

## What to Build

### 1. Bloom Filter (`graphify/approx.py` — NEW)

```python
import hashlib
from typing import Set, Tuple

class GraphBloomFilter:
    """Bloom filter for O(1) "does this edge exist?" checks.
    Key format: "{relation}:{confidence}:{src_label}:{tgt_label}"
    Uses bit array + k hash functions for probabilistic membership.
    No external dependencies — pure Python implementation using built-in hashlib."""
    
    def __init__(self, capacity: int, error_rate: float = 0.01):
        """capacity: expected number of elements. error_rate: false positive rate."""
        
    def add_edge(self, relation: str, confidence: str, src_label: str, tgt_label: str) -> None:
        """Add edge to bloom filter."""
        
    def likely_contains(self, relation: str, confidence: str, src_label: str, tgt_label: str) -> bool:
        """Check if edge might exist. False = definitely not. True = probably."""
        
    @property
    def size_bits(self) -> int:
        """Size of bit array in bits."""
        
    @classmethod
    def from_graph(cls, G, error_rate: float = 0.01) -> 'GraphBloomFilter':
        """Build bloom filter from an existing graph. Adds all edges."""

def build_path_bloom_filter(G, relation_type: str = "calls") -> GraphBloomFilter:
    """Build a bloom filter for path existence checks.
    Used by always-on hook: "Is there an auth-related path? No → skip GRAPH_REPORT.md" """
```

### 2. Graph Sampling (`graphify/approx.py` — EXTEND)

```python
import random

def sample_subgraph_nodes(G, sample_rate: float = 0.1, method: str = "random_walk",
                          seed: int = 42) -> set[str]:
    """Sample nodes from graph.
    random_walk: preserves community proportions via random walks.
    stratified: proportional sampling from each community.
    Returns set of sampled node IDs."""

def sample_subgraph(G, sample_rate: float = 0.1, method: str = "random_walk") -> nx.Graph:
    """Return induced subgraph on sampled nodes."""

def estimate_graph_from_sample(sampled_G, original_node_count: int) -> dict:
    """Estimate full graph stats from sample: node count, edge count, avg degree, density."""

def is_path_likely(bf: GraphBloomFilter, relation: str, src: str, tgt: str) -> bool:
    """Quick existence check using bloom filter. Returns True if path might exist."""
```

### 3. Embeddings (`graphify/embed.py` — NEW, optional)

```python
"""Node embedding generation. Requires: numpy (optional dependency)."""
import hashlib
from pathlib import Path

EMBEDDING_DIM = 128

def _import_numpy():
    """Lazy import — embeddings are optional."""
    import numpy as np
    return np

def generate_simple_embeddings(G, dimensions: int = EMBEDDING_DIM, seed: int = 42) -> dict[str, list[float]]:
    """Generate node embeddings using a deterministic random projection approach.
    No heavy ML deps needed. Each node gets a random vector seeded by its label/content hash.
    For production use, swap in node2vec/SDNE when numpy+scipy are available."""
    np = _import_numpy()
    rng = np.random.RandomState(seed)
    embeddings = {}
    for node_id, data in G.nodes(data=True):
        label = data.get("label", node_id)
        content_hash = hashlib.sha256(label.encode()).digest()
        node_seed = int.from_bytes(content_hash[:4], 'big')
        vec = rng.RandomState(node_seed).randn(dimensions)
        vec = vec / (np.linalg.norm(vec) + 1e-8)
        embeddings[node_id] = vec.tolist()
    return embeddings

def compute_cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two vectors (pure Python for portability)."""
    ...

def search_similar_nodes(query_vec: list[float], embeddings: dict[str, list[float]],
                          top_k: int = 10) -> list[tuple[str, float]]:
    """Return top-k most similar nodes by cosine similarity to query vector."""

def save_embeddings(embeddings: dict[str, list[float]], output_path: Path) -> None:
    """Save embeddings as JSON. Keys are node IDs, values are float lists."""

def load_embeddings(input_path: Path) -> dict[str, list[float]]:
    """Load embeddings from JSON file."""

def get_query_embedding(query_text: str, dimensions: int = EMBEDDING_DIM) -> list[float]:
    """Generate a query embedding from text using the same deterministic approach."""
    np = _import_numpy()
    content_hash = hashlib.sha256(query_text.encode()).digest()
    seed = int.from_bytes(content_hash[:4], 'big')
    vec = np.random.RandomState(seed).randn(dimensions)
    return (vec / (np.linalg.norm(vec) + 1e-8)).tolist()
```

### 4. Approximate Query Mode (`graphify/serve.py` — EXTEND)

Add approximate mode to `query_graph`:
```python
# New parameters in query_graph inputSchema:
#   approximate: boolean, default false
#   sample_rate: float, default 0.1 (used when approximate=true)

def _approximate_query(G, question, sample_rate=0.1, depth=3, budget=2000) -> str:
    """Query on a sampled subgraph. ~10x faster, ~90% accuracy."""
    sampled = sample_subgraph(G, sample_rate)
    # Run BFS on sampled graph
    ...
```

Add bloom filter pre-check:
```python
def _should_skip_query(G, question, bloom_filter) -> bool:
    """Check if question has any likely relevant paths via bloom filter.
    Returns True if definitely no paths exist → skip expensive traversal."""
    ...
```

### 5. Benchmark Runner (`graphify/benchmark.py` — EXTEND)

```python
def benchmark_phases(G) -> dict:
    """Run benchmarks comparing all phases:
    Phase 1 (baseline): BFS/DFS raw
    Phase 2-3 (indexed): BFS/DFS with indexes
    Phase 4-5 (cached): queries with cache+planner
    Phase 6 (approx): approximate queries at various sample rates
    
    Returns dict with comparison tables."""
    
def benchmark_approximate_accuracy(G, num_queries: int = 50, seed: int = 42) -> dict:
    """Measure speed vs accuracy tradeoff for approximate queries.
    Compares approximate BFS results against exact full-graph BFS ground truth:
      precision = |approx ∩ exact| / |approx|
      recall    = |approx ∩ exact| / |exact|
      f1        = 2 * precision * recall / (precision + recall)
    Runs at sample_rates: [0.05, 0.10, 0.25, 0.50].
    Returns {sample_rate: {precision, recall, f1, speedup_mult, p95_ms}}."""

def generate_progressive_report(progressive_path: str = "graphify-out/progressive.json",
                                output_path: str = "graphify-out/PROGRESSIVE.md") -> str:
    """Read progressive.json and generate a markdown attribution report.
    Table shows per-phase metrics at each scale tier:
    
    | Phase | QPS (50K) | p95 ms (50K) | Mem MB (50K) | Key Gain |
    |-------|-----------|-------------|-------------|----------|
    | 1-baseline | 80 | 45.8 | 52 | — |
    | 2-indexing | 950 | 3.2 | 60 | +1087% QPS |
    | 3-queryplan | 1800 | 1.8 | 62 | +89% QPS |
    | 4-approximate | 4200 | 0.4 | 64 | +133% QPS |
    
    Also includes "Top Gains" section attributing each improvement to a specific feature.
    Returns path to generated report."""

def benchmark_at_scale(G, scale: str = "huge") -> dict:
    """Run full benchmark at a specific scale tier.
    scale: "small" (50K), "medium" (100K), "large" (500K), "xlarge" (1M), "huge" (5M).
    Returns benchmark dict for that tier."""
```

### 6. Tests

**`tests/test_approx.py` (NEW, 5+ tests):**
```python
def test_bloom_filter_add_and_contains():
def test_bloom_filter_false_positive_rate():
def test_bloom_filter_from_graph():
def test_sample_subgraph_size():
def test_sample_subgraph_preserves_communities():
def test_is_path_likely():
```

**`tests/test_embed.py` (NEW, if numpy available):**
```python
import pytest
numpy = pytest.importorskip("numpy")

def test_generate_embeddings_output_shape():
def test_cosine_similarity_identical():
def test_cosine_similarity_orthogonal():
def test_search_similar_nodes():
```

**`tests/test_benchmark_query.py` (EXTEND):**
```python
def test_benchmark_approximate_accuracy():
def test_benchmark_approximate_precision_recall():
    """Verify precision=1.0 and recall=1.0 when sample_rate=1.0 (full graph)."""
def test_benchmark_phases_comparison():
```

## Files Changed/Created

| File | Action | Purpose |
|------|--------|---------|
| `graphify/approx.py` | **New** | Bloom filter, graph sampling, approximate queries |
| `graphify/embed.py` | **New** | Node embeddings (optional, numpy needed) |
| `graphify/serve.py` | **Extend** | Approximate query mode, bloom pre-check |
| `graphify/benchmark.py` | **Extend** | Phase comparison, approximate accuracy benchmarks |
| `tests/test_approx.py` | **New** | Bloom filter + sampling tests |
| `tests/test_embed.py` | **New** | Embedding tests |

## Compatibility
- Approximate mode is additive: `approximate=True` on query_graph, defaults to False
- Bloom filter stored in G.graph metadata, not serialized to graph.json
- Embedding file: `graphify-out/embeddings.json`
- numpy is optional — embed.py gracefully degrades without it

## Verification
```bash
pytest tests/test_approx.py tests/test_embed.py -q
pytest tests/test_benchmark_query.py -q
pytest tests/ -q  # full suite
```

### Progressive Benchmark (Final)

```bash
# 1. Compare against Phase 4-5 baseline
graphify benchmark --seed 42 --compare graphify-out/benchmark.json --output graphify-out/benchmark.json

# 2. Run full scale (including 5M)
graphify benchmark --seed 42 --scale huge --output graphify-out/benchmark_final.json

# 3. Generate attribution report
python -c "from graphify.benchmark import generate_progressive_report; generate_progressive_report()"

# 4. Read the report
cat graphify-out/PROGRESSIVE.md
```

`PROGRESSIVE.md` shows the per-phase attribution chain: which feature delivered what improvement, at each scale tier.

### Commit

```bash
git add -A && git commit -m "feat(phase-6-7): bloom filter + graph sampling + embeddings + final benchmark report"
```

---

## Code Review Checklist

Before merging this PR, verify:
- [ ] All tests pass: `pytest tests/ -q`
- [ ] `PROGRESSIVE.md` generated with correct attribution table
- [ ] Bloom filter FP rate ≤ configured error_rate on test graph
- [ ] Graph sampling preserves community proportions (K-S test vs original)
- [ ] Approximate queries show precision ≥ 0.85, recall ≥ 0.80 at sample_rate=0.25
- [ ] Embeddings L2 normalize and cosine similarity are correct
- [ ] numpy optional — all benchmarks work without it
- [ ] No breaking changes to existing MCP tools or APIs
- [ ] At least 1 other developer reviewed

---

## Prompt (paste into AI coding agent)

```
You are implementing Phases 6-7 of the Graphify fork enhancement plan.

Repository: ~/graphify
Branch: feat/phase-6-7-approximate-benchmark

TASK: Build approximate query methods, embeddings, and final benchmark comparison.

## PART A: Approximate Methods (graphify/approx.py)

Create graphify/approx.py:

1. class GraphBloomFilter:
   - __init__(capacity, error_rate=0.01): Set up bit array size and k hash functions. Pure Python (bytesarray + hashlib, no external deps).
   - add_edge(relation, confidence, src_label, tgt_label): Add key to filter.
   - likely_contains(relation, confidence, src_label, tgt_label) → bool.
   - size_bits property.
   - from_graph(G, error_rate) classmethod: Build from existing graph.

2. build_path_bloom_filter(G, relation_type="calls") → GraphBloomFilter: Build for path existence pre-checks.

3. sample_subgraph_nodes(G, sample_rate=0.1, method="random_walk", seed=42) → set[str]: Sample nodes. random_walk method: pick random start, walk to random neighbors, preserving community proportions.

4. sample_subgraph(G, sample_rate=0.1) → nx.Graph: Return G.subgraph(sampled_nodes).

5. estimate_graph_from_sample(sampled_G, original_node_count) → dict: Estimate full graph stats from sample.

6. is_path_likely(bf, relation, src, tgt) → bool: Quick bloom check before expensive traversal.

## PART B: Embeddings (graphify/embed.py)

Create graphify/embed.py. numpy is optional — use lazy import:

7. generate_simple_embeddings(G, dimensions=128, seed=42) → dict[str, list[float]]: Deterministic random projection embeddings. Each node's vector seeded by content hash of its label. L2 normalized.

8. compute_cosine_similarity(vec1, vec2) → float: Pure Python implementation.

9. search_similar_nodes(query_vec, embeddings, top_k=10) → list[tuple[str, float]]: Return top-k by cosine similarity.

10. save_embeddings / load_embeddings: JSON I/O.

11. get_query_embedding(query_text, dimensions=128) → list[float]: Deterministic query vector.

## PART C: Integration in serve.py

12. Add approximate query mode to _tool_query_graph:
    - New inputSchema params: approximate (bool, default false), sample_rate (float, default 0.1)
    - When approximate=True, sample graph first, then run BFS/DFS
    - Prefix output with "[APPROXIMATE] " to signal to agent

13. Add bloom pre-check helper: _should_skip_query(G, question, bloom) → bool. Check bloom filter before traversal. Save boolean in graph metadata.

## PART D: Benchmark Extension (graphify/benchmark.py)

14. benchmark_phases(G) → dict: Run and compare all phases. Measure: BFS baseline, indexed BFS, cached BFS, approximate BFS at 10%/25%/50% sample rates. Return comparison table as dict.

15. benchmark_approximate_accuracy(G, num_queries=50, seed=42) → dict: Run same queries on both approximate subgraph AND exact full graph. Compute precision, recall, f1 at sample_rates [0.05, 0.10, 0.25, 0.50]. Return per-rate dict with precision/recall/f1/speedup/p95_ms.

16. generate_progressive_report(progressive_path, output_path) → str: Read progressive.json, generate `PROGRESSIVE.md` markdown report with per-phase attribution table and "Top Gains" section. Each phase row shows metrics at every scale tier. Returns path to report.

17. benchmark_at_scale(G, scale="huge") → dict: Run full benchmark at a specific scale tier (small/medium/large/xlarge/huge).

## PART E: Tests

16. Create tests/test_approx.py with 5+ tests (bloom filter, sampling).
17. Create tests/test_embed.py with 4+ tests (skip if no numpy: `pytest.importorskip("numpy")`).
18. Add 2 benchmark tests to tests/test_benchmark_query.py.

MATCH EXISTING CODE STYLE. Use existing test patterns. numpy is OPTIONAL — all core logic works without it.

RUN `pytest tests/ -q` after implementation. All tests must pass.

RUN `graphify benchmark --seed 42 --compare graphify-out/benchmark.json --output graphify-out/benchmark.json` to capture final progressive delta.

RUN `graphify benchmark --seed 42 --scale huge --output graphify-out/benchmark_final.json` to run the full 5M scale.

RUN `python -c "from graphify.benchmark import generate_progressive_report; print(generate_progressive_report())"` to generate `graphify-out/PROGRESSIVE.md` — the final attribution report.

RUN `git add -A && git commit -m "feat(phase-6-7): bloom filter + graph sampling + embeddings + final benchmark report"`
```
