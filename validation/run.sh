#!/bin/bash
set -euo pipefail

VALIDATION_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$VALIDATION_DIR")"

DEFAULT_CORPUS_URL="https://github.com/microsoft/vscode"
DEFAULT_CORPUS_DIR="/tmp/graphify-validation/vscode"

VENV_B="$VALIDATION_DIR/.venv-baseline"
VENV_C="$VALIDATION_DIR/.venv-current"

NOW=$(date +%Y-%m-%d-%H%M%S)
RUN_DIR="$VALIDATION_DIR/runs/$NOW"
OUT_B="$RUN_DIR/out-baseline"
OUT_C="$RUN_DIR/out-current"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

header() { printf "\n${CYAN}=== %s ===${NC}\n" "$1"; }
ok()     { printf "  ${GREEN}OK${NC}\n"; }
fail()   { printf "  ${RED}FAIL: %s${NC}\n" "$1" >&2; exit 1; }
warn()   { printf "  ${YELLOW}WARNING: %s${NC}\n" "$1"; }

# ── Parse args ────────────────────────────────────────────────────
SKIP_SETUP=0; SKIP_BUILD=0; SKIP_QUERIES=0; CLEAN=0
CORPUS_ARG=""; TAG_ARG=""; COMPARE_AGAINST=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --corpus)   CORPUS_ARG="$2"; shift 2 ;;
        --clean)    CLEAN=1; shift ;;
        --skip-setup)   SKIP_SETUP=1; shift ;;
        --skip-build)   SKIP_BUILD=1; shift ;;
        --skip-queries) SKIP_QUERIES=1; shift ;;
        --tag)      TAG_ARG="$2"; shift 2 ;;
        --compare-against) COMPARE_AGAINST="$2"; shift 2 ;;
        -h|--help)
            cat <<'HELP'
Usage: ./run.sh [options]

Options:
  --corpus <path|url>   Repo path or git URL (default: microsoft/vscode in /tmp)
  --clean               Remove run artifacts (venvs, outputs) + /tmp corpus
  --skip-setup          Skip venv creation + corpus clone
  --skip-build          Skip graph building
  --skip-queries        Skip query/benchmark execution
  --tag <name>          Label this run in TIMELINE.md
  --compare-against <dir>  Compare against a previous run directory

Output:
  runs/YYYY-MM-DD-HHMMSS/
    out-baseline/   graph.json + GRAPH_REPORT.md + build.log
    out-current/    graph.json + GRAPH_REPORT.md + build.log
    COMPARISON.md   human-readable comparison report
    metrics.json    machine-readable metrics (CI-gatable)
    ASSESSMENT.md   progress/regression + recommendations

  latest -> runs/YYYY-MM-DD-HHMMSS (symlink)
  TIMELINE.md       cumulative tracking across all runs
HELP
            exit 0 ;;
        *) fail "Unknown flag: $1" ;;
    esac
done

# ── Resolve corpus path ───────────────────────────────────────────
if [ -z "$CORPUS_ARG" ]; then
    CORPUS_DIR="$DEFAULT_CORPUS_DIR"
    CORPUS_CLONE_URL="$DEFAULT_CORPUS_URL"
else
    if [ -d "$CORPUS_ARG" ]; then
        CORPUS_DIR="$CORPUS_ARG"
        CORPUS_CLONE_URL=""
    else
        REPO_NAME=$(basename "$CORPUS_ARG" .git)
        CORPUS_DIR="/tmp/graphify-validation/$REPO_NAME"
        CORPUS_CLONE_URL="$CORPUS_ARG"
    fi
fi

trap 'rm -f "$VALIDATION_DIR"/.tmp_*' EXIT

# ── Prereq check ─────────────────────────────────────────────────
check_prereqs() {
    local missing=0
    for cmd in python3 git; do
        command -v "$cmd" &>/dev/null || { printf "${RED}Missing: %s${NC}\n" "$cmd"; missing=1; }
    done
    [ $missing -eq 0 ] || exit 1
}

