#!/usr/bin/env bash
set -euo pipefail

echo "=== PR 10: Multi-Repo Groups — Verification ==="
echo ""

cd "$(dirname "$0")/../.."

echo "[1/4] Unit tests for new modules..."
rtk python -m pytest tests/test_registry.py tests/test_lazy_pool.py tests/test_groups.py tests/test_contract_bridge.py -q

TOTAL_NEW=$(rtk python -m pytest tests/test_registry.py tests/test_lazy_pool.py tests/test_groups.py tests/test_contract_bridge.py --collect-only -q 2>&1 | tail -1)
echo "  New module tests: $TOTAL_NEW"

echo ""
echo "[2/4] Full test suite (excluding pre-existing language failures)..."
FULL=$(rtk python -m pytest tests/ --ignore=tests/test_languages.py -q 2>&1 | tail -1)
echo "  $FULL"

echo ""
echo "[3/4] Coverage report (target >= 90%)..."
COV=$(rtk python -m pytest tests/test_registry.py tests/test_lazy_pool.py tests/test_groups.py tests/test_contract_bridge.py --cov=graphify.registry --cov=graphify.lazy_pool --cov=graphify.groups --cov=graphify.contract_bridge --cov-report=term -q 2>&1 | grep TOTAL)
echo "  $COV"

echo ""
echo "[4/4] Multi-Repo benchmark..."
rtk python -m graphify benchmark --seed 42 --phase 10 --compare graphify-out/benchmarks/phase-9-benchmark.json

echo ""
echo "=== Verification complete ==="
echo "Commit with: git add -A && git commit -m \"feat(phase-13): multi-repo groups (registry + lazy pool + contract bridge)\""
