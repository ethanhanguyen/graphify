# PR 2: Indexing Layer + Advanced Traversal

**Phases:** 2-3
**Stream:** A (Query Engine)
**Estimate:** 5-7 days
**Depends on:** Phase 1 (benchmark suite for measuring improvement)

## What to Build

### 1. Indexing Layer (`graphify/index.py` — NEW)

Three indexes built at graph load time, stored in `G.graph["indexes"]`:

**Edge Relation Type Index:**
```python
def build_edge_index(G) -> dict[str, list[tuple[str, str, dict]]]:
    """Hash map: relation_type → [(u, v, edge_data), ...].
    Speeds filtered traversal from O(E) scan to O(1) lookup."""

def get_edges_by_relation(G, relation_type: str) -> list:
    """Return all edges of a given relation_type using the index."""

def get_neighbors_by_relation(G, node: str, relation_type: str) -> list:
    """Return neighbors connected by a specific relation."""
```

**Confidence Bitmap Filter:**
```python
def build_confidence_bitmap(G) -> dict:
    """Three lists: EXTRACTED, INFERRED, AMBIGUOUS.
    Each stores the edge keys for O(1) confidence filtering."""

def filter_edges_by_confidence(G, edges, min_confidence: str = "INFERRED") -> list:
    """Return only edges meeting confidence threshold.
    EXTRACTED > INFERRED > AMBIGUOUS (no dependency on bitarray)."""
```

**Node Label Inverted Index:**
```python
def build_label_index(G) -> dict:
    """Prefix hash map: first 3 chars of normalized label → [node_ids].
    Replaces linear scan in _score_nodes() with sub-millisecond lookup."""

def lookup_nodes_by_prefix(prefix: str, index: dict) -> list[str]:
    """Return node IDs whose normalized label starts with prefix."""
```

**Integration function:**
```python
def build_indexes(G) -> dict:
    """Build all three indexes. Returns dict stored as G.graph['indexes'].
    Called from build_from_json() when build_indexes=True."""
```

### 2. Traversal Additions (`graphify/serve.py` — EXTEND)

**Bidirectional BFS:**
```python
def _bidirectional_shortest_path(G, src: str, tgt: str, max_hops: int = 20) -> tuple[list, float]:
    """BFS from both src and tgt simultaneously.
    Returns (path_nodes, path_length). Uses edge relation index if available."""
```

**Weighted Dijkstra:**
```python  
def _dijkstra_shortest_path(G, src: str, tgt: str) -> tuple[list, float]:
    """Uses edge['weight'] field. Returns (path, total_weight)."""
```

**A* with Community Heuristic:**
```python
def _astar_search(G, src: str, tgt: str, communities: dict, max_hops: int = 20) -> list:
    """Heuristic: h(n) = 1 if community(n) != community(target) else 0.5."""
```

**Update `_score_nodes` to use label index:**
```python
def _score_nodes(G, terms: list[str]) -> list[tuple[float, str]]:
    """Same signature. Uses G.graph['indexes']['label_index'] if available,
    falls back to linear scan for backward compatibility."""
```

**Update query_graph handler:**
- Add `mode="bidirectional"` — uses _bidirectional_shortest_path
- Add `mode="astar"` — uses _astar_search
- Keep `mode="bfs"` and `mode="dfs"` as defaults

**Update shortest_path handler:**
- Add `weighted=True` parameter — uses _dijkstra_shortest_path
- Add `mode="bidirectional"` — uses _bidirectional_shortest_path

**Update `_tool_query_graph` inputSchema:**
- mode enum: "bfs", "dfs", "bidirectional", "astar"

**Update `_tool_shortest_path` inputSchema:**
- Add "weighted" (boolean, default false)
- Add "mode" (string, enum: "default", "bidirectional")

### 3. Build Integration (`graphify/build.py` — EXTEND)

Add `build_indexes` parameter to `build_from_json()`:
```python
def build_from_json(extraction: dict, *, directed: bool = False, build_indexes: bool = True) -> nx.Graph:
    # ... existing code ...
    if build_indexes:
        from .index import build_indexes as _build_indexes
        G.graph["indexes"] = _build_indexes(G)
    return G
```

Also add to `build()` and `build_merge()`.

### 4. Tests

**`tests/test_index.py` (NEW, 8+ tests):**
```python
def test_build_edge_index():
def test_get_edges_by_relation():
def test_get_neighbors_by_relation():
def test_build_confidence_bitmap():
def test_filter_edges_by_confidence():
def test_build_label_index():
def test_lookup_nodes_by_prefix():
def test_indexes_stored_on_graph():
```

**`tests/test_serve.py` (EXTEND, add 7+ tests):**
```python
def test_bidirectional_shortest_path():
def test_bidirectional_no_path():
def test_bidirectional_max_hops_exceeded():
def test_dijkstra_with_weights():
def test_astar_with_communities():
def test_astar_stays_in_community():
def test_query_graph_bidirectional_mode():
def test_shortest_path_weighted():
```

## Files Changed/Created

| File | Action | Purpose |
|------|--------|---------|
| `graphify/index.py` | **New** | Three-index system (edge relation, confidence bitmap, label) |
| `graphify/build.py` | **Extend** | build_indexes parameter, call build_indexes() |
| `graphify/serve.py` | **Extend** | Bidirectional BFS, A*, Dijkstra, new modes, index usage |
| `tests/test_index.py` | **New** | Index layer tests |
| `tests/test_serve.py` | **Extend** | Traversal mode tests |

