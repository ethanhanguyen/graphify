"""Confidence-tiered edge emission for code extractors.

Edge emitter provides a fluent interface for extractors to emit
typed edges with confidence tiers. Supports:
- EXTRACTED: from tree-sitter AST (1.0)
- INFERRED: from cross-file resolution (0.5-0.9)
- AMBIGUOUS: low-certainty matches (0.1-0.4)
"""

from __future__ import annotations

from graphify.code_schema import (
    TypedEdge,
    TypedNode,
    NodeType,
    EdgeType,
    ConfidenceTier,
    CONFIDENCE_VALUES,
)


class EdgeEmitter:
    def __init__(self, source_file: str = ""):
        self.source_file = source_file
        self.edges: list[TypedEdge] = []
        self.node_types: dict[str, NodeType] = {}
        self._stats = {"extracted": 0, "inferred": 0, "ambiguous": 0}

    def emit(
        self,
        source: str,
        target: str,
        edge_type: EdgeType,
        line: int = 0,
        confidence: ConfidenceTier = ConfidenceTier.EXTRACTED,
        confidence_score: float | None = None,
        weight: float = 1.0,
    ) -> EdgeEmitter:
        if confidence_score is None:
            confidence_score = CONFIDENCE_VALUES[confidence]
        self.edges.append(TypedEdge(
            source=source,
            target=target,
            edge_type=edge_type,
            source_file=self.source_file,
            source_location=f"L{line}" if line else "",
            confidence=confidence,
            confidence_score=confidence_score,
            weight=weight,
        ))
        self._stats[confidence.value.lower()] += 1
        return self

    def tag_node(self, node_id: str, node_type: NodeType) -> EdgeEmitter:
        self.node_types[node_id] = node_type
        return self

    def calls(self, caller: str, callee: str, line: int = 0,
              confidence: ConfidenceTier = ConfidenceTier.EXTRACTED,
              confidence_score: float | None = None) -> EdgeEmitter:
        return self.emit(caller, callee, EdgeType.CALLS, line, confidence, confidence_score)

    def calls_inferred(self, caller: str, callee: str, line: int = 0,
                       confidence_score: float = 0.7) -> EdgeEmitter:
        return self.emit(caller, callee, EdgeType.CALLS, line,
                         ConfidenceTier.INFERRED, confidence_score)

    def inherits(self, child: str, parent: str, line: int = 0) -> EdgeEmitter:
        return self.emit(child, parent, EdgeType.INHERITS, line)

    def implements(self, cls: str, iface: str, line: int = 0) -> EdgeEmitter:
        return self.emit(cls, iface, EdgeType.IMPLEMENTS, line)

    def contains(self, container: str, child: str, line: int = 0) -> EdgeEmitter:
        return self.emit(container, child, EdgeType.CONTAINS, line)

    def imports(self, file_id: str, module: str, line: int = 0) -> EdgeEmitter:
        return self.emit(file_id, module, EdgeType.IMPORTS, line)

    def references(self, src: str, tgt: str, line: int = 0,
                   confidence: ConfidenceTier = ConfidenceTier.INFERRED,
                   confidence_score: float = 0.7) -> EdgeEmitter:
        return self.emit(src, tgt, EdgeType.REFERENCES, line,
                         confidence, confidence_score)

    def as_dicts(self) -> list[dict]:
        return [
            {
                "source": e.source,
                "target": e.target,
                "relation": e.edge_type.value,
                "confidence": e.confidence.value,
                "confidence_score": e.confidence_score,
                "source_file": e.source_file,
                "source_location": e.source_location,
                "weight": e.weight,
            }
            for e in self.edges
        ]

    def stats(self) -> dict:
        return dict(self._stats)

    def clear(self) -> EdgeEmitter:
        self.edges.clear()
        self.node_types.clear()
        self._stats = {"extracted": 0, "inferred": 0, "ambiguous": 0}
        return self
