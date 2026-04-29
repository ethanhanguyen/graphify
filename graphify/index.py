# indexing layer: O(1) lookups for edge relations, confidence filtering, and node labels
from __future__ import annotations
import networkx as nx


_CI_PRIORITY = {"EXTRACTED": 0, "INFERRED": 1, "AMBIGUOUS": 2}


def build_edge_index(G: nx.Graph) -> dict[str, list[tuple[str, str, dict]]]:
    """Hash map: relation_type → [(u, v, edge_data), ...]."""
    idx: dict[str, list[tuple[str, str, dict]]] = {}
    for u, v, data in G.edges(data=True):
        rel = data.get("relation", "")
        idx.setdefault(rel, []).append((u, v, dict(data)))
    return idx


def get_edges_by_relation(G: nx.Graph, relation_type: str) -> list[tuple[str, str, dict]]:
    indexes = G.graph.get("indexes", {}) if hasattr(G, "graph") else {}
    edge_idx = indexes.get("edge_relation", {})
    if edge_idx:
        return edge_idx.get(relation_type, [])
    return [(u, v, dict(data)) for u, v, data in G.edges(data=True)
            if data.get("relation") == relation_type]


def get_neighbors_by_relation(G: nx.Graph, node: str, relation_type: str) -> list[str]:
    indexes = G.graph.get("indexes", {}) if hasattr(G, "graph") else {}
    edge_idx = indexes.get("edge_relation", {})
    if edge_idx:
        candidates = edge_idx.get(relation_type, [])
        return [v for u, v, _ in candidates if u == node] + [u for u, v, _ in candidates if v == node]
    result = []
    for neighbor in G.neighbors(node):
        if G.edges[node, neighbor].get("relation") == relation_type:
            result.append(neighbor)
    return result


def build_confidence_bitmap(G: nx.Graph) -> dict[str, list[tuple[str, str]]]:
    bitmap: dict[str, list[tuple[str, str]]] = {"EXTRACTED": [], "INFERRED": [], "AMBIGUOUS": []}
    for u, v, data in G.edges(data=True):
        conf = data.get("confidence", "EXTRACTED")
        bitmap.setdefault(conf, []).append((u, v))
    return bitmap


def filter_edges_by_confidence(
    G: nx.Graph, edges: list[tuple[str, str]], min_confidence: str = "INFERRED"
) -> list[tuple[str, str]]:
    indexes = G.graph.get("indexes", {}) if hasattr(G, "graph") else {}
    bitmap = indexes.get("confidence_bitmap", {})
    min_prio = _CI_PRIORITY.get(min_confidence, 1)
    if bitmap:
        allowed: set[tuple[str, str]] = set()
        for ci, prio in _CI_PRIORITY.items():
            if prio <= min_prio:
                allowed.update(bitmap.get(ci, []))
        return [e for e in edges if e in allowed or (e[1], e[0]) in allowed]
    return [
        e for e in edges
        if _CI_PRIORITY.get(G.edges[e[0], e[1]].get("confidence", "EXTRACTED"), 0) <= min_prio
    ]


def build_label_index(G: nx.Graph) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = {}
    for nid, data in G.nodes(data=True):
        norm = data.get("norm_label") or "".join(
            c for c in (data.get("label") or "").lower() if c.isalnum() or c == " "
        ).strip()
        for length in (3, 2, 1):
            if len(norm) >= length:
                prefix = norm[:length]
                idx.setdefault(prefix, []).append(nid)
    return idx


def lookup_nodes_by_prefix(prefix: str, index: dict[str, list[str]]) -> list[str]:
    return list(dict.fromkeys(index.get(prefix.lower()[:3], [])))


def build_indexes(G: nx.Graph) -> dict:
    return {
        "edge_relation": build_edge_index(G),
        "confidence_bitmap": build_confidence_bitmap(G),
        "label_index": build_label_index(G),
    }
