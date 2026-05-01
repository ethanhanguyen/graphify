# Validation thresholds and metric definitions
# All thresholds are "fail if worse than" limits

from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class MetricThreshold:
    name: str
    description: str
    unit: str
    direction: str  # "lower_is_better" | "higher_is_better"
    warn_threshold: float  # absolute value or % change that triggers warning
    fail_threshold: float  # absolute value or % change that triggers failure
    compare_as: str  # "absolute" | "percent_change"

@dataclass
class ValidationConfig:
    graph_scales: List[int] = field(default_factory=lambda: [1000, 10000, 50000, 100000, 500000])
    fixture_repos: List[str] = field(default_factory=lambda: [
        "tests/fixtures/typescript",
        "tests/fixtures/python",
        "tests/fixtures/go",
        "tests/fixtures/java",
    ])
    benchmark_repos: List[str] = field(default_factory=lambda: [])  # populated by user

    query_metrics: List[MetricThreshold] = field(default_factory=lambda: [
        MetricThreshold(
            name="query_graph_p50",
            description="query_graph 50th percentile latency",
            unit="ms",
            direction="lower_is_better",
            warn_threshold=20,   # 20% slower triggers warning
            fail_threshold=50,   # 50% slower triggers failure
            compare_as="percent_change",
        ),
        MetricThreshold(
            name="query_graph_p95",
            description="query_graph 95th percentile latency",
            unit="ms",
            direction="lower_is_better",
            warn_threshold=20,
            fail_threshold=50,
            compare_as="percent_change",
        ),
        MetricThreshold(
            name="shortest_path_p50",
            description="shortest_path 50th percentile latency",
            unit="ms",
            direction="lower_is_better",
            warn_threshold=20,
            fail_threshold=50,
            compare_as="percent_change",
        ),
        MetricThreshold(
            name="memory_mb",
            description="Peak resident memory during benchmark",
            unit="MB",
            direction="lower_is_better",
            warn_threshold=30,
            fail_threshold=100,
            compare_as="percent_change",
        ),
    ])

    code_intelligence_metrics: List[MetricThreshold] = field(default_factory=lambda: [
        MetricThreshold(
            name="call_resolution_pct",
            description="Percentage of cross-file calls correctly resolved",
            unit="%",
            direction="higher_is_better",
            warn_threshold=2,    # 2% drop triggers warning
            fail_threshold=5,    # 5% drop triggers failure
            compare_as="absolute",
        ),
        MetricThreshold(
            name="process_trace_completeness_pct",
            description="Percentage of entry points with non-empty traces",
            unit="%",
            direction="higher_is_better",
            warn_threshold=2,
            fail_threshold=5,
            compare_as="absolute",
        ),
        MetricThreshold(
            name="ndcg_at_10",
            description="NDCG@10 for hybrid search relevance",
            unit="score",
            direction="higher_is_better",
            warn_threshold=0.05,
            fail_threshold=0.1,
            compare_as="absolute",
        ),
        MetricThreshold(
            name="context_accuracy_pct",
            description="Percentage of context() responses with correct incoming/outgoing calls",
            unit="%",
            direction="higher_is_better",
            warn_threshold=2,
            fail_threshold=5,
            compare_as="absolute",
        ),
        MetricThreshold(
            name="impact_accuracy_pct",
            description="Percentage of impact() responses with correct blast radius",
            unit="%",
            direction="higher_is_better",
            warn_threshold=2,
            fail_threshold=5,
            compare_as="absolute",
        ),
    ])

    index_metrics: List[MetricThreshold] = field(default_factory=lambda: [
        MetricThreshold(
            name="edge_type_lookup_us",
            description="Edge-type index lookup latency (100k-node graph)",
            unit="us",
            direction="lower_is_better",
            warn_threshold=50,
            fail_threshold=100,
            compare_as="percent_change",
        ),
        MetricThreshold(
            name="node_label_lookup_us",
            description="Node label index lookup latency (100k-node graph)",
            unit="us",
            direction="lower_is_better",
            warn_threshold=50,
            fail_threshold=100,
            compare_as="percent_change",
        ),
        MetricThreshold(
            name="composite_lookup_us",
            description="Composite index (type+confidence+label) lookup latency",
            unit="us",
            direction="lower_is_better",
            warn_threshold=50,
            fail_threshold=100,
            compare_as="percent_change",
        ),
    ])

    cache_metrics: List[MetricThreshold] = field(default_factory=lambda: [
        MetricThreshold(
            name="cache_hit_rate_pct",
            description="Query cache hit rate after 10 repeated queries",
            unit="%",
            direction="higher_is_better",
            warn_threshold=5,
            fail_threshold=15,
            compare_as="absolute",
        ),
        MetricThreshold(
            name="cached_latency_p50",
            description="Cached query 50th percentile latency",
            unit="ms",
            direction="lower_is_better",
            warn_threshold=10,
            fail_threshold=30,
            compare_as="percent_change",
        ),
    ])

    coverage_metrics: List[MetricThreshold] = field(default_factory=lambda: [
        MetricThreshold(
            name="line_coverage_pct",
            description="Line coverage percentage",
            unit="%",
            direction="higher_is_better",
            warn_threshold=1,
            fail_threshold=3,
            compare_as="absolute",
        ),
        MetricThreshold(
            name="branch_coverage_pct",
            description="Branch coverage percentage",
            unit="%",
            direction="higher_is_better",
            warn_threshold=2,
            fail_threshold=5,
            compare_as="absolute",
        ),
    ])

    # Overall gate thresholds
    min_overall_coverage: float = 90.0
    min_call_resolution_accuracy: float = 95.0
    min_process_trace_completeness: float = 95.0
    min_ndcg_at_10: float = 0.75

    def all_metrics(self) -> List[MetricThreshold]:
        return (self.query_metrics + self.code_intelligence_metrics +
                self.index_metrics + self.cache_metrics + self.coverage_metrics)
