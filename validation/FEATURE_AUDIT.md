# Graphify Fork Feature Audit — Query/Path/Explain Quality Impact
**Graph:** `/Users/hoang/graphify/validation/out-speedai/graph.json`
**Corpus:** existing graph
**Mode:** AST-only (structural pipeline only)
**Date:** 2026-04-30

---

## Legend
- **OFF** = baseline (all fork features disabled)
- **ON** = this feature enabled independently
- **Δ** = ON − OFF; ↑ = higher is better for this metric
- **Quality?** = qualitative judgment of direction
- Metrics: **nodes** = BFS subgraph nodes (lower is more focused), **deg** = median explain degree (lower is more focused), **hops** = path hop count (lower is shorter)

## Category A: Query-Time Features

| Feature | BFS nodes | BFS edges | BFS ms | Path hops | Path ms | Expl. deg | Quality? |
|---------|-----------|-----------|--------|-----------|---------|-----------|----------|
| index.py (conf-filter) | 31,510.5 → 31,510.5 | 56,243.5 → 56,243.5 | 19.5ms → 37.3ms | 3 → 3 | 0.4ms → 0.4ms | 39.5 → 39.5 | ⚠ slower |
| query_planner.py | 31,510.5 → 31,510.5 | 56,243.5 → 56,243.5 | 19.5ms → 18.4ms | 3 → 3 | 0.4ms → 0.3ms | 39.5 → 39.5 | ✓ speed 18.4ms < 19.5ms |
| search/hybrid.py | 31,510.5 → 31,510.5 | 56,243.5 → 56,243.5 | 19.5ms → 18.1ms | 3 → 3 | 0.4ms → 0.8ms | 39.5 → 39.5 | ✓ speed 18.1ms < 19.5ms |
| approx.py (bloom) | 31,510.5 → 31,510.5 | 56,243.5 → 56,243.5 | 19.5ms → 20.3ms | 3 → 3 | 0.4ms → 0.3ms | 39.5 → 39.5 | ⚠ mixed |
| approx.py (sampling 10%) | 31,510.5 → 31,510.5 | 56,243.5 → 56,243.5 | 19.5ms → 17.9ms | 3 → 3 | 0.4ms → 0.7ms | 39.5 → 39.5 | ✓ speed 17.9ms < 19.5ms |
| matviews.py | 31,510.5 → 31,510.5 | 56,243.5 → 56,243.5 | 19.5ms → 19.6ms | 3 → 3 | 0.4ms → 0.3ms | 39.5 → 39.5 | ⚠ mixed |
| code_schema.py (types) | 31,510.5 → 31,510.5 | 56,243.5 → 56,243.5 | 19.5ms → 20.1ms | 3 → 3 | 0.4ms → 0.3ms | 39.5 → 39.5 | ⚠ mixed |

## Category B: Build-Time Features

_No build-time features measured. Run with a corpus to enable._

Build-time features require `--corpus` to rebuild the graph:
```bash
python validation/measure_features.py --corpus validation/corpora/toycorp
```

## Category C: Integration Features (not measurable on structural benchmark)

| Feature | Module | Reason not measurable |
|---------|--------|-----------------------|
| skills/ (agent skills) | skills/ |  generates SKILL.md per community, not query-able |
| groups.py (multi-repo) | groups.py |  cross-repo group management, not measurable on single repo |
| lazy_pool.py | lazy_pool.py |  graph LRU pool for multi-repo, no effect on single repo |
| registry.py | registry.py |  ~/.graphify/registry cross-repo index, not measurable |
| contract_bridge.py | contract_bridge.py |  cross-repo interface bridging, not measurable |
| hooks.py (git hooks) | hooks.py |  post-commit hooks, not measurable on benchmark |
| __main__.py (platform installers) | 14-platform install |  integration only, not measurable |
| wiki.py (wiki export) | wiki.py |  export format, not measurable on benchmark |
| export.py (formats) | export.py |  HTML/SVG/Obsidian/GraphML/Neo4j exports, not measurable |
| report.py (report gen) | report.py |  GRAPH_REPORT.md generation, part of pipeline not query |

---

## Notes
- Hybrid search quality requires a labeled test set; structural benchmark only shows search selects DIFFERENT nodes
- Call resolution must be benchmarked with `--corpus` flag to rebuild graph
- Cumulative stacking effect is NOT the sum of individual deltas (features interact)
- Lower BFS nodes/edges/degree = more focused results. This is a proxy for quality, not ground truth.
