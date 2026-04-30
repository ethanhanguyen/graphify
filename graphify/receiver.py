"""Receiver inference for self/this/super method calls."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExtractedCallSite:
    name: str
    receiver: str | None = None
    arity: int = 0
    line: int = 0
    in_class: str | None = None
    is_dynamic: bool = False
    full_call_text: str = ""


def infer_receiver(
    call: ExtractedCallSite,
    enclosing_class: str | None,
    graph_nodes: dict[str, dict],
) -> str | None:
    if call.receiver in ("self", "this", "cls"):
        return enclosing_class
    if call.receiver == "super":
        return _find_parent_class(enclosing_class, graph_nodes)
    if call.receiver:
        return call.receiver
    return enclosing_class if call.is_dynamic else None


def _find_parent_class(class_nid: str | None, graph_nodes: dict[str, dict]) -> str | None:
    if not class_nid:
        return None
    class_node = graph_nodes.get(class_nid, {})
    parent_nid = class_node.get("extends")
    if parent_nid and parent_nid in graph_nodes:
        return parent_nid
    return None


def is_constructor_call(name: str, graph_nodes: dict[str, dict]) -> str | None:
    for nid, data in graph_nodes.items():
        label = data.get("label", "")
        node_type = data.get("node_type", "")
        if node_type in ("CLASS", "STRUCT", "INTERFACE"):
            if _matches(label, name):
                return nid
    return None


def _matches(label: str, name: str) -> bool:
    a = label.strip("()").lstrip(".").lower()
    b = name.strip("()").lstrip(".").lower()
    return a == b
