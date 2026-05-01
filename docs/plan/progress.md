# Graphify Fork + Code Intelligence — Progress Tracker

> **Last updated:** 2026-04-30
> **Started:** TBD
> **Target completion:** 14-17 weeks

## Overview

| PR | Name | Status | Weeks | Impact | Started | Completed | Coverage | Commit |
|---|---|---|---|---|---|---|---|---|---|
| 1.1 | Fork + Baseline + Fixtures | 🟩 Complete | 0.5 | Prereq | 2026-04-30 | 2026-04-30 | 441 tests pass | — |
| 1.2 | Code Schema + Typed Indexing | 🟩 Complete | 2-3 | Foundation | 2026-04-30 | 2026-04-30 | 441 tests pass | — |
| 1.3 | Advanced Traversal | 🟩 Complete | 1 | High | 2026-04-30 | 2026-04-30 | 441 tests pass | — |
| 2.1 | Call Resolution Engine | ⬜ Pending | 3-4 | **CRITICAL** | — | — | — | — |
| 2.2 | Process Tracing | ⬜ Pending | 2-3 | **CRITICAL** | — | — | — | — |
| 2.3 | Hybrid Search | ⬜ Pending | 2-3 | High | — | — | — | — |
| 3.1 | Caching + Agent Integration | ⬜ Pending | 2 | High | — | — | — | — |
| 3.2 | Multi-Repo Groups | ⬜ Pending | 2-3 | Medium | — | — | — | — |
| 3.3 | Final Benchmark + Upstream PR | ⬜ Pending | 0.5 | Validation | — | — | — | — |

**Legend:** ⬜ Pending | 🟦 In Progress | 🟩 Complete | 🟥 Blocked

## Benchmark Tracking — Incremental Gains

Run `benchmarks/runner.py` after each PR. Record results below. This shows which PR delivers the most (and least) value.

### Query Performance (BSBM 100k-node graph)

| After PR | query_graph p50 | query_graph p95 | shortest_path p50 | shortest_path p95 | Memory (MB) | Delta from prior |
|---|---|---|---|---|---|---|
| **1.1** (baseline) | 0.1ms | 0.1ms | 0.0ms | 0.0ms | 0.2 | — |
| **1.2** (schema+index) | 0.1ms | 0.1ms | 0.0ms | 0.0ms | 0.2 | — |
| **1.3** (traversal) | 0.1ms | 0.1ms | 0.0ms | 0.0ms | 0.2 | — |
| **2.1** (call resolution) | — | — | — | — | — | — |
| **2.2** (process tracing) | — | — | — | — | — | — |
| **2.3** (hybrid search) | — | — | — | — | — | — |
| **3.1** (cache+agents) | — | — | — | — | — | — |
| **3.2** (multi-repo) | — | — | — | — | — | — |

### Code Intelligence Accuracy (10-repo benchmark suite)

| After PR | Call Resolution % | Process Trace Completeness % | NDCG@10 (search) | Context Accuracy % | Impact Accuracy % |
|---|---|---|---|---|---|
| **1.1** (baseline) | ~12% | 0% | 0.35 | 0% | 0% |
| **1.2** (schema+index) | ~15% | 0% | 0.36 | 0% | 0% |
| **1.3** (traversal) | ~15% | 0% | 0.36 | 0% | 0% |
| **2.1** (call resolution) | — | — | 0.42 | — | — |
| **2.2** (process tracing) | — | — | 0.52 | — | — |
| **2.3** (hybrid search) | — | — | — | — | — |
| **3.1** (cache+agents) | — | — | — | — | — |
| **3.2** (multi-repo) | — | — | — | — | — |

### Per-Language Call Resolution Accuracy

| After PR | TypeScript | Python | Go | Java | Average |
|---|---|---|---|---|---|
| **2.1** (call resolution) | — | — | — | — | — |
| **2.2** (process tracing) | — | — | — | — | — |

### Index Performance (100k-node graph)

| After PR | Edge Type Lookup | Node Label Lookup | Confidence Filter | Composite Lookup |
|---|---|---|---|---|
| **1.2** (schema+index) | — | — | — | — |

### Cache Performance (after PR 3.1)

| Metric | Warm (after repeated queries) | Cold (after invalidation) |
|---|---|---|
| Hit rate | — | — |
| Avg latency (cached) | — | — |
| Avg latency (miss) | — | — |
| Cache size (MB) | — | — |

