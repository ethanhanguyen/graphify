# PR 3: Query Planning + Caching + Materialized Views

**Phases:** 4-5
**Stream:** A (Query Engine)
**Estimate:** 4-6 days
**Depends on:** Phase 2-3 (indexes must exist)

## What to Build

### 1. Query Planner (`graphify/query_planner.py` — NEW)

```python
def select_start_nodes_by_degree(G, candidates: list[str]) -> str:
    """From scored candidates, pick the one with lowest degree.
    This is the most selective start point, minimizing fan-out."""
    
def order_frontier_by_confidence(G, frontier: list[str], preference: str = "extracted") -> list[str]:
    """Prefer traversing EXTRACTED edges before INFERRED before AMBIGUOUS.
    Uses confidence bitmap index if available."""
    
def reorder_frontier_at_hop(G, current_frontier: set[str], visited: set[str]) -> list[str]:
    """At each BFS hop, reorder frontier: lowest-degree nodes first,
    EXTRACTED edges first, INFERRED edges second."""
```

### 2. Query Result Cache (`graphify/query_cache.py` — NEW)

```python
import hashlib, time, json
from pathlib import Path

CACHE_TTL = 3600  # 1 hour

def cache_key(query_text: str, mode: str, depth: int, budget: int) -> str:
    """SHA256 of (query_text, mode, depth, budget)."""
    return hashlib.sha256(
        f"{query_text}|{mode}|{depth}|{budget}".encode()
    ).hexdigest()

def get_cached_query(cache_dir: Path, key: str) -> str | None:
    """Load cached result if exists and not expired.
    Cache files stored as cache_dir/{key}.txt.
    Each file has first line as timestamp, rest is result."""

def set_cached_query(cache_dir: Path, key: str, result: str) -> None:
    """Store query result as cache_dir/{key}.txt.
    Writes atomic (write to .tmp, rename)."""

def clear_expired_cache(cache_dir: Path, ttl: int = CACHE_TTL) -> int:
    """Remove expired cache entries. Returns count removed."""

def cache_stats(cache_dir: Path) -> dict:
    """Return {entries, hits, misses, hit_rate} from cache directory."""
```

### 3. Materialized Views (`graphify/matviews.py` — NEW)

```python
def compute_transitive_closure(G, relation_type: str) -> dict[tuple, int]:
    """Compute transitive closure over edges of a given relation type.
    Returns {(u, v): hop_distance} for all reachable pairs."""
    
def write_materialized_view(closure: dict[tuple, int], relation_type: str, output_dir: Path) -> None:
    """Write closure as edge list: one line per (u, v, distance).
    Stored in output_dir/{relation_type}.edges"""

def load_materialized_view(relation_type: str, input_dir: Path) -> dict[tuple, int] | None:
    """Load precomputed closure. Returns None if not found."""
    
def check_materialized_path(G, src: str, tgt: str, relation_type: str, 
                            matviews_dir: Path) -> int | None:
    """O(1) lookup: is there a path of 'relation_type' edges from src to tgt?
    Returns hop distance or None."""
    
# Precomputed closure types:
# - "calls": all 'calls' edges transitively closed
# - "imports": all 'imports' + 'imports_from' closures
```

### 4. Serve Integration (`graphify/serve.py` — EXTEND)

**Update query_graph handler** to use:
- Query planner: reorder frontier at each hop
- Query cache: check cache before running BFS, cache result after
- Edge selectivity: prefer extracted edges first

**New inputSchema fields:**
```
query_graph:
  use_cache: boolean, default true  ← new
  prefer: string, enum: "extracted", "inferred", "all"  ← new
  materialize: boolean, default false  ← new
```

**Update shortest_path handler** to:
- Check materialized views first (O(1) lookup)
- Fall back to traversal if no cached closure

### 5. Build Integration (`graphify/build.py` — EXTEND)

