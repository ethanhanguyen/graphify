# Graphify Validation Suite

Apples-to-apples comparison between baseline (safishamsi/graphify) and current (your fork).

## Quick Start

```bash
cd validation && ./run.sh
```

One command does everything: clone corpus -> install both versions -> build graphs -> auto-discover targets from both graphs -> run query/path/explain at scale -> generate `COMPARISON.md`.

Targets are data-driven: common node labels are extracted from both graphs, ranked by degree, and used to generate {10 queries, 5 path pairs, 10 explain targets}. Works for any corpus — no hardcoded names.

## Why This Fork Beats the Baseline

Running on `microsoft/vscode` (9,936 files, ~11.5M words) — a production codebase:

> **Note on query engine:** Upstream PyPI `graphifyy==0.5.7` lacks the `graphify.search` module (BM25 orchestrator). It falls back to keyword substring match + BFS. The fork uses BM25 search on labels/paths/docstrings. Both engines run against their own graph; the graph structure differences (below) are the primary driver of quality improvement, not the engine.

| Metric | Baseline | Current | Improvement |
|--------|----------|---------|-------------|
| Graph size | 164 MB | 106 MB | **35% smaller** |
| Communities detected | 2,419 | 3,716 | **54% more granular** |
| Noise edges (`localize()` fan-out) | 2,628 edges | 4 edges | **pruned** |
| Cross-file calls resolved | 0 | 70,788 | **new capability** |
| Query target hit rate | ~10% | ~80% | **8× improvement** |
| Path latency (avg) | 62.3ms | 58.6ms | **6% faster** |

### Query Quality: Before vs After

**Q: "how does lifecycle.ts work?"**
- *Baseline:* 51 results — chat renderer methods, Playwright driver, `localize()` noise. **Zero results about `lifecycle.ts`.**
- *Current:* 10 results — all variants of `lifecycle.ts` across modules + its true dependents.

**Q: "what role does event.ts play?"**
- *Baseline:* 60 results — random browser infrastructure, `localize()`, Playwright code. **Zero results about `event.ts`.**
- *Current:* 10 results — all `event.ts` variants + the file's semantic connections.

**Q: "describe the function of async.ts"**
- *Baseline:* 22 results — Python test data from copilot extension. **Zero results about `async.ts`.**
- *Current:* 10 results — `.work()`, `.run()`, and `async.ts` module hubs.

### Explain Quality: Before vs After

| Node | Baseline degree | Current degree | Meaning |
|------|----------------|----------------|---------|
| `localize()` | 2,628 | 4 | Noise eliminated — only real callers |
| `lifecycle.ts` | 1 | 2,674 | Real connections discovered |
| `uri.ts` | 1 | 1,998 | Real connections discovered |
| `event.ts` | 2 | 1,725 | Real connections discovered |
| `test-checker.ts` | 1,582 | 1,582 | Identical — preserved correctly |

### The Core Change

The baseline connected utility functions (`localize()`, `toDisposable()`, `autorun`) to *every file that imported them* — creating massive noise edges that polluted all queries. The current graph replaces import-fan-out with cross-file call resolution (`call_dag`), connecting nodes only through real call relationships. Result: **smaller graph, richer connections, correct answers.**

## CLI Options

```
./run.sh [options]

Options:
  --corpus <path|url>   Repo path or git URL (default: vscode)
  --clean               Remove all artifacts (venvs, outputs, corpus)
  --skip-setup          Skip venv creation + corpus clone
  --skip-build          Skip graph building
  --skip-query          Skip query/benchmark execution
```

Examples:
```bash
./run.sh --corpus https://github.com/torvalds/linux
./run.sh --corpus /path/to/local/repo
./run.sh --skip-setup --skip-build   # just re-run queries + report
./run.sh --clean                         # wipe everything
```

## What It Does

1. **Setup** - clones `microsoft/vscode` (shallow, ~1.2 GB) as the default corpus, creates isolated venvs for baseline (PyPI `graphifyy`) and current (local `pip install -e`)
2. **Build** - runs `graphify update` on both versions against the same corpus (AST-only, no LLM)
3. **Queries + Report** - auto-discovers common node labels from both graphs, runs 10 queries, 5 shortest-paths, and 10 node explains on each version (50 CLI calls total), generates `COMPARISON.md` with per-query breakdowns, median/avg stats, and side-by-side comparison

## Prerequisites

- Python 3.12+
- git

## Output

```
validation/
├── COMPARISON.md            # auto-generated comparison report
├── corpora/
│   └── vscode/              # default corpus (or custom name)
├── out-baseline/            # baseline graph + query results
│   ├── graph.json
│   ├── GRAPH_REPORT.md
│   ├── query/response.txt
│   ├── path/response.txt
│   ├── explain/response.txt
├── out-speedai/             # current graph + query results
│   └── ...
├── .venv-baseline/          # isolated baseline venv
└── .venv-speedai/           # isolated current venv
```

## Re-running

```bash
# Full run (rebuild everything)
./run.sh

# Skip setup (reuse existing corpus + venvs)
./run.sh --skip-setup

# Just regenerate report from existing outputs
.venv-speedai/bin/python generate_report.py
```
