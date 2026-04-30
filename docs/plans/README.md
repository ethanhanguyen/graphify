# Graphify Fork Enhancement — Implementation Roadmap

**Fork source:** `safishamsi/graphify` (v0.5.5, Apache 2.0)
**Target fork:** TBD

## Structure

```
docs/plans/
├── README.md                  ← this file
├── spec.md                    ← technical specification (APIs, types, interfaces)
└── pr-prompts/
    ├── pr-1-baseline.md       ← Phase 1: Fork + baseline + benchmark suite
    ├── pr-2-indexing.md       ← Phase 2-3: Indexing layer + advanced traversal
    ├── pr-3-query-planning.md ← Phase 4-5: Query planning + caching + materialized views
    ├── pr-4-approximate.md    ← Phase 6-7: Approximate methods + benchmark
    ├── pr-5-code-schema.md    ← Phase 8: Typed code schema
    ├── pr-6-call-resolution.md← Phase 9: Call resolution engine
    ├── pr-7-process-tracing.md← Phase 10: Process tracing
    ├── pr-8-hybrid-search.md  ← Phase 11: Hybrid search (BM25 + semantic + RRF)
    ├── pr-9-agent-integration.md ← Phase 12: Agent integration layer
    └── pr-10-multi-repo.md    ← Phase 13: Multi-repo groups (Enterprise)
```

## Two Work Streams

### Stream A: Query Engine Optimization (Phases 1-7)

**Goal:** Make graph traversal faster and more efficient.
**Estimate:** 14-20 dev days

| Phase | PR | What | Days | Delivers |
|-------|-----|------|------|----------|
| 1 | pr-1 | Fork, dev env, benchmark suite | 1-2 | Baseline metrics |
| 2-3 | pr-2 | Edge relation index, confidence bitmap, node label trie, bidirectional BFS, A*, Dijkstra | 5-7 | 10-100x traversal speedup |
| 4-5 | pr-3 | Cardinality-based query planning, edge selectivity, query cache, materialized closures | 4-6 | Sub-millisecond cached queries |
| 6-7 | pr-4 | Bloom filters, graph sampling, embeddings, benchmark vs baseline | 4-6 | Approximate query at scale |

### Stream B: Code Intelligence Enhancement (Phases 8-13)

**Goal:** Close the feature gap with GitNexus under Apache 2.0 license.
**Estimate:** 12-16 weeks

| Phase | PR | What | Weeks | Delivers |
|-------|-----|------|-------|----------|
| 8 | pr-5 | Typed code schema (44 node types, 21 edge types) | 2-3 | Code-aware graph representation (>90% node type coverage) |
| 9 | pr-6 | Call resolution engine (6-stage DAG, MRO walk) | 3-4 | "What calls X?" answers (+ resolution coverage benchmark) |
| 10 | pr-7 | Process tracing (entry point → call chain) | 2-3 | Blast radius, change impact (+ tracing throughput benchmark) |
| 11 | pr-8 | Hybrid search (BM25 + semantic + RRF) | 2-3 | Ranked codebase queries (+ search latency/overlap benchmark) |
| 12 | pr-9 | Agent integration (skills, hooks, context injection) | 1-2 | Auto-generated agent config (+ completeness validation) |
| 13 | pr-10 | Multi-repo groups (registry, lazy pool, contract bridge) | 2-3 | Enterprise monorepo support (+ cross-repo scale benchmark) |

## Dependency Order

```
Phase 1 (Baseline)
    │
    ├──► Phase 2-3 (Indexing + Traversal)
    │        │
    │        └──► Phase 4-5 (Query Planning + Caching)
    │                 │
    │                 └──► Phase 6-7 (Approximate + Benchmark)
    │
    └──► Phase 8 (Code Schema)
             │
             ├──► Phase 9 (Call Resolution)
             │        │
             │        └──► Phase 10 (Process Tracing)
             │                 │
             │                 └──► Phase 11 (Hybrid Search)
             │                          │
             │                          └──► Phase 12 (Agent Integration)
             │
             └──► Phase 13 (Multi-Repo Groups) — can start after Phase 8
```

### Parallel Execution Plan

After Phase 1 + Phase 8 are done, three devs can work in parallel:

| Wave | PRs (parallel) | Prereqs | Combined Est. |
|------|---------------|---------|--------------|
| W1 | pr-1 | None | 1-2 days |
| W2 | pr-2 + pr-5 | pr-1 | 5-7d (A) + 2-3w (B) |
| W3 | pr-3 + pr-6 + pr-10 | pr-2 + pr-5 + pr-5 | 4-6d + 3-4w + 2-3w |
| W4 | pr-4 + pr-7 | pr-3 + pr-6 | 4-6d + 2-3w |
| W5 | pr-8 | pr-4 + pr-7 + pr-3 | 2-3w |
| W6 | pr-9 | pr-8 | 1-2w |