Add `materialize` parameter:
```python
def build_from_json(extraction: dict, *, directed: bool = False,
                    build_indexes: bool = True,
                    materialize: list[str] | None = None) -> nx.Graph:
    """If materialize=["calls", "imports"], compute transitive closures."""
    # ... after graph construction ...
    if materialize:
        from .matviews import compute_transitive_closure, write_materialized_view
        for rel_type in materialize:
            closure = compute_transitive_closure(G, rel_type)
            write_materialized_view(closure, rel_type, Path("graphify-out/matviews"))
    return G
```

**New CLI flag:**
```
graphify build --materialize=calls,imports  # Precompute closures
```

### 6. Tests

**`tests/test_query_planner.py` (NEW, 5+ tests):**
```python
def test_select_lowest_degree_start():
def test_reorder_by_confidence():
def test_cardinality_estimation():
def test_reorder_frontier_at_hops():
def test_planner_with_empty_frontier():
```

**`tests/test_query_cache.py` (NEW, 6+ tests):**
```python
def test_cache_key_deterministic():
def test_set_and_get_cached_query(tmp_path):
def test_expired_cache_not_returned(tmp_path):
def test_clear_expired_cache(tmp_path):
def test_cache_miss_returns_none(tmp_path):
def test_cache_stats(tmp_path):
```

**`tests/test_matviews.py` (NEW, 4+ tests):**
```python
def test_compute_transitive_closure_calls():
def test_write_and_load_materialized_view(tmp_path):
def test_check_materialized_path_found():
def test_check_materialized_path_not_found():
```

## Files Changed/Created

| File | Action | Purpose |
|------|--------|---------|
| `graphify/query_planner.py` | **New** | Degree-based start selection, confidence-ordered frontier |
| `graphify/query_cache.py` | **New** | SHA256-keyed query result cache with TTL |
| `graphify/matviews.py` | **New** | Transitive closure computation and lazy loading |
| `graphify/build.py` | **Extend** | materialize parameter, CLI flag |
| `graphify/serve.py` | **Extend** | Query planner + cache + materialized view integration |
| `graphify/__main__.py` | **Extend** | --materialize flag on build subcommand |
| `tests/test_query_planner.py` | **New** | Query planner tests |
| `tests/test_query_cache.py` | **New** | Cache tests |
| `tests/test_matviews.py` | **New** | Materialized view tests |

## Compatibility
- All existing MCP tool signatures unchanged
- New parameters are additive with backward-compatible defaults
- Cache directory: `graphify-out/query_cache/`
- Materialized views directory: `graphify-out/matviews/`

## Verification
```bash
pytest tests/test_query_planner.py tests/test_query_cache.py tests/test_matviews.py -q
pytest tests/test_serve.py -q  # serve integration tests
pytest tests/ -q  # full suite
```

### Commit

```bash
git add -A && git commit -m "feat(phase-4-5): query planner + cache + materialized views"
```

---

## Code Review Checklist

Before merging this PR, verify:
- [ ] All tests pass: `pytest tests/ -q`
- [ ] `graphify benchmark --compare` shows QPS improvement over Phase 2-3 baseline
- [ ] Cache hit rate improves with repeated queries (cache_stats shows hits)
- [ ] Materialized closures produce correct transitive results vs BFS traversal
- [ ] Expired cache entries are evicted (TTL respected)
- [ ] No breaking changes to existing MCP tools or APIs
- [ ] Cache and matview directories under `graphify-out/` only
- [ ] At least 1 other developer reviewed

### Progressive Benchmark

```bash
graphify benchmark --seed 42 --compare graphify-out/benchmark.json --output graphify-out/benchmark.json
```

This:
- Loads Phase 2-3 baseline from `graphify-out/benchmark.json`
- Re-runs benchmark on same graph with cache+planner enabled (same seed for reproducibility)
- Diffs results, appends `{"phase": "3-query-planning", "deltas": {...}}` to `graphify-out/progressive.json`
- Overwrites `benchmark.json` with current results (becomes new baseline for next phase)

