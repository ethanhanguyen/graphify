"""Typed indexes for fast graph queries.

Builds three index structures on the NetworkX graph:
1. Edge-type index: {edge_type: [(src, tgt), ...]}
2. Node label trie: full-text prefix search on node labels
3. Confidence bitmap: per-edge confidence tiers for filtering

These enable O(1) edge-type lookups, O(k) label prefix searches,
and O(1) confidence-filtered neighbor queries.
"""

from __future__ import annotations

import json
from pathlib import Path
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

    def to_dict(self) -> dict:
        conf_dict = {f"{k[0]}|{k[1]}": v for k, v in self.confidence._conf.items()}
        return {
            "edge_types": self.edge_type.type_counts(),
            "edge_type_keys": self.edge_type.edge_types(),
            "edge_by_type": {k: list(v) for k, v in self.edge_type._by_type.items()},
            "confidence": conf_dict,
            "trie_nodes": self._serialize_trie(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CompositeIndex":
        idx = cls.__new__(cls)
        conf_raw = data.get("confidence", {})
        idx.confidence = ConfidenceBitmap.__new__(ConfidenceBitmap)
        idx.confidence._conf = {
            tuple(k.split("|", 1)): v for k, v in conf_raw.items() if "|" in k
        }
        idx.labels = cls._deserialize_trie(data.get("trie_nodes", {}))
        idx.edge_type = EdgeTypeIndex.__new__(EdgeTypeIndex)
        idx.edge_type._by_type = {
            k: [(t[0], t[1]) if isinstance(t, list) else t for t in v]
            for k, v in data.get("edge_by_type", {}).items()
        }
        idx.edge_type._by_type_undirected = {}
        for rel, pairs in idx.edge_type._by_type.items():
            undirected = set()
            for u, v in pairs:
                undirected.add((u, v) if u <= v else (v, u))
            idx.edge_type._by_type_undirected[rel] = undirected
        return idx

    def _serialize_trie(self) -> dict:
        queue: list[tuple[str, NodeLabelTrie]] = [("", self.labels)]
        result: dict[str, list[str]] = {}
        while queue:
            path, node = queue.pop(0)
            if node._node_ids:
                result[path or "_"] = node._node_ids
            for ch in sorted(node._children):
                queue.append((path + ch, node._children[ch]))
        return result

    @classmethod
    def _deserialize_trie(cls, data: dict) -> NodeLabelTrie:
        trie = NodeLabelTrie.__new__(NodeLabelTrie)
        trie._children = {}
        trie._node_ids = []
        for path, node_ids in data.items():
            if path == "_":
                trie._node_ids = node_ids
                continue
            node = trie
            for ch in path:
                if ch not in node._children:
                    child = NodeLabelTrie.__new__(NodeLabelTrie)
                    child._children = {}
                    child._node_ids = []
                    node._children[ch] = child
                node = node._children[ch]
            node._node_ids = node_ids
        return trie


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


def save_indexes(G: nx.Graph, output_path: str) -> None:
    index = get_index(G) or build_indexes(G)
    p = Path(output_path).with_suffix(".index.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(index.to_dict(), f, separators=(",", ":"))


def load_indexes(path: str) -> CompositeIndex | None:
    p = Path(path).with_suffix(".index.json")
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return CompositeIndex.from_dict(data)


def load_or_build_indexes(G: nx.Graph, graph_path: str) -> CompositeIndex:
    idx = load_indexes(graph_path)
    if idx is None:
        idx = build_indexes(G)
    else:
        G.graph["index"] = idx
    return idx
