"""Tests for graphify/code_schema.py -- typed code schema enums and dataclasses."""
from graphify.code_schema import (
    EXTENSION_LANGUAGE_MAP,
    RELATION_MAP,
    EdgeType,
    NodeType,
    TypedEdge,
    TypedNode,
)


class TestNodeType:
    def test_enum_values_exist(self):
        assert NodeType.FUNCTION.name == "FUNCTION"
        assert NodeType.CLASS.name == "CLASS"
        assert NodeType.METHOD.name == "METHOD"
        assert NodeType.INTERFACE.name == "INTERFACE"
        assert NodeType.ENUM.name == "ENUM"
        assert NodeType.CONCEPT.name == "CONCEPT"
        assert NodeType.UNKNOWN.name == "UNKNOWN"

    def test_enum_count_is_17(self):
        assert len(NodeType) == 17


class TestEdgeType:
    def test_enum_values_exist(self):
        assert EdgeType.CALLS.name == "CALLS"
        assert EdgeType.IMPORTS.name == "IMPORTS"
        assert EdgeType.CONTAINS.name == "CONTAINS"
        assert EdgeType.RELATES_TO.name == "RELATES_TO"

    def test_enum_count_is_20(self):
        assert len(EdgeType) == 20


class TestRelationMap:
    def test_covers_common_relations(self):
        assert "calls" in RELATION_MAP
        assert "imports" in RELATION_MAP
        assert "contains" in RELATION_MAP
        assert "uses" in RELATION_MAP
        assert "references" in RELATION_MAP

    def test_maps_to_correct_enum(self):
        assert RELATION_MAP["calls"] == EdgeType.CALLS
        assert RELATION_MAP["imports"] == EdgeType.IMPORTS
        assert RELATION_MAP["contains"] == EdgeType.CONTAINS

    def test_count_19_mapped_relations(self):
        assert len(RELATION_MAP) == 19


class TestTypedNode:
    def test_to_dict_minimal(self):
        node = TypedNode(id="n1", label="foo", node_type=NodeType.FUNCTION)
        d = node.to_dict()
        assert d["id"] == "n1"
        assert d["label"] == "foo"
        assert d["node_type"] == "FUNCTION"
        assert d["file_type"] == "code"

    def test_to_dict_full(self):
        node = TypedNode(
            id="n1",
            label="myFunc",
            node_type=NodeType.FUNCTION,
            source_file="src/main.py",
            source_location="L42",
            language="python",
            signature="def myFunc(x: int)",
            docstring="Does things.",
            visibility="private",
            is_exported=True,
            community=3,
        )
        d = node.to_dict()
        assert d["language"] == "python"
        assert d["signature"] == "def myFunc(x: int)"
        assert d["docstring"] == "Does things."
        assert d["visibility"] == "private"
        assert d["is_exported"] is True
        assert d["community"] == 3

    def test_to_dict_defaults_omitted(self):
        node = TypedNode(id="n1", label="foo", node_type=NodeType.FUNCTION)
        d = node.to_dict()
        assert "visibility" not in d
        assert "is_exported" not in d
        assert "community" not in d


class TestTypedEdge:
    def test_to_dict(self):
        edge = TypedEdge(
            source="a",
            target="b",
            edge_type=EdgeType.CALLS,
            confidence="EXTRACTED",
            confidence_score=1.0,
        )
        d = edge.to_dict()
        assert d["source"] == "a"
        assert d["target"] == "b"
        assert d["relation"] == "calls"
        assert d["confidence"] == "EXTRACTED"
        assert d["confidence_score"] == 1.0

    def test_to_dict_inferred(self):
        edge = TypedEdge(
            source="x",
            target="y",
            edge_type=EdgeType.IMPORTS,
            confidence="INFERRED",
            confidence_score=0.5,
        )
        d = edge.to_dict()
        assert d["relation"] == "imports"
        assert d["confidence_score"] == 0.5


class TestExtensionLanguageMap:
    def test_common_extensions(self):
        assert EXTENSION_LANGUAGE_MAP[".py"] == "python"
        assert EXTENSION_LANGUAGE_MAP[".ts"] == "typescript"
        assert EXTENSION_LANGUAGE_MAP[".tsx"] == "typescript"
        assert EXTENSION_LANGUAGE_MAP[".go"] == "go"
        assert EXTENSION_LANGUAGE_MAP[".java"] == "java"
        assert EXTENSION_LANGUAGE_MAP[".rs"] == "rust"
