from __future__ import annotations
from pathlib import Path
import networkx as nx
from graphify.index import get_edges_by_relation


def compute_transitive_closure(G: nx.Graph, relation_type: str) -> dict[tuple, int]:
    """Compute transitive closure over edges of a given relation type.

    Returns {(u, v): hop_distance} for all reachable pairs.
    """
    edges = get_edges_by_relation(G, relation_type)
    if not edges:
        edges = [
            (u, v)
            for u, v, data in G.edges(data=True)
            if data.get("relation") == relation_type
        ]

    adj: dict[str, set[str]] = {}
    for u, v, _ in edges:
        adj.setdefault(u, set()).add(v)
        adj.setdefault(v, set()).add(u)

    closure: dict[tuple, int] = {}

    for src in adj:
        dist: dict[str, int] = {src: 0}
        stack = [src]
        while stack:
            node = stack.pop()
            d = dist[node] + 1
            for nb in adj.get(node, set()):
                if nb not in dist:
                    dist[nb] = d
                    closure[(src, nb)] = d
                    stack.append(nb)

    return closure


def write_materialized_view(
    closure: dict[tuple, int], relation_type: str, output_dir: Path
) -> None:
    """Write closure as edge list: one line per (u, v, distance).

    Stored in output_dir/{relation_type}.edges
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{relation_type}.edges"
    lines = [f"{u}|{v}|{d}" for (u, v), d in sorted(closure.items())]
    out_file.write_text("\n".join(lines), encoding="utf-8")


def load_materialized_view(
    relation_type: str, input_dir: Path
) -> dict[tuple, int] | None:
    """Load precomputed closure. Returns None if not found."""
    in_file = input_dir / f"{relation_type}.edges"
    if not in_file.exists():
        return None
    closure: dict[tuple, int] = {}
    for line in in_file.read_text(encoding="utf-8").strip().split("\n"):
        if not line:
            continue
        parts = line.split("|")
        if len(parts) == 3:
            u, v, d = parts
            closure[(u, v)] = int(d)
    return closure


def check_materialized_path(
    G: nx.Graph, src: str, tgt: str, relation_type: str, matviews_dir: Path
) -> int | None:
    """O(1) lookup: is there a path of 'relation_type' edges from src to tgt?

    Returns hop distance or None if not found.
    """
    if src == tgt:
        return 0
    closure = load_materialized_view(relation_type, matviews_dir)
    if closure is None:
        return None
    result = closure.get((src, tgt))
    if result is not None:
        return result
    return closure.get((tgt, src))