## Compatibility
- All existing MCP tool signatures unchanged (additive only)
- `build_indexes=True` by default, has no effect if no index.py imported
- `_bfs()` and `_dfs()` preserved, new functions are separate
- graph.json format unchanged (indexes stored in G.graph metadata, not serialized)
- Existing mode="bfs"/"dfs" still work as defaults

## Verification
```bash
pytest tests/test_index.py tests/test_serve.py -q
pytest tests/ -q  # all existing tests still pass
python -c "from graphify.index import build_indexes; print('OK')"
```

### Commit

```bash
git add -A && git commit -m "feat(phase-2-3): edge index + bidirectional BFS + A* + Dijkstra"
```

---

## Code Review Checklist

Before merging this PR, verify:
- [ ] All tests pass: `pytest tests/ -q`
- [ ] `graphify benchmark --compare` shows QPS improvement over Phase 1 baseline
- [ ] Bidirectional BFS finds same paths as unidirectional on identical inputs
- [ ] Indexes built with `build_indexes=True`, skipped with `build_indexes=False`
- [ ] No breaking changes to existing `_bfs()` / `_dfs()` functions
- [ ] Content-based .edges file format: 426 lines (not 425)
- [ ] MCP tool `mode` enum supports new values without breaking old ones
- [ ] At least 1 other developer reviewed

### Progressive Benchmark

```bash
graphify benchmark --seed 42 --compare graphify-out/benchmark.json --output graphify-out/benchmark.json
```

This:
- Loads Phase 1 baseline from `graphify-out/benchmark.json`
- Re-runs benchmark on same graph with indexes enabled (same seed for reproducibility)
- Diffs results, appends `{"phase": "2-indexing", "deltas": {...}}` to `graphify-out/progressive.json`
- Overwrites `benchmark.json` with current results (becomes new baseline for next phase)

---

## Prompt (paste into AI coding agent)

```
You are implementing Phases 2-3 of the Graphify fork enhancement plan.

Repository: ~/graphify
Branch: feat/phase-2-3-indexing-traversal

TASK: Build the indexing layer and advanced traversal methods.

## PART A: Indexing Layer

Create graphify/index.py with these functions:

1. build_edge_index(G) → dict[str, list[tuple]]: Hash map from relation_type to list of (u, v, edge_data). Built once at graph load. Speeds filtered traversal from O(E) scan to O(1) lookup.

2. get_edges_by_relation(G, relation_type) → list: Uses index if available, falls back to linear scan.

3. get_neighbors_by_relation(G, node, relation_type) → list: Neighbors connected by specific relation type.

4. build_confidence_bitmap(G) → dict with keys "EXTRACTED", "INFERRED", "AMBIGUOUS": Each maps to a list of edge tuples (u, v). Allows O(1) filtering by confidence tier.

5. filter_edges_by_confidence(G, edges, min_confidence) → list: Return only edges at or above confidence threshold. EXTRACTED > INFERRED > AMBIGUOUS. Falls back if no bitmap.

6. build_label_index(G) → dict: Prefix hash from first 3 chars of normalized label to list of node_ids. For sub-millisecond lookup replacing linear scan.

7. lookup_nodes_by_prefix(prefix, index) → list[str]: Look up by prefix.

8. build_indexes(G) → dict: Build all three indexes. Store result as {"edge_relation": ..., "confidence_bitmap": ..., "label_index": ...}.

## PART B: update build.py

In build_from_json(extraction, *, directed=False, build_indexes=True):
- At the end, if build_indexes: call build_indexes(G) and store result as G.graph["indexes"]
- Also propagate build_indexes through build() and build_merge() with same default

## PART C: Advanced Traversal in serve.py

Add these functions (keep existing _bfs and _dfs):

9. _bidirectional_shortest_path(G, src, tgt, max_hops=20) → (list, float): BFS from both ends. Uses index if available. Returns (path_nodes, path_length).

10. _dijkstra_shortest_path(G, src, tgt) → (list, float): Uses edge weight field. Returns (path, total_weight).

11. _astar_search(G, src, tgt, communities_dict, max_hops=20) → list: A* with heuristic h(n) = 1 if different community else 0.5.

12. Update _score_nodes(G, terms): Use G.graph["indexes"]["label_index"] if available, fall back to linear scan.

13. Update _tool_query_graph handler: Add mode="bidirectional" and mode="astar" options. Update inputSchema enum.

14. Update _tool_shortest_path handler: Add weighted=True and mode="bidirectional" parameters. Update inputSchema.

## PART D: Tests

15. Create tests/test_index.py with 8+ tests covering all index functions.

16. Add 8+ tests to tests/test_serve.py: _bidirectional_shortest_path (normal, no-path, max-hops-exceeded), _dijkstra_shortest_path, _astar_search (normal, stays-in-community), query_graph with bidirectional/astar modes, shortest_path with weighted=True.

MATCH EXISTING CODE STYLE. Keep _bfs/_dfs unchanged. All new functions go AFTER existing ones. Use the exact test patterns from test_serve.py (see _make_graph helper, assert patterns).

RUN `pytest tests/ -q` after implementation. All tests must pass.

RUN `graphify benchmark --seed 42 --compare graphify-out/benchmark.json --output graphify-out/benchmark.json` to capture the progressive improvement over Phase 1 baseline.

RUN `git add -A && git commit -m "feat(phase-2-3): edge index + bidirectional BFS + A* + Dijkstra"`
```