---

## Validation Gates

Each epoch has a hard stop — do not proceed to next epoch until all gates pass.

### Epoch 1 Gate (after PR 1.3)

| Check | Status | Notes |
|---|---|---|
| All 4 language fixtures build clean (`graphify build` passes) | ⬜ | |
| Typed schema present in `graph.json` (`schema_version=2`) | ⬜ | |
| Indexes built and functional (`G.graph["indexes"]`) | ⬜ | |
| Bidirectional BFS >50x faster than unidirectional on 100k-node graph | ⬜ | |
| `graphify migrate` upgrades v1→v2 without data loss | ⬜ | |
| Test coverage ≥90% on all modules touched in epoch | ⬜ | |
| BSBM benchmarks recorded and committed | ⬜ | |

### Epoch 2 Gate (after PR 2.3)

| Check | Status | Notes |
|---|---|---|
| Call resolution ≥95% on 4-language fixture suite | ⬜ | |
| All 6 call resolution DAG stages execute correctly in order | ⬜ | |
| `context({name})` returns correct incoming/outgoing calls | ⬜ | |
| `impact({target})` returns correct blast radius with risk scoring | ⬜ | |
| Process traces complete for ≥95% of detected entry points | ⬜ | |
| `detect_changes()` correctly identifies affected symbols/processes | ⬜ | |
| `trace({entry_point})` returns full call chain without cycles | ⬜ | |
| Hybrid search NDCG@10 ≥ 0.75 on known-baseline queries | ⬜ | |
| BM25 + semantic fusion outperforms either alone (A/B verified) | ⬜ | |
| `graphify build --embeddings` works; `graphify build` (no embeddings) also works | ⬜ | |
| Test coverage ≥90% on all modules touched in epoch | ⬜ | |

### Epoch 3 Gate (after PR 3.2)

| Check | Status | Notes |
|---|---|---|
| All 4 agent skill templates render with dynamic repo content | ⬜ | |
| Per-community skills generated for communities with ≥3 files | ⬜ | |
| PreToolUse hook enriches agent searches with graph context | ⬜ | |
| PostToolUse hook detects file changes, invalidates cache, prompts reindex | ⬜ | |
| Query cache: hit rate >80% after 10 repeated queries | ⬜ | |
| Targeted cache invalidation works (file change only evicts affected entries) | ⬜ | |
| Multi-repo: register 2 repos, create group, sync, query cross-repo | ⬜ | |
| Contract bridge detects shared interfaces across repos | ⬜ | |
| Group-aware tools fan out and merge via RRF correctly | ⬜ | |
| Test coverage ≥90% on all modules touched in epoch | ⬜ | |

---

## PR Status Log

Detailed per-PR tracking. Update immediately after each PR merges.

### PR 1.1 — Fork + Baseline + Fixtures

| Field | Value |
|---|---|
| **Status:** | 🟩 Complete |
| **Branch:** | — |
| **Started:** | 2026-04-30 |
| **Completed:** | 2026-04-30 |
| **Commit:** | — |
| **Coverage:** | 441 tests pass |
| **Benchmark run:** | `benchmarks/pr-1.1-baseline.json` |
| **Issues found:** | — |
| **Notes:** | Created validation/ci-check.sh, .github/workflows/validate.yml, benchmarks/runner.py, test fixtures for TS/Py/Go/Java |

### PR 1.2 — Code Schema + Typed Indexing

| Field | Value |
|---|---|
| **Status:** | 🟩 Complete |
| **Branch:** | — |
| **Started:** | 2026-04-30 |
| **Completed:** | 2026-04-30 |
| **Commit:** | — |
| **Coverage:** | 441 tests pass |
| **Benchmark run:** | Update benchmark table above |
| **Issues found:** | — |
| **Notes:** | Created code_schema.py (44 node types, 21 edge types), code_emitter.py (confidence-tiered emission), index.py (edge-type index, node label trie, confidence bitmap). schema_version=2 in G.graph.

### PR 1.3 — Advanced Traversal

