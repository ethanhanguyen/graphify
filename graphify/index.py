"""Typed indexes for fast graph queries.

Builds three index structures on the NetworkX graph:
1. Edge-type index: {edge_type: [(src, tgt), ...]}
2. Node label trie: full-text prefix search on node labels
3. Confidence bitmap: per-edge confidence tiers for filtering

These enable O(1) edge-type lookups, O(k) label prefix searches,
and O(1) confidence-filtered neighbor queries.
"""

from __future__ import annotations

import networkx as nx
from graphify.code_schema import (
    NodeType,
    EdgeType,
    ConfidenceTier,
    CONFIDENCE_PRIORITY,
    SCHEMA_VERSION,
)


class EdgeTypeIndex:
    """O(1) lookup: find all edges of a given type."""

    def __init__(self, G: nx.Graph):
        self._by_type: dict[str, list[tuple[str, str]]] = {}
        self._by_type_undirected: dict[str, set[tuple[str, str]]] = {}
        for u, v, d in G.edges(data=True):
            rel = d.get("relation", "")
            if rel:
                self._by_type.setdefault(rel, []).append((u, v))
                key = (u, v) if u <= v else (v, u)
                self._by_type_undirected.setdefault(rel, set()).add(key)

    def edges(self, edge_type: str) -> list[tuple[str, str]]:
        return self._by_type.get(edge_type, [])

    def count(self, edge_type: str) -> int:
        return len(self._by_type.get(edge_type, []))

    def undirected_pairs(self, edge_type: str) -> set[tuple[str, str]]:
        return self._by_type_undirected.get(edge_type, set())

    def edge_types(self) -> list[str]:
        return list(self._by_type.keys())

    def type_counts(self) -> dict[str, int]:
        return {k: len(v) for k, v in self._by_type.items()}


class NodeLabelTrie:
    """Prefix-searchable index over node labels (case-insensitive)."""

    def __init__(self, G: nx.Graph):
        self._children: dict[str, NodeLabelTrie] = {}
        self._node_ids: list[str] = []
        for nid, d in G.nodes(data=True):
            label = (d.get("label") or nid).lower()
            self._insert(label, nid)

    def _insert(self, label: str, node_id: str) -> None:
        node = self
        for ch in label:
            if ch not in node._children:
                node._children[ch] = NodeLabelTrie.__new__(NodeLabelTrie)
                node._children[ch]._children = {}
                node._children[ch]._node_ids = []
            node = node._children[ch]
        node._node_ids.append(node_id)

    def search(self, prefix: str, limit: int = 50) -> list[str]:
        prefix = prefix.lower()
        node = self
        for ch in prefix:
            if ch not in node._children:
                return []
            node = node._children[ch]
        return self._collect(node, limit)

    def _collect(self, node: NodeLabelTrie, limit: int) -> list[str]:
        result = list(node._node_ids)
        for child in sorted(node._children.values(), key=lambda c: len(c._node_ids), reverse=True):
            if len(result) >= limit:
                break
            result.extend(self._collect(child, limit - len(result)))
        return result[:limit]


class ConfidenceBitmap:
    """Fast edge confidence filtering. Maps (src, tgt) → ConfidenceTier."""

    def __init__(self, G: nx.Graph):
        self._conf: dict[tuple[str, str], int] = {}
        for u, v, d in G.edges(data=True):
            conf = d.get("confidence", "EXTRACTED")
            tier = CONFIDENCE_PRIORITY.get(conf, 0)
            if isinstance(G, nx.MultiGraph):
                for k in d:
                    if u != k and v != k:
                        self._conf[(u, v)] = min(self._conf.get((u, v), 99), tier)
            else:
                self._conf[(u, v)] = tier

    def tier(self, u: str, v: str) -> int:
        key = (u, v) if (u, v) in self._conf else (v, u)
        return self._conf.get(key, 99)

    def filter_neighbors(self, G: nx.Graph, node_id: str, min_tier: int = 0) -> list[str]:
        """Return neighbors of node_id whose connecting edge meets min_tier."""
        result = []
        for nb in G.neighbors(node_id):
            if self.tier(node_id, nb) <= min_tier:
                result.append(nb)
        return result

    def is_extracted(self, u: str, v: str) -> bool:
        return self.tier(u, v) == 0


class CompositeIndex:
    """Combined typed edge + confidence + label lookup."""

    def __init__(self, G: nx.Graph):
        self.edge_type = EdgeTypeIndex(G)
        self.labels = NodeLabelTrie(G)
        self.confidence = ConfidenceBitmap(G)

    def query(self, edge_type: str, min_tier: int = 0,
              label_prefix: str = "") -> list[str]:
        edges = self.edge_type.edges(edge_type)
        result: list[str] = []
        for u, v in edges:
            if self.confidence.tier(u, v) <= min_tier:
                result.append(u)
                result.append(v)
        if label_prefix:
            match_ids = set(self.labels.search(label_prefix))
            result = [n for n in result if n in match_ids]
        return list(set(result))


def build_indexes(G: nx.Graph) -> CompositeIndex:
    """Build all indexes on a graph. Attaches index to G.graph dict."""
    index = CompositeIndex(G)
    G.graph["index"] = index
    G.graph["schema_version"] = SCHEMA_VERSION
    return index


def has_index(G: nx.Graph) -> bool:
    return G.graph.get("schema_version") == SCHEMA_VERSION and "index" in G.graph


def get_index(G: nx.Graph) -> CompositeIndex | None:
    return G.graph.get("index") if has_index(G) else None