**Max parallelism:** 3 concurrent PRs during Waves W2-W3.
**Total calendar time (2 devs):** ~8-10 weeks.
**Total calendar time (3 devs, overlapping):** ~6-8 weeks.

## Key Decisions

1. **Stream A and B are independent** — they can be developed in parallel by different developers.
2. **Phase 11 (Hybrid Search)** needs both streams complete (Phase 5 cache + Phase 10 process tracing).
3. **All MCP tool signatures unchanged** — additive only. Existing `_bfs()`/`_dfs()` preserved.
4. **graph.json format extended** — typed nodes/edges additive, generic nodes preserved for non-code files.
5. **Each PR is self-contained** with its own prompt that can be pasted into a fresh agent session.

## How to Use

1. **Read** `spec.md` for the technical specification.
2. **Check** the PR prompt in `pr-prompts/` for the phase you want to implement.
3. **Paste** the prompt into an AI coding agent.
4. **Run** `pytest tests/ -q` after each PR to verify nothing broke.
5. **Run** the progressive benchmark after each Stream A PR (see below).
6. **Commit** using the exact commit message in the PR prompt.
7. **Review** using the Code Review Checklist at the end of each PR doc before merging.

## Progressive Benchmarking

Each Stream A PR appends to `graphify-out/progressive.json`, building a per-phase attribution chain showing which features delivered which improvements. Stream B PRs add feature-specific benchmarks to `graphify/benchmark.py` for call resolution, process tracing, search quality, and multi-repo scale.

### Scale Tiers

| Tier | Nodes | Flag | Est. Memory | Use |
|------|-------|------|-------------|-----|
| small | 50K | default | ~50 MB | CI / quick check |
| medium | 100K | default | ~100 MB | CI |
| large | 500K | default | ~500 MB | Dev machine |
| xlarge | 1M | default | ~1 GB | Dev machine |
| huge | 5M | `--scale huge` | ~5 GB | Nightly / dedicated box |

### Attribution Chain

After each Stream A PR, run:
```bash
graphify benchmark --seed 42 --compare graphify-out/benchmark.json --output graphify-out/benchmark.json
```

This produces `graphify-out/progressive.json`:

```json
[
  {"phase": "1-baseline",     "qps_50k": 80,   "p95_ms_50k": 45.8},
  {"phase": "2-indexing",     "qps_50k": 950,  "p95_ms_50k": 3.2,  "delta_qps": "+1087%"},
  {"phase": "3-query-planning","qps_50k": 1800, "p95_ms_50k": 1.8,  "delta_qps": "+89%"},
  {"phase": "4-approximate",  "qps_50k": 4200, "p95_ms_50k": 0.4,  "delta_qps": "+133%"}
]
```

### Final Report (after PR 4)

```bash
graphify benchmark --seed 42 --scale huge --output graphify-out/benchmark_final.json
python -c "from graphify.benchmark import generate_progressive_report; generate_progressive_report()"
cat graphify-out/PROGRESSIVE.md
```

`PROGRESSIVE.md` contains:
- Per-phase metrics table at every scale tier
- "Top Gains" section attributing each improvement to a specific feature
- Speed-vs-accuracy tradeoff curve for approximate methods

### Stream B Feature Benchmarks

Stream B PRs add targeted benchmarks to `graphify/benchmark.py`:

| PR | Benchmark | Measures |
|----|-----------|----------|
| pr-5 | Schema coverage validation | % nodes with non-UNKNOWN type, % edges mapped to known EdgeType |
| pr-6 | `benchmark_call_resolution(G)` | Resolution throughput (calls/sec), coverage % at 50K-1M node scales |
| pr-7 | `benchmark_process_tracing(G)` | Trace throughput, average depth, change impact analysis speed |
| pr-8 | `benchmark_search_latency(G)` | BM25 vs semantic vs hybrid latency, RRF fusion overlap improvement |
| pr-9 | Skill completeness validation | Generated skills >50 lines, have sections, zero placeholders |
| pr-10 | `benchmark_cross_repo_query(pool)` | Pool eviction overhead, cross-repo query latency, scaling at 2/5/10/20 repos |

These run independently — no progressive.json accumulation for Stream B (features are additive, not competing).

## Compatibility Rules (all phases)

- All existing MCP tool signatures remain unchanged
- `graph.json` format extended additively (indexes stored as `G.graph` metadata)
- Existing `serve.py` `_bfs()` / `_dfs()` functions preserved
- `build_from_json()` gets optional new parameters, defaults backward-compatible
- New files packaged under `graphify/`, no breaking changes to imports
- Python 3.10+ support maintained throughout
