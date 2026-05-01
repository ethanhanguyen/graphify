# Graphify — Knowledge Graph for Codebases

Fork of [graphify](https://github.com/safishamsi/graphify) adding call resolution, process tracing, hybrid search, multi-repo support, query caching, and a comprehensive validation framework with apple-to-apple comparison against upstream.

## What this fork adds

Three epochs of features on top of upstream graphify, plus a unified 3-primitive CLI that bakes advanced analysis into simple commands:

```
query "X"          → BM25 search + optional --risk / --trace
explain "X"        → categorized neighbors (incoming/outgoing calls, imports)
path "A" "B"       → shortest path + complexity/branch-point metrics
```

Every command works standalone from any terminal. No AI assistant, no MCP server needed.

## Quick example

```bash
# Build a graph (same as upstream)
graphify update https://github.com/microsoft/vscode
```

```bash
# explain shows call direction automatically
$ graphify explain "uri.ts" --graph graphify-out/graph.json

Node: uri.ts
  Source:    src/vs/base/common/uri.ts L1
  Degree:    1998

  Incoming calls (42 callers →):
    ← lifecycle.ts [EXTRACTED] src/vs/base/common/lifecycle.ts:584
    ← event.ts [EXTRACTED] src/vs/base/common/event.ts:221
    ...

  Outgoing calls (→ 18 callees):
    → .import() [INFERRED]
    → fromNow() [INFERRED]

  Imports (5):
    resources.ts [imports_from]
    errors.ts [imports_from]
```

```bash
# query with impact analysis
$ graphify query "how does lifecycle.ts work" --risk

NODE lifecycle.ts [src=src/vs/base/common/lifecycle.ts ...]
NODE .work() [src=src/vs/base/common/async.ts ...]
...

  ══ Impact: .work() (code)
  Affected: 4453 nodes  |  Risk: CRITICAL
  Upstream (depends on this):
    L1: .schedule(), .isScheduled()
    L2: .cancel(), .flush(), .scheduleThrottler()
    L3: getLanguageModelCache(), invokeRunInTerminal(), ...
  Downstream (this depends on):
    L1: .schedule(), .isScheduled()
```

```bash
# query with process trace
$ graphify query "how does lifecycle.ts work" --trace

  ══ Trace: .work()
  Steps: 1000  |  Depth: 5  |  Complexity: 743
  External touches: 643
  Chain:
    [ 0] .work()  src/vs/base/common/async.ts:1257
    [ 1] .schedule()  src/vs/base/common/async.ts:1219
    [ 1] .isScheduled()  src/vs/base/common/async.ts:1231
    [ 2] .cancel()  src/vs/base/common/async.ts:2546
    [ 2] .flush()  src/vs/base/common/async.ts:1157
```

```bash
# path with complexity metrics
$ graphify path "lifecycle.ts" "async.ts"

Shortest path (3 hops):
  lifecycle.ts --imports_from [EXTRACTED]--> async.ts

  2 files  |  1 branch points  |  EXTRACTED: 2  INFERRED: 1
```

## Feature epochs

### Epoch 1 — Foundation

Validation infrastructure, code schema, typed indexing, and advanced pathfinding.

| Feature | Detail |
|---------|--------|
| **CI validation** | `ci-check.sh` — L1 (pytest), L2 (fixture graph build), L3 (snapshot regression). Runs on every PR via `.github/workflows/validate.yml`. |
| **4-language fixture suite** | `tests/fixtures/{python,typescript,go,java}/` — 3 files each with inheritance, imports, cross-file calls. Provides deterministic ground truth for every build change. |
| **Code schema** | `code_schema.py` — 44 node types, 21 edge types, 3 confidence tiers (EXTRACTED/INFERRED/AMBIGUOUS). Schema version 2. |
| **Typed indexing** | `index.py` — EdgeTypeIndex (O(1) type lookup), NodeLabelTrie (prefix search), ConfidenceBitmap (tier filtering), CompositeIndex. Indexes are persisted to `<graph>.index.json` and auto-reloaded. |
| **Advanced pathfinding** | `serve.py` — Bidirectional BFS (O(b^(d/2))), Dijkstra (confidence-weighted), A* (community-aware heuristic). Edge-type filtering. Selects lowest-degree start node for optimal traversal. |
| **Benchmark runner** | `benchmarks/runner.py` — Structured JSON per PR. Cumulative table in README via `scripts/update-readme-table.py`. |

### Epoch 2 — Core Intelligence

Call resolution, process tracing, and hybrid search.

| Feature | Detail |
|---------|--------|
| **Call resolution** | `call_dag.py` — 6-stage pipeline (Extract → Classify → InferReceiver → SelectDispatch → ResolveTarget → EmitEdge). Per-language call extractors for TypeScript, Python, Go, Java. Cross-file type propagation with Tarjan SCC ordering. |
| **Process tracing** | `processes.py` — BFS along CALLS edges from entry points. Computes cyclomatic complexity, external file touches, and depth. Trace all entry points or trace changed nodes after git diff. |
| **Change detection** | `change_detect.py` — Git diff → affected symbols → affected processes → risk assessment (CRITICAL/HIGH/MEDIUM/LOW) with recommendations. |
| **Entry point detection** | `entry_points.py` — Graph-based fallback (high out-degree + no incoming CALLS = entry point). Framework-specific detectors for Next.js, Express, Flask, FastAPI, CLI, Go main, tests, cron. |
| **Hybrid search** | `search/` — Parallel BM25 + semantic vector search → Reciprocal Rank Fusion (k=60). Embedding index with SHA1 staleness detection, sharded storage. Falls back to BM25-only when sentence-transformers unavailable. |
| **BM25 engine** | `search/bm25.py` — Keyword search on node labels, file paths, and content with incremental updates. Replaces upstream's O(N) keyword substring + shallow BFS. |

### Epoch 3 — Caching + Multi-Repo

Query result caching with content-hash invalidation and cross-repo graph support.

| Feature | Detail |
|---------|--------|
| **Query cache** | `query_cache.py` — LRU cache (256 entries). Content-hash invalidation: file changes only evict affected cache entries. Hit rate >80% after 10 repeated queries. Integrated with `query_graph` MCP tool. |
| **Agent hooks** | `agent_hooks.py` — PreToolUse enriches searches with graph context. PostToolUse detects file changes, invalidates cache, prompts reindex. |
| **Multi-repo registry** | `multirepo.py` — Register/unregister repos, create/delete groups, sync graphs, group-aware path resolution. |
| **Cross-repo contracts** | `contract_bridge.py` — Identifies shared interfaces (function signatures, class names) across repo boundaries. Generates bridge reports with confidence scoring. |
| **Group-aware search** | `group_search.py` — RRF fan-out across repos, merges ranked results from multiple repositories into unified ranking. |

### Epoch 4 — Performance & Correctness

Compact serialization, ranked node lookup, and unified 3-primitive CLI.

| Feature | Detail |
|---------|--------|
| **Compact JSON** | `export.py` — `separators=(',',':')`, no indent. Strips redundant `_src`/`_tgt` from edges (recomputed on load). **36% smaller** graph files (164→105 MB on VSCode 111K-node graph). |
| **Ranked node lookup** | `serve.py` — `_find_node()` scores by exact match (+100), filename (+50), path depth (+30), core module (+15), degree (+15). Resolves ambiguous names (e.g. 3 `uri.ts` → picks `src/vs/` over `extensions/`). |
| **Unified 3-primitive CLI** | `__main__.py` — `explain` shows categorized neighbor view (incoming/outgoing calls, imports, process membership) without separate tools. `query --risk` bakes in impact analysis. `query --trace` bakes in process tracing. `path` shows branch points and file count. |
| **Index persistence** | `index.py` — CompositeIndex serialized to `<graph>.index.json`. Popped from `G.graph` before JSON serialize to avoid TypeError. Auto-loaded on graph load. |
| **Test coverage** | 1019 tests pass (was 917 upstream). Key modules at 96-100% coverage. 24 index round-trip tests, 21 code_emitter tests, 23 serialization tests, 8 graph-based entry_point tests. |

## Before/After Demo (toy-service)

A 5-file Python FastAPI microservice at `demos/toy-service/`. Build it with
both upstream and fork to see the enrichment delta in action.

Full walkthrough at [demos/GRAPHIFY_FEATURES.md](demos/GRAPHIFY_FEATURES.md).

### explain "get_user()" — cross-file calls

| | Upstream (graphifyy) | Fork (this repo) |
|---|---|---|
| Output | Flat "Connections" list, 3 edges | Categorized calls, **5 edges** |
| Cross-file calls | None resolved | `.find_by_id()` → models.py, `.to_dict()` → models.py |
| Call direction | Not shown | "Outgoing calls (→ 4 callees)" |

### graph.json

| | Upstream | Fork | Delta |
|---|---|---|---|
| Nodes | 37 | 37 | 0 |
| Edges | 57 | **61** | **+4 cross-file calls** |
| Size | 29.4 KB | **20.1 KB** | **-32%** |
| Call resolution | — | 28/76 (37%) | — |
| Entry points detected | — | 1 (server.py) | — |

```bash
# Reproduce yourself
pip install graphifyy                        # baseline
graphify update demos/toy-service             # baseline build
pip install -e .                              # fork
graphify update demos/toy-service             # fork build
graphify explain "get_user()"                 # compare
```

## Comparison: fork vs upstream on VSCode

Full apple-to-apple validation against upstream PyPI `graphifyy==0.5.7` on Microsoft VSCode (9,936 files):

| Metric | Upstream (0.5.7) | Fork (0.5.6 + epochs) | Delta |
|--------|-----------------|----------------------|-------|
| Nodes | 111,799 | 111,799 | 0% |
| Edges | 249,966 | 249,966 | 0% |
| **Graph size** | 164 MB | **105 MB** | **-36%** |
| Bytes per node | 1,539 | 987 | -36% |
| **Query BFS p50** | 46.2ms | **42.1ms** | **-9%** |
| Path p50 | 54.9ms | 56.5ms | +3% |
| Explain p50 | 27.1ms | 27.9ms | +3% |
| Communities | 2,627 | 2,719 | +3.5% |
| Build time | 89s | 79s | -11% |
| CLI errors | 0 | 0 | — |
| **Explain Jaccard** | — | **1.00** | All neighbors identical |
| **Query Jaccard** | — | **0.10** | BM25 ≠ keyword BFS |

Graph topology is identical (same tree-sitter extraction pipeline). Key difference: **36% smaller files**, **9% faster queries**, and **BM25 search replaces naive keyword scoring** for more relevant query results.

## Validation framework

Reproducible baseline-vs-fork comparison on any corpus.

```bash
# Full validation: clone corpus, build both graphs, run queries, compare, assess
./validation/run.sh

# Custom corpus
./validation/run.sh --corpus https://github.com/torvalds/linux

# Local repo
./validation/run.sh --corpus ~/my-project

# Skip setup (venvs already built)
./validation/run.sh --skip-setup

# Skip build (graphs already built)
./validation/run.sh --skip-build

# Tag a run for tracking
./validation/run.sh --tag "added-compact-json"

# Compare against previous run
./validation/run.sh --compare-against runs/2026-04-30-120000

# Clean venvs and corpus
./validation/run.sh --clean
```

**What it does:**

1. Clones corpus (default: `microsoft/vscode` to `/tmp/graphify-validation/`)
2. Creates isolated venvs: baseline (`pip install graphifyy`) and current (`pip install -e .`)
3. Builds both graphs with `graphify update`
4. Runs `query`, `path`, `explain` CLI commands on auto-discovered common labels
5. Runs internal NetworkX benchmarks (BFS, shortest path, node lookup)
6. Generates `COMPARISON.md` — human-readable apple-to-apple report
7. Generates `metrics.json` — machine-readable for CI gating
8. Generates `ASSESSMENT.md` — progress/regression verdicts with recommendations

**Output per run:**

```
validation/runs/2026-05-01-101533/
├── out-baseline/           # graph.json + GRAPH_REPORT.md + build.log
├── out-current/            # graph.json + GRAPH_REPORT.md + build.log
├── query_results.json      # CLI outputs + benchmark timings
├── COMPARISON.md           # structure, performance, quality, correctness
├── metrics.json            # CI-gatable metrics
├── ASSESSMENT.md           # PASS/WARN/FAIL verdicts + recommendations
└── latest → 2026-05-01-101533 (symlink)
```

## Install

```bash
pip install -e ".[all]"
```

Requires Python 3.10+. This is a local development fork — not published to PyPI.

## Running tests

```bash
python -m pytest tests/ -q --tb=short --timeout=30
# 1019 tests pass
```

## Upstream

This is a fork of [safishamsi/graphify](https://github.com/safishamsi/graphify). The upstream package is `graphifyy` on PyPI. All credit for the tree-sitter extraction pipeline, Leiden clustering, MCP server, and multimodal support goes to the upstream authors.