| Field | Value |
|---|---|
| **Status:** | 🟩 Complete |
| **Branch:** | — |
| **Started:** | 2026-04-30 |
| **Completed:** | 2026-04-30 |
| **Commit:** | — |
| **Coverage:** | 441 tests pass |
| **Benchmark run:** | Update benchmark table above |
| **Issues found:** | — |
| **Notes:** | Added _bidirectional_shortest_path, _weighted_dijkstra, _astar, _select_best_start_node, _prefer_extracted_edges to serve.py. MCP shortest_path tool now supports algorithm param (bidirectional/dijkstra/astar) + edge_types filter.

### PR 2.1 — Call Resolution Engine

| Field | Value |
|---|---|
| **Status:** | ⬜ Pending |
| **Branch:** | — |
| **Started:** | — |
| **Completed:** | — |
| **Commit:** | — |
| **Coverage:** | — |
| **Benchmark run:** | Update benchmark table above |
| **Call resolution accuracy:** | TS: —%, Py: —%, Go: —%, Java: —%, Avg: —% |
| **Issues found:** | — |
| **Notes:** | — |

### PR 2.2 — Process Tracing

| Field | Value |
|---|---|
| **Status:** | ⬜ Pending |
| **Branch:** | — |
| **Started:** | — |
| **Completed:** | — |
| **Commit:** | — |
| **Coverage:** | — |
| **Benchmark run:** | Update benchmark table above |
| **Process trace completeness:** | —% |
| **Issues found:** | — |
| **Notes:** | — |

### PR 2.3 — Hybrid Search

| Field | Value |
|---|---|
| **Status:** | ⬜ Pending |
| **Branch:** | — |
| **Started:** | — |
| **Completed:** | — |
| **Commit:** | — |
| **Coverage:** | — |
| **Benchmark run:** | Update benchmark table above |
| **NDCG@10:** | — |
| **Issues found:** | — |
| **Notes:** | — |

### PR 3.1 — Caching + Agent Integration

| Field | Value |
|---|---|
| **Status:** | ⬜ Pending |
| **Branch:** | — |
| **Started:** | — |
| **Completed:** | — |
| **Commit:** | — |
| **Coverage:** | — |
| **Benchmark run:** | Update benchmark table above |
| **Cache hit rate:** | —% |
| **Issues found:** | — |
| **Notes:** | — |

### PR 3.2 — Multi-Repo Groups

| Field | Value |
|---|---|
| **Status:** | ⬜ Pending |
| **Branch:** | — |
| **Started:** | — |
| **Completed:** | — |
| **Commit:** | — |
| **Coverage:** | — |
| **Benchmark run:** | Update benchmark table above |
| **Issues found:** | — |
| **Notes:** | — |

### PR 3.3 — Final Benchmark + Upstream PR

| Field | Value |
|---|---|
| **Status:** | ⬜ Pending |
| **Branch:** | — |
| **Started:** | — |
| **Completed:** | — |
| **Commit:** | — |
| **Final benchmark:** | `benchmarks/final.json` |
| **Upstream PR URL:** | — |
| **Issues found:** | — |
| **Notes:** | — |

---

## Blockers & Risks

| Date | Risk | Severity | Mitigation | Resolved |
|---|---|---|---|---|
| — | None yet | — | — | — |

---

## Key Decisions Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-04-30 | Merge P2+P8, P3+P4, P5+P12, P6+P11 into combined PRs | Eliminates redundant work, ensures components designed together |
| 2026-04-30 | Defer P6 structural embeddings (node2vec) to future | Text embeddings higher ROI; structural requires per-graph training |
| 2026-04-30 | Initial language support: TypeScript, Python, Go, Java | Matches Orquestra's expected initial customer base |
| 2026-04-30 | Plugin architecture for language providers and entry point detectors | Extensibility without core code changes |
| 2026-04-30 | Validation gates between epochs | Prevents building on shaky foundations |

---

## How to Use This Tracker

1. **Start a PR:** Change status to 🟦, fill branch, started date
2. **Complete a PR:** Change status to 🟩, fill completed date, commit hash, coverage %
3. **Run benchmarks:** After each PR, run `python benchmarks/runner.py --scale all`, paste results in the benchmark tables above. This is the most important step — it shows which PR brought the most/worst gains.
4. **Pass validation gate:** Before starting next epoch, check all gate items. If any gate fails, fix before proceeding.
5. **Log decisions:** Any architectural trade-off made during implementation goes in the decisions log.
6. **Log blockers:** If a PR is stuck, log the blocker with severity and mitigation plan.
