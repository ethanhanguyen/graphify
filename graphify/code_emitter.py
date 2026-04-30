"""Unified edge emission with confidence tiers and backward-compatible type inference."""
from __future__ import annotations

from pathlib import Path

from .code_schema import (
    EXTENSION_LANGUAGE_MAP,
    RELATION_MAP,
    EdgeType,
    NodeType,
    TypedEdge,
    TypedNode,
)

__all__ = [
    "emit_node",
    "emit_edge",
    "infer_node_type_from_extraction",
    "extractor_to_typed",
]

CONFIDENCE_SCORES: dict[str, float] = {
    "EXTRACTED": 1.0,
    "INFERRED": 0.5,
    "AMBIGUOUS": 0.2,
}


def emit_node(node: TypedNode) -> dict:
    return node.to_dict()


def emit_edge(edge: TypedEdge) -> dict:
    return edge.to_dict()


def infer_node_type_from_extraction(extraction_node: dict, file_path: str = "") -> NodeType:
    label = extraction_node.get("label", "")
    file_type = extraction_node.get("file_type", "")

    if file_type != "code":
        return NodeType.CONCEPT

    if not label:
        return NodeType.UNKNOWN

    if label.endswith("()"):
        if label.startswith("."):
            return NodeType.METHOD
        return NodeType.FUNCTION

    if label[0].isupper():
        return NodeType.CLASS

    return NodeType.UNKNOWN


def extractor_to_typed(
    extraction_node: dict, extraction_edge: dict | None = None
) -> tuple[TypedNode, TypedEdge | None]:
    node_type = infer_node_type_from_extraction(extraction_node)
    typed_node = TypedNode(
        id=extraction_node.get("id", ""),
        label=extraction_node.get("label", ""),
        node_type=node_type,
        source_file=extraction_node.get("source_file", ""),
        source_location=extraction_node.get("source_location", ""),
        language=EXTENSION_LANGUAGE_MAP.get(
            Path(extraction_node.get("source_file", "")).suffix, ""
        ),
    )

    typed_edge = None
    if extraction_edge:
        relation = extraction_edge.get("relation", "relates_to")
        edge_type = RELATION_MAP.get(relation, EdgeType.RELATES_TO)
        typed_edge = TypedEdge(
            source=extraction_edge.get("source", ""),
            target=extraction_edge.get("target", ""),
            edge_type=edge_type,
            confidence=extraction_edge.get("confidence", "EXTRACTED"),
            confidence_score=CONFIDENCE_SCORES.get(
                extraction_edge.get("confidence", "EXTRACTED"), 1.0
            ),
            source_file=extraction_edge.get("source_file", ""),
            source_location=extraction_edge.get("source_location", ""),
            weight=extraction_edge.get("weight", 1.0),
        )

    return typed_node, typed_edge
