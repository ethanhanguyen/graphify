from __future__ import annotations
import networkx as nx

_CI_PRIORITY = {"EXTRACTED": 0, "INFERRED": 1, "AMBIGUOUS": 2}


def select_start_nodes_by_degree(G: nx.Graph, candidates: list[str]) -> str:
    """From scored candidates, pick the one with lowest degree.

    This is the most selective start point, minimizing fan-out during traversal.
    """
    if not candidates:
        return ""
    return min(candidates, key=lambda n: G.degree(n))


def order_frontier_by_confidence(
    G: nx.Graph, frontier: list[str], preference: str = "extracted"
) -> list[str]:
    """Reorder frontier: prefer EXTRACTED edges before INFERRED before AMBIGUOUS.

    Uses edge confidence ordering. Within same confidence level, lower-degree
    nodes come first for better selectivity.

    preference can be "extracted" (EXTRACTED first), "inferred" (INFERRED first),
    or "all" (no reordering by confidence).
    """
    if preference == "all":
        return sorted(frontier, key=lambda n: G.degree(n))

    conf_order = {
        "extracted": ["EXTRACTED", "INFERRED", "AMBIGUOUS"],
        "inferred": ["INFERRED", "EXTRACTED", "AMBIGUOUS"],
    }

    order = conf_order.get(preference, conf_order["extracted"])
    rank = {ci: i for i, ci in enumerate(order)}

    def best_incoming_confidence(node: str) -> int:
        best = 99
        for neighbor in G.neighbors(node):
            edata = G.edges[neighbor, node]
            ci = edata.get("confidence", "EXTRACTED")
            best = min(best, rank.get(ci, 99))
        return best

    return sorted(frontier, key=lambda n: (best_incoming_confidence(n), G.degree(n)))


def reorder_frontier_at_hop(
    G: nx.Graph, current_frontier: set[str], visited: set[str]
) -> list[str]:
    """At each BFS hop, reorder: lowest-degree nodes first, then confidence priority.

    Excludes already-visited nodes.
    """
    unvisited = [n for n in current_frontier if n not in visited]
    if not unvisited:
        return []
    ranked = []
    for n in unvisited:
        best_ci = 2
        for neighbor in G.neighbors(n):
            edata = G.edges[neighbor, n]
            ci = edata.get("confidence", "EXTRACTED")
            best_ci = min(best_ci, _CI_PRIORITY.get(ci, 2))
        ranked.append((best_ci, G.degree(n), n))
    ranked.sort()
    return [n for _, _, n in ranked]
