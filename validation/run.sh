#!/bin/bash
set -euo pipefail

# ── Paths ─────────────────────────────────────────────────────────
VALIDATION_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$VALIDATION_DIR")"

DEFAULT_CORPUS_DIR="$VALIDATION_DIR/corpora/vscode"
DEFAULT_CORPUS_URL="https://github.com/microsoft/vscode"
OUT_B="$VALIDATION_DIR/out-baseline"
OUT_S="$VALIDATION_DIR/out-speedai"
VENV_B="$VALIDATION_DIR/.venv-baseline"
VENV_S="$VALIDATION_DIR/.venv-speedai"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

header() { printf "${CYAN}=== %s ===${NC}\n" "$1"; }
ok()     { printf "${GREEN}  OK${NC}\n"; }
fail()   { printf "${RED}  FAIL: %s${NC}\n" "$1" >&2; exit 1; }
warn()   { printf "${YELLOW}  WARNING: %s${NC}\n" "$1"; }

# ── Parse args ────────────────────────────────────────────────────
SKIP_SETUP=0; SKIP_BUILD=0; SKIP_QUERY=0; CLEAN=0; CORPUS_ARG=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --corpus) CORPUS_ARG="$2"; shift 2 ;;
        --clean) CLEAN=1; shift ;;
        --skip-setup) SKIP_SETUP=1; shift ;;
        --skip-build) SKIP_BUILD=1; shift ;;
        --skip-query) SKIP_QUERY=1; shift ;;
        -h|--help)
            cat <<'HELP'
Usage: ./run.sh [options]

Options:
  --corpus <path|url>  Repo path or git URL (default: vscode)
  --clean              Remove all artifacts (venvs, outputs, corpus)
  --skip-setup         Skip venv creation + corpus clone
  --skip-build         Skip graph building
  --skip-query         Skip query/benchmark execution
HELP
            exit 0 ;;
        *) fail "Unknown flag: $1" ;;
    esac
done

# ── Resolve corpus path ───────────────────────────────────────────
if [ -z "$CORPUS_ARG" ]; then
    CORPUS_DIR="$DEFAULT_CORPUS_DIR"
else
    if [ -d "$CORPUS_ARG" ]; then
        CORPUS_DIR="$CORPUS_ARG"
    else
        REPO_NAME=$(basename "$CORPUS_ARG" .git)
        CORPUS_DIR="$VALIDATION_DIR/corpora/$REPO_NAME"
        CORPUS_CLONE_URL="$CORPUS_ARG"
    fi
fi

# ── Trap cleanup ──────────────────────────────────────────────────
trap 'rm -f "$VALIDATION_DIR"/.tmp_*' EXIT

# ── Prerequisite check ────────────────────────────────────────────
check_prereqs() {
    local missing=0
    for cmd in python3 git; do
        command -v "$cmd" &>/dev/null || { printf "${RED}Missing: %s${NC}\n" "$cmd"; missing=1; }
    done
    [ $missing -eq 0 ] || exit 1
}

# ── Helpers ───────────────────────────────────────────────────────
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
    printf "Building %s graph...\n" "$label"
    local log="$VALIDATION_DIR/.tmp_${label}_log"
    local start
    start=$(date +%s)
    if ! "$venv/bin/graphify" update "$CORPUS_DIR" > "$log" 2>&1; then
        printf "  ${RED}%s build FAILED${NC}\n" "$label"
        cat "$log"
        return 1
    fi
    printf "  Build time: %ds\n" $(( $(date +%s) - start ))
    move_graphify_out "$outdir"
    return 0
}

# ── Clean mode ────────────────────────────────────────────────────
if [ $CLEAN -eq 1 ]; then
    header "Clean"
    rm -rf "$OUT_B" "$OUT_S" "$VENV_B" "$VENV_S"
    if [ -z "$CORPUS_ARG" ]; then
        rm -rf "$DEFAULT_CORPUS_DIR"
    fi
    printf "${GREEN}Removed all artifacts.${NC}\n"
    exit 0
fi

# ── Phase 1: Setup ────────────────────────────────────────────────
check_prereqs

if [ $SKIP_SETUP -eq 0 ]; then
    header "Phase 1: Setup"

    # Corpus
    if [ ! -d "$CORPUS_DIR" ]; then
        CLONE_URL="${CORPUS_CLONE_URL:-$DEFAULT_CORPUS_URL}"
        mkdir -p "$(dirname "$CORPUS_DIR")"
        printf "Cloning %s ...\n" "$CLONE_URL"
        git clone --depth 1 --single-branch "$CLONE_URL" "$CORPUS_DIR"
        printf "  Corpus ready: %s\n" "$CORPUS_DIR"
    else
        printf "  Corpus: %s\n" "$CORPUS_DIR"
    fi

    # Baseline venv
    if [ ! -d "$VENV_B" ]; then
        printf "Creating baseline venv (PyPI graphifyy)...\n"
        python3 -m venv "$VENV_B"
        "$VENV_B/bin/pip" install 'graphifyy[all]' || fail "Baseline pip install failed"
        printf "  Baseline venv ready.\n"
    else
        printf "  Baseline venv exists.\n"
    fi

    # Current venv
    if [ ! -d "$VENV_S" ]; then
        printf "Creating current venv (local graphify)...\n"
        python3 -m venv "$VENV_S"
        "$VENV_S/bin/pip" install -e "$PROJECT_ROOT[all]" || fail "Current pip install failed"
        printf "  Current venv ready.\n"
    else
        printf "  Current venv exists.\n"
    fi

    header "Versions"
    printf "  Baseline: %s\n" "$("$VENV_B/bin/pip" show graphifyy 2>/dev/null | awk '/^Version:/{print $2}' || echo '?')"
    printf "  Current:  %s\n" "$("$VENV_S/bin/pip" show graphifyy 2>/dev/null | awk '/^Version:/{print $2}' || echo '?')"
    echo ""
fi

# ── Phase 2: Build ────────────────────────────────────────────────
if [ $SKIP_BUILD -eq 0 ]; then
    header "Phase 2: Build"
    [ -d "$CORPUS_DIR" ] || fail "Corpus missing. Run without --skip-setup or specify --corpus."

    rm -rf "$CORPUS_DIR/graphify-out"
    rm -rf "$OUT_B" "$OUT_S"
    mkdir -p "$OUT_B" "$OUT_S"

    run_build "baseline" "$VENV_B" "$OUT_B" || fail "Baseline build failed"
    ok

    rm -rf "$CORPUS_DIR/graphify-out"

    run_build "current" "$VENV_S" "$OUT_S" || fail "Current build failed"
    ok

    [ -f "$OUT_B/graph.json" ] && [ -f "$OUT_S/graph.json" ] || \
        fail "graph.json missing after build phase"
fi

# ── Phase 3: Queries + Report ─────────────────────────────────────
if [ $SKIP_QUERY -eq 0 ]; then
    header "Phase 3: Queries + Report"
    [ -f "$OUT_B/graph.json" ] && [ -f "$OUT_S/graph.json" ] || \
        fail "graph.json not found. Run build phase first."
    "$VENV_S/bin/python" "$VALIDATION_DIR/generate_report.py" || fail "Query/report failed"
    ok
else
    header "Phase 3: Report (cached queries)"
    "$VENV_S/bin/python" "$VALIDATION_DIR/generate_report.py" --skip-queries || fail "Report failed"
    ok
fi

printf "\n${GREEN}Done.${NC} Report: %s/COMPARISON.md\n" "$VALIDATION_DIR"
