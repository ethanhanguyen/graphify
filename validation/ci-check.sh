#!/bin/bash
set -euo pipefail

VALIDATION_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$VALIDATION_DIR")"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

header() { printf "${CYAN}=== %s ===${NC}\n" "$1"; }
ok()     { printf "${GREEN}  OK${NC}\n"; }
fail()   { printf "${RED}  FAIL: %s${NC}\n" "$1" >&2; exit 1; }
warn()   { printf "${YELLOW}  WARNING: %s${NC}\n" "$1"; }

# === L1: pytest with coverage ===
header "L1: Unit Tests + Coverage"
cd "$PROJECT_ROOT"
python -m pytest tests/ -q --tb=short --timeout=30 2>&1 || fail "Tests failed"
ok

# === L2: Snapshot regression on fixture graphs ===
header "L2: Fixture Graph Regression"
FIXTURE_DIR="$PROJECT_ROOT/tests/fixtures"

rm -rf "$FIXTURE_DIR/graphify-out"

python -m graphify update "$FIXTURE_DIR" 2>&1 || fail "Fixture build failed"

GRAPH_FILE="$FIXTURE_DIR/graphify-out/graph.json"
[ -f "$GRAPH_FILE" ] || fail "graph.json not produced"

"$VALIDATION_DIR/.venv-speedai/bin/python" -c "
import json, sys
from pathlib import Path

g = json.loads(Path('$GRAPH_FILE').read_text())
nodes = g.get('nodes', [])
edges = g.get('edges', [])
n = len(nodes)
e = len(edges)

if n < 10:
    print(f'ERROR: only {n} nodes extracted from fixtures (expected >=10)')
    sys.exit(1)
if e < 5:
    print(f'ERROR: only {e} edges extracted from fixtures (expected >=5)')
    sys.exit(1)

# Verify typed schema: every node has a file_type
types = set(n.get('file_type', '') for n in nodes)
if 'code' not in types:
    print(f'ERROR: no code nodes found. types: {types}')
    sys.exit(1)

# Verify edge confidence
confs = set(e.get('confidence', '') for e in edges)
if 'EXTRACTED' not in confs:
    print(f'ERROR: no EXTRACTED edges. confidences: {confs}')
    sys.exit(1)

print(f'L2 PASS: {n} nodes, {e} edges, types={types}')
" || fail "Fixture graph validation failed"

ok

# === L3 (optional, only when BENCHMARK_AGAINST env set) ===
if [ -n "${BENCHMARK_AGAINST:-}" ] && [ -f "$BENCHMARK_AGAINST" ]; then
    header "L3: Regression against $BENCHMARK_AGAINST"
    "$VALIDATION_DIR/.venv-speedai/bin/python" "$VALIDATION_DIR/compare.py" \
        --baseline "$BENCHMARK_AGAINST" \
        --graph "$GRAPH_FILE" \
        --pr "$(git rev-parse --abbrev-ref HEAD)" || fail "Regression detected"
    ok
else
    header "L3: Skipped (no BENCHMARK_AGAINST snapshort)"
fi

header "All CI checks passed"