# ── Helpers ──────────────────────────────────────────────────────
move_graphify_out() {
    local dest="$1"
    local src="$CORPUS_DIR/graphify-out"
    if [ -d "$src" ] && [ -n "$(ls -A "$src" 2>/dev/null)" ]; then
        mv "$src"/* "$dest"/
    fi
    rm -rf "$src"
}

run_build() {
    local label="$1" venv="$2" outdir="$3"
    printf "  Building %s graph...\n" "$label"
    local log="$outdir/build.log"
    local start
    start=$(date +%s)
    if ! "$venv/bin/graphify" update "$CORPUS_DIR" > "$log" 2>&1; then
        printf "    ${RED}%s build FAILED${NC}\n" "$label"
        cat "$log"
        return 1
    fi
    local elapsed=$(( $(date +%s) - start ))
    printf "    Build time: %ds\n" "$elapsed"
    echo "$elapsed" > "$outdir/build_time.txt"
    move_graphify_out "$outdir"
    return 0
}

# ── Timeline helper ──────────────────────────────────────────────
append_timeline() {
    local timeline="$VALIDATION_DIR/TIMELINE.md"
    local tag="${TAG_ARG:-}"
    local label="${tag:+($tag) }$NOW"
    local nodes_b nodes_c edges_b edges_c

    if [ -f "$OUT_B/graph.json" ]; then
        nodes_b=$(python3 -c "import json; g=json.load(open('$OUT_B/graph.json')); print(len(g.get('nodes',[])))" 2>/dev/null || echo "?")
        edges_b=$(python3 -c "import json; g=json.load(open('$OUT_B/graph.json')); print(len(g.get('links',g.get('edges',[]))))" 2>/dev/null || echo "?")
    else
        nodes_b="?"; edges_b="?"
    fi

    if [ -f "$OUT_C/graph.json" ]; then
        nodes_c=$(python3 -c "import json; g=json.load(open('$OUT_C/graph.json')); print(len(g.get('nodes',[])))" 2>/dev/null || echo "?")
        edges_c=$(python3 -c "import json; g=json.load(open('$OUT_C/graph.json')); print(len(g.get('links',g.get('edges',[]))))" 2>/dev/null || echo "?")
    else
        nodes_c="?"; edges_c="?"
    fi

    if [ ! -f "$timeline" ]; then
        cat > "$timeline" <<'TLEOF'
# Validation Timeline

| Run | Tag | Baseline Nodes | Baseline Edges | Current Nodes | Current Edges |
|-----|-----|---------------|---------------|--------------|--------------|
TLEOF
    fi

    echo "| $label | $tag | $nodes_b | $edges_b | $nodes_c | $edges_c |" >> "$timeline"
}

# ── Clean mode ──────────────────────────────────────────────────
if [ $CLEAN -eq 1 ]; then
    header "Clean"
    rm -rf "$VENV_B" "$VENV_C"
    if [ -z "$CORPUS_ARG" ]; then
        rm -rf "$DEFAULT_CORPUS_DIR"
    fi
    printf "  ${GREEN}Removed venvs + default corpus.${NC}\n"
    printf "  Run directories in validation/runs/ are preserved.\n"
    printf "  To remove all runs: rm -rf validation/runs/\n"
    exit 0
fi

# ── Phase 0: Prereqs ────────────────────────────────────────────
header "Phase 0: Prerequisites"
check_prereqs

printf "  Run directory: %s\n" "$RUN_DIR"
mkdir -p "$RUN_DIR" "$OUT_B" "$OUT_C"
rm -f "$VALIDATION_DIR/latest"
ln -sf "$RUN_DIR" "$VALIDATION_DIR/latest"

if [ -n "$COMPARE_AGAINST" ]; then
    printf "  Comparing against: %s\n" "$COMPARE_AGAINST"
fi
ok

# ── Phase 1: Setup (Corpus + Venvs) ─────────────────────────────
if [ $SKIP_SETUP -eq 0 ]; then
    header "Phase 1: Setup"

    # Corpus
    if [ -n "$CORPUS_CLONE_URL" ] && [ ! -d "$CORPUS_DIR" ]; then
        printf "  Cloning %s ...\n" "$CORPUS_CLONE_URL"
        mkdir -p "$(dirname "$CORPUS_DIR")"
        git clone --depth 1 --single-branch "$CORPUS_CLONE_URL" "$CORPUS_DIR"
        printf "    Corpus ready: %s\n" "$CORPUS_DIR"
    else
        if [ -n "$CORPUS_CLONE_URL" ]; then
            printf "  Corpus: %s (exists)\n" "$CORPUS_DIR"
        else
            printf "  Corpus: %s (local)\n" "$CORPUS_DIR"
        fi
    fi

    # Baseline venv (PyPI)
    if [ ! -d "$VENV_B" ]; then
        printf "  Creating baseline venv (PyPI graphifyy)...\n"
        python3 -m venv "$VENV_B"
        "$VENV_B/bin/pip" install 'graphifyy[all]' || fail "Baseline pip install failed"
    else
        printf "  Baseline venv: exists\n"
    fi

    # Current venv (local repo)
    if [ ! -d "$VENV_C" ]; then
        printf "  Creating current venv (local graphify)...\n"
        python3 -m venv "$VENV_C"
        "$VENV_C/bin/pip" install -e "$PROJECT_ROOT[all]" || fail "Current pip install failed"
    else
        printf "  Current venv: exists\n"
    fi

    header "Versions"
    printf "  Baseline: %s\n" "$("$VENV_B/bin/pip" show graphifyy 2>/dev/null | awk '/^Version:/{print $2}' || echo '?')"
    printf "  Current:  %s\n" "$("$VENV_C/bin/pip" show graphifyy 2>/dev/null | awk '/^Version:/{print $2}' || echo '?')"
fi

# ── Phase 2: Build ──────────────────────────────────────────────
if [ $SKIP_BUILD -eq 0 ]; then
    header "Phase 2: Build"
    [ -d "$CORPUS_DIR" ] || fail "Corpus missing. Run without --skip-setup or specify --corpus."

    rm -rf "$CORPUS_DIR/graphify-out"
    run_build "baseline" "$VENV_B" "$OUT_B" || fail "Baseline build failed"
    ok

    rm -rf "$CORPUS_DIR/graphify-out"
    run_build "current" "$VENV_C" "$OUT_C" || fail "Current build failed"
    ok

    [ -f "$OUT_B/graph.json" ] && [ -f "$OUT_C/graph.json" ] || \
        fail "graph.json missing after build phase"
fi

# ── Phase 3: Queries ────────────────────────────────────────────
if [ $SKIP_QUERIES -eq 0 ]; then
    header "Phase 3: Queries"
    [ -f "$OUT_B/graph.json" ] && [ -f "$OUT_C/graph.json" ] || \
        fail "graph.json not found. Run build phase first."

    "$VENV_C/bin/python" "$VALIDATION_DIR/generate_report.py" \
        --out-b "$OUT_B" \
        --out-c "$OUT_C" \
        --venv-b "$VENV_B" \
        --venv-c "$VENV_C" \
        --run-dir "$RUN_DIR" \
        || fail "Query execution failed"
    ok
else
    header "Phase 3: Queries (skipped)"
fi

# ── Phase 4: Comparison ─────────────────────────────────────────
header "Phase 4: Comprehensive Comparison"

if [ -f "$RUN_DIR/query_results.json" ]; then
    COMPARE_ARGS=("$VALIDATION_DIR/compare.py" --run-dir "$RUN_DIR" --out-b "$OUT_B" --out-c "$OUT_C")
    [ -n "$COMPARE_AGAINST" ] && COMPARE_ARGS+=(--against "$COMPARE_AGAINST")
    "$VENV_C/bin/python" "${COMPARE_ARGS[@]}" || warn "Comparison had warnings"
    ok
else
    warn "No query results — comparison limited to graph structure only"
    COMPARE_ARGS=("$VALIDATION_DIR/compare.py" --run-dir "$RUN_DIR" --out-b "$OUT_B" --out-c "$OUT_C" --structure-only)
    [ -n "$COMPARE_AGAINST" ] && COMPARE_ARGS+=(--against "$COMPARE_AGAINST")
    "$VENV_C/bin/python" "${COMPARE_ARGS[@]}" || warn "Structure comparison had warnings"
fi

# ── Phase 5: Assessment ─────────────────────────────────────────
header "Phase 5: Assessment"

ASSESS_ARGS=("$VALIDATION_DIR/assess.py" --run-dir "$RUN_DIR")
[ -n "$COMPARE_AGAINST" ] && ASSESS_ARGS+=(--against "$COMPARE_AGAINST")
"$VENV_C/bin/python" "${ASSESS_ARGS[@]}" || warn "Assessment had warnings"
ok

# ── Timeline ────────────────────────────────────────────────────
append_timeline

printf "\n${GREEN}Done.${NC}\n"
printf "  Run:    %s\n" "$RUN_DIR"
printf "  Report: %s/COMPARISON.md\n" "$RUN_DIR"
printf "  Assess: %s/ASSESSMENT.md\n" "$RUN_DIR"
printf "  JSON:   %s/metrics.json\n" "$RUN_DIR"
printf "  Timeline: %s/TIMELINE.md\n" "$VALIDATION_DIR"
