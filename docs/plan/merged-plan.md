# Graphify Fork + Code Intelligence — Merged Plan

**Status:** Proposed
**Date:** 2026-04-30

## Source Documents

- [Graphify Code Intelligence Gap](./graphify-code-intelligence-gap.md) — Phases 8-13
- [Graphify Fork Optimization](./graphify-fork-optimization.md) — Phases 1-7

## Critical Finding: Plans Are Interdependent

The original docs describe Phases 1-7 and 8-13 as "independent work streams with no shared dependencies." This is incorrect. Key cross-plan synergies:

| Synergy | Why |
|---|---|
| **P2 Indexing + P8 Code Schema** | Typed edge indexes (CALLS, IMPLEMENTS, etc.) are 10x more useful than indexing generic "calls"/"implements" edges |
| **P3 Bidirectional BFS + P9 Call Resolution** | Bidir BFS on typed CALLS edges enables precise "blast radius" queries in one hop |
| **P6 Approximate + P11 Hybrid Search** | Both propose embeddings; P6 (node2vec = structural) and P11 (text = semantic) are complementary but should share infrastructure |
| **P5 Caching + P12 Agent Integration** | Agent hooks need to know cache staleness; query cache feeds into PreToolUse enrichment |

**Decision:** Do NOT run these as two independent tracks. Interleave them with merged PRs.

## Dependency Graph

```
PR 1.1 (Fork+Baseline+Fixtures)
 ├── PR 1.2 (Code Schema + Typed Indexing) ────────────────┐
 │    ├── PR 1.3 (Advanced Traversal) ─────────────────────┤
 │    ├── PR 2.1 (Call Resolution) ────────────────────────┤
 │    │    ├── PR 2.2 (Process Tracing) ───────────────────┤
 │    │    └── PR 2.3 (Hybrid Search) ────────────────────┤
 │    │         └── PR 3.1 (Caching + Agent Integration) ──┤
 │    └── PR 3.2 (Multi-Repo Groups) ─────────────────────┘
 └── PR 3.3 (Final Benchmark) ─── runs after all PRs
```

## Epoch 1: Foundation — Weeks 1-4

### PR 1.1 — Fork + Baseline + Test Fixtures *(0.5 weeks)*

**Impact: Prerequisite**

Fork `safishamsi/graphify`, set up CI, add BSBM-synthetic benchmarks (50k-500k node graphs), record baseline numbers for all current MCP tool calls. Add language-specific fixture repos (TypeScript, Python, Go, Java, each ~500 symbols) that exercise call resolution, import chains, and inheritance.

### PR 1.2 — Code Schema + Typed Indexing *(2-3 weeks)*

**Impact: Foundation for all code intelligence**

Merge P8 (Code Schema) with P2 (Indexing). Build typed edge indexes alongside the schema.

New files:
- `graphify/code_schema.py` — 44 node types, 21 edge types, source location on all nodes
- `graphify/code_emitter.py` — Confidence-tiered edge emission (1.0 EXTRACTED, 0.5-0.9 INFERRED)
- `graphify/index.py` — Edge-type indexes, confidence bitmaps, node label trie

Modified files:
- `graphify/extract/__init__.py` — Enhanced `extract()` returns typed nodes/edges from tree-sitter AST
- `graphify/build.py` — `build_from_json()` accepts typed schema, calls `build_indexes(G)`

### PR 1.3 — Advanced Traversal *(1 week)*

**Impact: High — massive query speedup**

Merge P3 (Bidirectional BFS, Dijkstra, A*) with P4 (Query Planning). Cardinality estimation is cheap with typed indexes from PR 1.2.

Modified: `serve.py`
- `_bidirectional_shortest_path(G, src, tgt, max_hops, edge_types)`
- `_weighted_dijkstra(G, src, tgt, weight_field="confidence")`
- `_astar(G, src, tgt, heuristic=community_aware_heuristic)`
- `_select_best_start_node(candidates)` — lowest-degree node
- `_prefer_extracted_edges(frontier)` — confidence-tier sort

## Epoch 2: Core Intelligence — Weeks 5-12

### PR 2.1 — Call Resolution Engine *(3-4 weeks)*

**Impact: CRITICAL — enables "what calls what?"**

New files:
- `graphify/imports.py` — 4 import resolution strategies per language
- `graphify/call_extractors/` — `{ts,py,go,java}/call_extractor.py`
- `graphify/receiver.py` — self/this resolution, constructor inference
- `graphify/mro.py` — C3 linearization, first_wins, ruby_mixin
- `graphify/cross_file.py` — SCC-ordered cross-file type propagation
- `graphify/call_dag.py` — 6-stage call resolution DAG

New MCP tools:
- `context({name: "X"})` — 360° symbol view
- `impact({target: "X", direction: "upstream", minConfidence: 0.8})` — blast radius

### PR 2.2 — Process Tracing *(2-3 weeks)*

**Impact: CRITICAL — feeds Battle Testing + Compliance Validator**

New files:
- `graphify/processes.py` — Entry point detection (plugin-based), process tracing
- `graphify/process_cluster.py` — Deduplicate overlapping traces

New MCP tools:
- `detect_changes({scope: "all"})` — git diff → affected symbols/processes with risk level
- `trace({entry_point: "X"})` — full process trace with step-by-step call chain

New output: `graphify-out/processes.json`

### PR 2.3 — Hybrid Search *(2-3 weeks)*

**Impact: High**

Merge P11 (Hybrid Search) with relevant parts of P6 (Approximate Methods).

