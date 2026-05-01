# Graphify Validation Suite

Apples-to-apples comparison between baseline (safishamsi/graphify) and current (your fork).

## Quick Start

```bash
cd validation && ./run.sh
```

One command does everything: clone corpus -> install both versions -> build graphs -> auto-discover targets from both graphs -> run query/path/explain at scale -> generate `COMPARISON.md`.

Targets are data-driven: common node labels are extracted from both graphs, ranked by degree, and used to generate {10 queries, 5 path pairs, 10 explain targets}. Works for any corpus — no hardcoded names.

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