---

## Prompt (paste into AI coding agent)

```
You are implementing Phases 4-5 of the Graphify fork enhancement plan.

Repository: ~/graphify
Branch: feat/phase-4-5-query-planning-caching

TASK: Build query planner, result cache, and materialized views.

## PART A: Query Planner (graphify/query_planner.py)

Create graphify/query_planner.py:

1. select_start_nodes_by_degree(G, candidates) → str: From scored candidates, pick the one with lowest degree. Minimizes fan-out.

2. order_frontier_by_confidence(G, frontier, preference="extracted") → list[str]: Reorder frontier — prefer EXTRACTED edges before INFERRED before AMBIGUOUS.

3. reorder_frontier_at_hop(G, current_frontier, visited) → list[str]: At each BFS hop, reorder: lowest-degree nodes first, then confidence priority.

## PART B: Query Cache (graphify/query_cache.py)

Create graphify/query_cache.py:

4. cache_key(query_text, mode, depth, budget) → str: SHA256 hex digest.

5. get_cached_query(cache_dir, key) → str | None: Load from cache_dir/{key}.txt. File format: line 1 = timestamp (epoch), rest = result text. Return None if expired (>1hr TTL) or missing.

6. set_cached_query(cache_dir, key, result) → None: Write to cache_dir/{key}.txt. Atomic: write .tmp first, then rename. Create cache_dir if not exists.

7. clear_expired_cache(cache_dir, ttl=3600) → int: Remove expired entries. Return count.

8. cache_stats(cache_dir) → dict: Return {entries, hits, misses, hit_rate}. Track hits/misses via a simple counter file in cache_dir.

## PART C: Materialized Views (graphify/matviews.py)

Create graphify/matviews.py:

9. compute_transitive_closure(G, relation_type) → dict[tuple, int]: Iterate over edges matching relation_type. Compute all reachable pairs via transitive closure. Return {(u, v): hop_distance}.

10. write_materialized_view(closure, relation_type, output_dir) → None: Write edge list to output_dir/{relation_type}.edges. One line per entry: "u|v|distance".

11. load_materialized_view(relation_type, input_dir) → dict | None: Load from input_dir/{relation_type}.edges. Return None if file not found.

12. check_materialized_path(G, src, tgt, relation_type, matviews_dir) → int | None: O(1) lookup in precomputed closure.

## PART D: Integration

13. In graphify/serve.py, update _tool_query_graph:
    - Use query_planner.select_start_nodes_by_degree() to pick start node
    - Use query_planner.order_frontier_by_confidence() at each hop
    - Check query_cache before running search, cache result after
    - Add use_cache (bool), prefer (string: "extracted"|"inferred"|"all"), materialize (bool) to inputSchema

14. In graphify/serve.py, update _tool_shortest_path:
    - Check matviews.check_materialized_path() before traversing
    - Fall back to regular traversal if no cached closure

15. In graphify/build.py, extend build_from_json():
    - Add materialize: list[str] | None = None parameter
    - If materialize list provided, compute and write closures for each relation type

16. In graphify/__main__.py, add --materialize flag to the build subcommand.

## PART E: Tests

17. Create tests/test_query_planner.py with 5+ tests.
18. Create tests/test_query_cache.py with 6+ tests using tmp_path fixture.
19. Create tests/test_matviews.py with 4+ tests.

MATCH EXISTING CODE STYLE. Use same patterns as existing test files. All new cache/materialize directories go under graphify-out/.

RUN `pytest tests/ -q` after implementation. All existing tests must still pass.

RUN `graphify benchmark --seed 42 --compare graphify-out/benchmark.json --output graphify-out/benchmark.json` to capture the progressive improvement over Phase 2-3 baseline.

RUN `git add -A && git commit -m "feat(phase-4-5): query planner + cache + materialized views"`
```