New files:
- `graphify/search/__init__.py` — orchestrator
- `graphify/search/bm25.py` — BM25 on symbol names, paths, docstrings
- `graphify/search/embeddings.py` — Text embeddings (384D), incremental SHA1 update
- `graphify/search/fusion.py` — Reciprocal Rank Fusion (K=60)
- `graphify/search/grouping.py` — Process-grouped results

Modified: `serve.py` — default `query_graph` mode becomes `"hybrid"`

P6's node2vec/PyKEEN deferred to `graphify/search/structural/` as future optional add-on.

## Epoch 3: Integration & Scale — Weeks 13-17

### PR 3.1 — Caching + Agent Integration *(2 weeks)*

**Impact: High for agent UX**

Merge P5 (Caching) with P12 (Agent Integration).

New files:
- `graphify/query_cache.py` — SHA256(query) → cached results, TTL-based
- `graphify/skills/` — exploring.py, debugging.py, impact.py, refactoring.py
- `graphify/skills/repo_skills.py` — Per-community SKILL.md generation
- `graphify/skills/hooks.py` — PreToolUse + PostToolUse scripts

Cache invalidation driven by PostToolUse hook (targeted eviction, not full flush).

### PR 3.2 — Multi-Repo Groups *(2-3 weeks)*

**Impact: Medium (Enterprise)**

New files:
- `graphify/registry.py` — `~/.graphify/registry.json`
- `graphify/lazy_pool.py` — Lazy connection pool (5 concurrent, 5-min TTL)
- `graphify/groups.py` — Create/sync/query repository groups
- `graphify/contract_bridge.py` — Cross-repo dependency mapping

### PR 3.3 — Final Benchmark + Upstream PR *(0.5 weeks)*

Run BSBM + code intelligence metrics on final fork vs upstream. Publish results. PR to upstream if significant wins.

## Priority Matrix

| PR | Weeks | Impact | Depends On | Enables |
|---|---|---|---|---|
| **1.1** Fork + Baseline + Fixtures | 0.5 | Prereq | — | Everything |
| **1.2** Code Schema + Typed Indexing | 2-3 | Foundation | 1.1 | All code phases + fast traversal |
| **1.3** Advanced Traversal | 1 | High | 1.2 | Fast process tracing (2.2) |
| **2.1** Call Resolution | 3-4 | **CRITICAL** | 1.2 | Self-Healing, Battle Testing, Context Layer |
| **2.2** Process Tracing | 2-3 | **CRITICAL** | 2.1, 1.3 | Compliance Validator, Battle Testing L5 |
| **2.3** Hybrid Search | 2-3 | High | 1.2 | Context Layer relevance |
| **3.1** Caching + Agent Integration | 2 | High | 2.1, 2.3 | Multi-Harness + Skill Generator |
| **3.2** Multi-Repo Groups | 2-3 | Medium | 1.2 | Enterprise customers |
| **3.3** Final Benchmark | 0.5 | Validation | All | Upstream PR |

**Total: 14-17 weeks** (down from original 19-28 weeks by merging overlapping phases)

## Improvements Over Originals

1. **Cross-plan phase merging** — P2 merged into P1.2 (typed indexing); P4 merged into P1.3 (traversal); P6 merged into P2.3 (hybrid search); P5 merged with P3.1 (caching+agents). Eliminates redundant work.

2. **Plugin architecture for language support** — Call extractors (PR 2.1) and entry point detectors (PR 2.2) use registry pattern. Adding a 5th language or 3rd framework doesn't modify core code.

3. **Test fixture suite built early** — PR 1.1 creates language-specific fixtures that serve as validation harness for PR 2.1 call resolution accuracy and PR 3.3 final comparison.

4. **Validation gates between epochs** — Each epoch ends with measurable success criteria before entering next epoch.

5. **Clean embedding separation** — Text embeddings (`search/text/`) and structural embeddings (`search/structural/`) separated with shared RRF fusion. P6's node2vec deferred.

6. **Targeted cache invalidation** — PostToolUse hooks trigger targeted eviction, not full cache flush.

7. **Versioned skill generation** — Agent skills generated to `skills/v2/` namespace, allowing safe updates.

## Risks & Mitigations

| Risk | Probability | Mitigation |
|---|---|---|
| Call resolution accuracy below 95% parity | Medium | Start with TypeScript only, add languages incrementally |
| Index memory overhead on large repos | Medium | Bitmap indexes compact; fallback lazy loading for >500k nodes |
| Upstream rejects PRs | Low | Keep fork as primary; schema extensions are additive |
| Embedding model size bloats deployment | Medium | sentence-transformers as optional `[embeddings]` extra; BM25-only fallback |

## Requirements Per PR

- **Test coverage:** 90%+ per PR (both unit and integration)
- **Git commits:** Each PR = one merge commit (squash allowed for fixups)
- **Benchmark record:** Run BSBM + code intelligence benchmarks after each PR, record results in `docs/plan/progress.md`
- **Incremental validation:** Each PR's benchmark diff shows exact gains/regressions vs previous PR

## Recommended Initial Scope

Epochs 1-2 (PRs 1.1 through 2.2, ~10 weeks) deliver the critical capability: agents can answer "what calls what" and "what breaks if I change this" with fast traversals. This directly enables Orquestra's Reliability, Battle Testing, and Self-Healing.

Stop and validate there before committing to Epoch 3.

## Related

- [Original Code Intelligence Gap Plan](../plans/graphify-code-intelligence-gap.md)
- [Original Fork Optimization Plan](../plans/graphify-fork-optimization.md)
- Graphify upstream: <https://github.com/safishamsi/graphify>
- GitNexus (reference): <https://github.com/abhigyanpatwari/GitNexus>
