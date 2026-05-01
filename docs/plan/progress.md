# Graphify Epoch 4 — Performance & Correctness

> **Last updated:** TBD
> **Started:** 2026-05-01
> **Target completion:** 1 week

## Overview

Epoch 4 fixes the 5 root causes discovered in the VSCode SweBench audit.

| PR | Name | Status | Impact |
|---|---|---|---|
| 4.1 | Compact & Fast Serialization | ⬜ Pending | **CRITICAL** — 8x load speed |
| 4.2 | Ranked Node Lookup | ⬜ Pending | **CRITICAL** — correct explain/path |
| 4.3 | Graph-Based Entry Points | ⬜ Pending | **CRITICAL** — fix processes list |
| 4.4 | CLI Query via Hybrid Search | ⬜ Pending | HIGH — query quality |
| 4.5 | Index Persistence + Coverage Remediation | ⬜ Pending | HIGH — speed + 63%→85% coverage |
| 4.6 | VSCode SweBench Re-Run | ⬜ Pending | VALIDATION |

**Legend:** ⬜ Pending | 🟦 In Progress | 🟩 Complete | 🟥 Blocked

---

## VSCode SweBench — Before & After Targets

| Metric | Before (Epoch 3) | After (Epoch 4 target) |
|---|---|---|
| **Query** p50 | 1488ms | <200ms |
| **Query** p95 | 1864ms | <300ms |
| **Path** p50 | 1470ms | <200ms |
| **Path** p95 | 1597ms | <300ms |
| **Explain** p50 | 1390ms | <200ms |
| **Explain** p95 | 1517ms | <300ms |
| **Processes list** | 0 results (empty) | ≥5 processes |
| **Query diversity** | same output 15/15 | ≥5 distinct communities |
| **Explain accuracy** | 4/10 wrong node | 0/10 wrong |
| **graph.json size** | 164 MB | <80 MB |

---

## Root Cause → Solution Map

| # | Root Cause | PR | Solution |
|---|---|---|---|
| RC1 | 164MB JSON parsed per subprocess | **4.1** | Compact serialization + shared fast loader |
| RC2 | `processes list` needs extractions (gone post-build) | **4.3** | Graph-based entry point detection |
| RC3 | CLI query uses O(N) keyword scan, not BM25 | **4.4** | Wire CLI query to SearchOrchestrator |
| RC4 | `_find_node` first substring match, no ranking | **4.2** | Ranked lookup: exact→short path→degree |
| RC5 | `json.dump(indent=2)`, `_src`/`_tgt` redundancy | **4.1** | `separators=(',',':')`, strip redundant fields |

---

## Validation Gates (Epoch 4)

| Check | Status | Target |
|---|---|---|
| All PRs: new/changed module coverage ≥90% | ⬜ | Verified per PR |
| Full test suite: 900+ pass | ⬜ | `python -m pytest tests/` |
| VSCode SweBench rerun p50 <250ms all ops | ⬜ | `benchmarks/vscode-bench.py` |
| Processes list returns ≥5 results on VSCode | ⬜ | Manual + benchmark |
| Explain returns correct node for uri.ts, event.ts, lifecycle.ts | ⬜ | Manual + benchmark |

---

## PR Status Log

### PR 4.1 — Compact & Fast Serialization

| Field | Value |
|---|---|
| **Status:** | ⬜ Pending |
| **Started:** | — |
| **Completed:** | — |
| **Coverage:** | — |
| **Notes:** | `separators=(',',':')`, orjson optional, shared `_load_graph_file()` across all CLI + serve + build paths |

### PR 4.2 — Ranked Node Lookup

| Field | Value |
|---|---|
| **Status:** | ⬜ Pending |
| **Started:** | — |
| **Completed:** | — |
| **Coverage:** | — |
| **Notes:** | Exact match → path depth → degree scoring. Fixes explain + path CLI |

### PR 4.3 — Graph-Based Entry Points

| Field | Value |
|---|---|
| **Status:** | ⬜ Pending |
| **Started:** | — |
| **Completed:** | — |
| **Coverage:** | — |
| **Notes:** | `GraphEntryPointDetector` from node attributes. Fixes `processes list` |

### PR 4.4 — CLI Query via Hybrid Search

| Field | Value |
|---|---|
| **Status:** | ⬜ Pending |
| **Started:** | — |
| **Completed:** | — |
| **Coverage:** | — |
| **Notes:** | Replaces naive scoring with BM25 from `graphify/search/`. Graceful fallback |

### PR 4.5 — Index Persistence + Coverage Remediation

| Field | Value |
|---|---|
| **Status:** | ⬜ Pending |
| **Started:** | — |
| **Completed:** | — |
| **Coverage:** | — |
| **Notes:** | Save/load indexes. Tests for index.py (0%→95%), code_emitter.py (0%→95%), serve.py (17%→60%+) |

### PR 4.6 — VSCode SweBench Re-Run

| Field | Value |
|---|---|
| **Status:** | ⬜ Pending |
| **Started:** | — |
| **Completed:** | — |
| **Coverage:** | — |
| **Notes:** | Re-run benchmark, record baselines, final validation |

---

## Blockers & Risks

| Date | Risk | Severity | Mitigation | Resolved |
|---|---|---|---|---|
| 2026-05-01 | orjson may not install on all platforms | Low | Optional dependency, stdlib JSON fallback | No |

---

## How to Use This Tracker

1. **Start a PR:** Change status to 🟦, fill started date
2. **Complete a PR:** Change status to 🟩, fill completed date, coverage %
3. **Run benchmarks:** After PR 4.6, run `python benchmarks/vscode-bench.py`, paste results
4. **Pass validation gate:** Before declaring Epoch 4 done, check all gate items
