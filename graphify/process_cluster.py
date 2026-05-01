from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from graphify.processes import Process, ProcessStep


@dataclass
class ProcessCluster:
    canonical: Process
    variants: list[Process] = field(default_factory=list)
    cohesion_score: float = 0.0


def cluster_processes(processes: list[Process], overlap_threshold: float = 0.9) -> list[ProcessCluster]:
    if not processes:
        return []

    sorted_procs = sorted(processes, key=lambda p: p.total_steps, reverse=True)
    clusters: list[ProcessCluster] = []
    assigned: set[int] = set()

    for i, canonical in enumerate(sorted_procs):
        if i in assigned:
            continue

        cluster = ProcessCluster(canonical=canonical, variants=[canonical])
        assigned.add(i)

        canonical_sigs = _node_signature(canonical)

        for j, other in enumerate(sorted_procs):
            if j in assigned:
                continue
            other_sigs = _node_signature(other)
            if not canonical_sigs or not other_sigs:
                continue

            overlap = len(canonical_sigs & other_sigs) / max(len(canonical_sigs | other_sigs), 1)

            if overlap >= overlap_threshold:
                cluster.variants.append(other)
                assigned.add(j)

        cluster.cohesion_score = _compute_cohesion(cluster)
        clusters.append(cluster)

    return sorted(clusters, key=lambda c: c.cohesion_score, reverse=True)


def deduplicate(processes: list[Process]) -> list[Process]:
    if not processes:
        return []

    clusters = cluster_processes(processes)
    result: list[Process] = []
    for cluster in clusters:
        result.append(merge_cluster(cluster))
    return result


def merge_cluster(cluster: ProcessCluster) -> Process:
    if not cluster.variants:
        return cluster.canonical

    deepest = max(cluster.variants, key=lambda p: p.total_steps)

    all_step_ids: dict[str, ProcessStep] = {}
    for p in cluster.variants:
        for step in p.steps:
            if step.node_id not in all_step_ids or step.depth < all_step_ids[step.node_id].depth:
                all_step_ids[step.node_id] = step

    merged_steps = sorted(all_step_ids.values(), key=lambda s: s.depth)

    return deepest.__class__(
        name=cluster.canonical.name,
        entry_point=cluster.canonical.entry_point,
        steps=merged_steps,
        total_steps=len(merged_steps),
        max_depth=max((s.depth for s in merged_steps), default=0),
        language=cluster.canonical.language,
        framework=cluster.canonical.framework,
        confidence=cluster.canonical.confidence * cluster.cohesion_score,
        cyclomatic_complexity=deepest.cyclomatic_complexity,
        external_touches=deepest.external_touches,
    )


def _node_signature(process: Process) -> set[str]:
    return {step.node_id for step in process.steps}


def _compute_cohesion(cluster: ProcessCluster) -> float:
    if len(cluster.variants) <= 1:
        return 1.0

    canonical_sigs = _node_signature(cluster.canonical)

    overlaps = []
    for variant in cluster.variants:
        variant_sigs = _node_signature(variant)
        if not canonical_sigs or not variant_sigs:
            continue
        overlap = len(canonical_sigs & variant_sigs) / max(len(canonical_sigs | variant_sigs), 1)
        overlaps.append(overlap)

    return sum(overlaps) / len(overlaps) if overlaps else 1.0
