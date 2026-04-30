"""Method Resolution Order per language — walk class hierarchy to find method definitions."""
from __future__ import annotations

from collections import deque
from enum import Enum


class MROStrategy(Enum):
    FIRST_WINS = "first_wins"
    C3 = "c3"
    RUBY_MIXIN = "ruby_mixin"
    NONE = "none"


MRO_FOR_LANGUAGE: dict[str, MROStrategy] = {
    "python": MROStrategy.C3,
    "typescript": MROStrategy.FIRST_WINS,
    "javascript": MROStrategy.FIRST_WINS,
    "go": MROStrategy.NONE,
    "java": MROStrategy.FIRST_WINS,
    "rust": MROStrategy.NONE,
    "csharp": MROStrategy.FIRST_WINS,
    "cpp": MROStrategy.FIRST_WINS,
}

_RELATION_EXTENDS = frozenset({"extends", "inherits", "implements"})


def get_parent_classes(G, class_node_id: str) -> list[str]:
    parents: list[str] = []
    for neighbor in G.neighbors(class_node_id):
        edge_data = G.edges[class_node_id, neighbor]
        relation = edge_data.get("relation", "")
        if relation not in _RELATION_EXTENDS:
            continue
        src = edge_data.get("_src", edge_data.get("source", ""))
        tgt = edge_data.get("_tgt", edge_data.get("target", ""))
        if src == class_node_id and tgt == neighbor:
            parents.append(neighbor)
    return parents


def build_class_hierarchy(G) -> dict[str, list[str]]:
    hierarchy: dict[str, list[str]] = {}
    for u, v, data in G.edges(data=True):
        relation = data.get("relation", "")
        if relation in _RELATION_EXTENDS:
            src = data.get("_src", data.get("source", u))
            tgt = data.get("_tgt", data.get("target", v))
            if src and tgt:
                hierarchy.setdefault(src, []).append(tgt)
    return hierarchy


def resolve_method_by_mro(
    target_method: str,
    class_node_id: str,
    G,
    language: str,
) -> str | None:
    strategy = MRO_FOR_LANGUAGE.get(language, MROStrategy.NONE)

    if strategy == MROStrategy.NONE:
        if _class_has_method(G, class_node_id, target_method):
            return class_node_id
        return None

    if strategy == MROStrategy.FIRST_WINS:
        return _mro_first_wins(G, class_node_id, target_method)

    if strategy == MROStrategy.C3:
        linearized = _c3_linearize(G, class_node_id, set(), [])
        for cls_id in linearized:
            if _class_has_method(G, cls_id, target_method):
                return cls_id
        return None

    if strategy == MROStrategy.RUBY_MIXIN:
        return _mro_first_wins(G, class_node_id, target_method)

    return None


def _class_has_method(G, class_node_id: str, target_method: str) -> bool:
    if class_node_id not in G:
        return False
    method_label = f".{target_method}()"
    for neighbor in G.neighbors(class_node_id):
        if neighbor.startswith(class_node_id + "_"):
            neighbor_label = G.nodes[neighbor].get("label", "")
            if neighbor_label.lower() == method_label.lower():
                return True
    return False


def _mro_first_wins(G, class_node_id: str, target_method: str) -> str | None:
    if _class_has_method(G, class_node_id, target_method):
        return class_node_id
    queue: deque[str] = deque(get_parent_classes(G, class_node_id))
    seen: set[str] = {class_node_id}
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        if _class_has_method(G, current, target_method):
            return current
        for parent in get_parent_classes(G, current):
            if parent not in seen:
                queue.append(parent)
    return None


def _c3_linearize(G, class_node_id: str, seen: set[str], result: list[str]) -> list[str]:
    if class_node_id in seen:
        return result
    seen.add(class_node_id)
    parents = get_parent_classes(G, class_node_id)
    for parent in parents:
        _c3_linearize(G, parent, seen, result)
    result.append(class_node_id)
    return result
