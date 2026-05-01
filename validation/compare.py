"""Baseline vs current comparison engine. Computes deltas, detects regressions."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from .config import MetricThreshold, ValidationConfig


@dataclass
class MetricDelta:
    metric_name: str
    baseline_value: float
    current_value: float
    delta: float          # current - baseline (absolute) or % change
    delta_pct: float      # percentage change: ((current - baseline) / baseline) * 100
    direction: str        # "higher_is_better" | "lower_is_better"
    verdict: str          # "pass" | "warn" | "fail" | "no_baseline" | "n/a"


@dataclass 
class ComparisonResult:
    pr_name: str
    baseline_ref: str      # "PR 1.1" or previous PR
    deltas: List[MetricDelta] = field(default_factory=list)
    summary: str = ""      # "pass" | "warn" | "fail"
    warnings: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)


def load_baseline(baseline_path: Path) -> Dict:
    """Load baseline benchmark JSON."""
    if not baseline_path.exists():
        return {}
    return json.loads(baseline_path.read_text())


def load_current(results_path: Path) -> Dict:
    """Load current benchmark JSON."""
    if not results_path.exists():
        return {}
    return json.loads(results_path.read_text())


def compute_delta(
    metric: MetricThreshold,
    baseline_value: Optional[float],
    current_value: Optional[float],
) -> MetricDelta:
    """Compare baseline vs current, determine pass/warn/fail."""
    if baseline_value is None or current_value is None:
        return MetricDelta(
            metric_name=metric.name,
            baseline_value=baseline_value or 0,
            current_value=current_value or 0,
            delta=0,
            delta_pct=0,
            direction=metric.direction,
            verdict="no_baseline" if baseline_value is None else "n/a",
        )

    absolute_delta = current_value - baseline_value
    
    if baseline_value == 0:
        delta_pct = 0.0
    else:
        delta_pct = (absolute_delta / abs(baseline_value)) * 100

    # Determine verdict
    if metric.compare_as == "percent_change":
        compare_value = abs(delta_pct)
    else:
        compare_value = abs(absolute_delta)

    # For "higher_is_better", a drop is bad
    # For "lower_is_better", an increase is bad
    is_regression = (
        (metric.direction == "higher_is_better" and current_value < baseline_value) or
        (metric.direction == "lower_is_better" and current_value > baseline_value)
    )

    if not is_regression:
        verdict = "pass"
    elif compare_value >= metric.fail_threshold:
        verdict = "fail"
    elif compare_value >= metric.warn_threshold:
        verdict = "warn"
    else:
        verdict = "pass"

    return MetricDelta(
        metric_name=metric.name,
        baseline_value=baseline_value,
        current_value=current_value,
        delta=absolute_delta,
        delta_pct=delta_pct,
        direction=metric.direction,
        verdict=verdict,
    )


def compare(
    baseline: Dict,
    current: Dict,
    config: ValidationConfig,
    pr_name: str,
    baseline_ref: str,
) -> ComparisonResult:
    """Full comparison: all metrics from config against baseline."""
    result = ComparisonResult(pr_name=pr_name, baseline_ref=baseline_ref)

    for metric in config.all_metrics():
        baseline_val = baseline.get(metric.name)
        current_val = current.get(metric.name)
        delta = compute_delta(metric, baseline_val, current_val)
        result.deltas.append(delta)

        if delta.verdict == "warn":
            result.warnings.append(
                f"{metric.name}: {baseline_val} → {current_val} "
                f"({'↑' if delta.delta > 0 else '↓'}{abs(delta.delta_pct):.1f}%)"
            )
        elif delta.verdict == "fail":
            result.failures.append(
                f"{metric.name}: {baseline_val} → {current_val} "
                f"({'↑' if delta.delta > 0 else '↓'}{abs(delta.delta_pct):.1f}%)"
            )

    if result.failures:
        result.summary = "fail"
    elif result.warnings:
        result.summary = "warn"
    else:
        result.summary = "pass"

    return result


def compare_against_previous(
    all_results: Dict[str, Dict],  # PR name → metrics dict
    config: ValidationConfig,
) -> List[ComparisonResult]:
    """Compare each PR against its predecessor to find which PR caused gains/regressions."""
    comparisons = []
    pr_names = sorted(all_results.keys())

    for i, pr_name in enumerate(pr_names):
        baseline_ref = pr_names[i - 1] if i > 0 else "baseline"
        baseline = all_results[baseline_ref] if i > 0 else all_results[pr_name]
        current = all_results[pr_name]
        result = compare(baseline, current, config, pr_name, baseline_ref)
        comparisons.append(result)

    return comparisons
