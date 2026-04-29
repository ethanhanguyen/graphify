"""Tests for graphify/code_emitter.py -- typed node/edge emission and inference."""
from graphify.code_emitter import (
    emit_edge,
    emit_node,
    extractor_to_typed,
    infer_node_type_from_extraction,
)
from graphify.code_schema import EdgeType, NodeType, TypedEdge, TypedNode


class TestEmitNode:
    def test_returns_compatible_dict(self):
        node = TypedNode(id="n1", label="foo()", node_type=NodeType.FUNCTION)
        d = emit_node(node)
        assert d["id"] == "n1"
        assert d["node_type"] == "FUNCTION"
        assert d["file_type"] == "code"


class TestEmitEdge:
    def test_returns_compatible_dict(self):
        edge = TypedEdge(source="a", target="b", edge_type=EdgeType.CALLS)
        d = emit_edge(edge)
        assert d["source"] == "a"
        assert d["target"] == "b"
        assert d["relation"] == "calls"


class TestInferNodeType:
    def test_infer_function(self):
        node = {"label": "myFunc()", "file_type": "code", "id": "mod_myfunc"}
        assert infer_node_type_from_extraction(node) == NodeType.FUNCTION

    def test_infer_method(self):
        node = {"label": ".myMethod()", "file_type": "code", "id": "cls_mymethod"}
        assert infer_node_type_from_extraction(node) == NodeType.METHOD

    def test_infer_class(self):
        node = {"label": "MyClass", "file_type": "code", "id": "mod_myclass"}
        assert infer_node_type_from_extraction(node) == NodeType.CLASS

    def test_infer_concept(self):
        node = {"label": "Design Doc", "file_type": "document", "id": "doc_design"}
        assert infer_node_type_from_extraction(node) == NodeType.CONCEPT

    def test_infer_unknown_empty_label(self):
        node = {"label": "", "file_type": "code", "id": "mod_empty"}
        assert infer_node_type_from_extraction(node) == NodeType.UNKNOWN

    def test_infer_unknown_no_label(self):
        node = {"file_type": "code", "id": "mod_nolabel"}
        assert infer_node_type_from_extraction(node) == NodeType.UNKNOWN

    def test_infer_unknown_lowercase_no_paren(self):
        node = {"label": "myVariable", "file_type": "code", "id": "mod_var"}
        assert infer_node_type_from_extraction(node) == NodeType.UNKNOWN


class TestExtractorToTyped:
    def test_roundtrip_node_only(self):
        node = {
            "id": "a",
            "label": "func()",
            "file_type": "code",
            "source_file": "x.py",
        }
        typed_node, typed_edge = extractor_to_typed(node)
        assert typed_node.node_type == NodeType.FUNCTION
        assert typed_node.id == "a"
        assert typed_node.label == "func()"
        assert typed_node.language == "python"
        assert typed_edge is None

    def test_roundtrip_with_edge(self):
        node = {
            "id": "a",
            "label": "func()",
            "file_type": "code",
            "source_file": "x.py",
        }
        edge = {
            "source": "a",
            "target": "b",
            "relation": "calls",
            "confidence": "EXTRACTED",
        }
        typed_node, typed_edge = extractor_to_typed(node, edge)
        assert typed_node.node_type == NodeType.FUNCTION
        assert typed_edge is not None
        assert typed_edge.edge_type == EdgeType.CALLS
        assert typed_edge.confidence_score == 1.0

    def test_roundtrip_inferred_edge(self):
        node = {"id": "b", "label": "MyClass", "file_type": "code"}
        edge = {
            "source": "b",
            "target": "c",
            "relation": "imports",
            "confidence": "INFERRED",
        }
        typed_node, typed_edge = extractor_to_typed(node, edge)
        assert typed_node.node_type == NodeType.CLASS
        assert typed_edge.edge_type == EdgeType.IMPORTS
        assert typed_edge.confidence_score == 0.5

    def test_roundtrip_unknown_relation(self):
        node = {"id": "x", "label": "X", "file_type": "code"}
        edge = {"source": "x", "target": "y", "relation": "custom_rel"}
        _, typed_edge = extractor_to_typed(node, edge)
        assert typed_edge.edge_type == EdgeType.RELATES_TO
