from __future__ import annotations

from graphify.code_emitter import EdgeEmitter
from graphify.code_schema import EdgeType, ConfidenceTier, CONFIDENCE_VALUES


class TestEdgeEmitterFluentAPI:
    def test_emit_edge(self):
        emitter = EdgeEmitter(source_file="test.py")
        emitter.emit("a", "b", EdgeType.CALLS, line=10, confidence=ConfidenceTier.EXTRACTED)
        assert len(emitter.edges) == 1
        e = emitter.edges[0]
        assert e.source == "a"
        assert e.target == "b"
        assert e.edge_type == EdgeType.CALLS
        assert e.confidence == ConfidenceTier.EXTRACTED
        assert e.source_file == "test.py"

    def test_calls_alias(self):
        emitter = EdgeEmitter()
        emitter.calls("main", "init")
        assert len(emitter.edges) == 1
        assert emitter.edges[0].edge_type == EdgeType.CALLS

    def test_calls_inferred(self):
        emitter = EdgeEmitter()
        emitter.calls_inferred("a", "b", confidence_score=0.7)
        e = emitter.edges[0]
        assert e.confidence == ConfidenceTier.INFERRED
        assert e.confidence_score == 0.7

    def test_inherits(self):
        emitter = EdgeEmitter()
        emitter.inherits("Child", "Parent", line=5)
        e = emitter.edges[0]
        assert e.edge_type == EdgeType.INHERITS
        assert e.source == "Child"
        assert e.target == "Parent"

    def test_implements(self):
        emitter = EdgeEmitter()
        emitter.implements("MyClass", "MyInterface")
        e = emitter.edges[0]
        assert e.edge_type == EdgeType.IMPLEMENTS

    def test_contains(self):
        emitter = EdgeEmitter()
        emitter.contains("File", "Class")
        e = emitter.edges[0]
        assert e.edge_type == EdgeType.CONTAINS

    def test_imports(self):
        emitter = EdgeEmitter()
        emitter.imports("file.ts", "react")
        e = emitter.edges[0]
        assert e.edge_type == EdgeType.IMPORTS

    def test_references(self):
        emitter = EdgeEmitter()
        emitter.references("a", "b", confidence=ConfidenceTier.INFERRED, confidence_score=0.7)
        e = emitter.edges[0]
        assert e.edge_type == EdgeType.REFERENCES
        assert e.confidence == ConfidenceTier.INFERRED

    def test_fluent_chaining(self):
        emitter = EdgeEmitter()
        emitter.calls("a", "b").calls("b", "c").inherits("c", "p")
        assert len(emitter.edges) == 3

    def test_tag_node(self):
        emitter = EdgeEmitter()
        emitter.tag_node("n1", "FUNCTION").tag_node("n2", "CLASS")
        assert emitter.node_types["n1"] == "FUNCTION"
        assert emitter.node_types["n2"] == "CLASS"


class TestAsDictsOutput:
    def test_as_dicts_format(self):
        emitter = EdgeEmitter(source_file="src/a.py")
        emitter.calls("func_a", "func_b", line=42)
        dicts = emitter.as_dicts()
        assert len(dicts) == 1
        d = dicts[0]
        assert d["source"] == "func_a"
        assert d["target"] == "func_b"
        assert d["relation"] == "calls"
        assert d["confidence"] == "EXTRACTED"
        assert d["source_file"] == "src/a.py"
        assert "weight" in d
        assert "confidence_score" in d

    def test_as_dicts_multiple_edges(self):
        emitter = EdgeEmitter()
        emitter.contains("file", "class_a")
        emitter.contains("file", "class_b")
        dicts = emitter.as_dicts()
        assert len(dicts) == 2

    def test_as_dicts_empty(self):
        emitter = EdgeEmitter()
        assert emitter.as_dicts() == []


class TestStats:
    def test_stats_initial(self):
        emitter = EdgeEmitter()
        s = emitter.stats()
        assert s == {"extracted": 0, "inferred": 0, "ambiguous": 0}

    def test_stats_after_emit(self):
        emitter = EdgeEmitter()
        emitter.calls("a", "b", confidence=ConfidenceTier.EXTRACTED)
        emitter.calls_inferred("b", "c")
        emitter.references("c", "d", confidence=ConfidenceTier.AMBIGUOUS, confidence_score=0.2)
        s = emitter.stats()
        assert s["extracted"] == 1
        assert s["inferred"] == 1
        assert s["ambiguous"] == 1

    def test_stats_after_clear(self):
        emitter = EdgeEmitter()
        emitter.calls("a", "b")
        emitter.clear()
        s = emitter.stats()
        assert s == {"extracted": 0, "inferred": 0, "ambiguous": 0}


class TestClear:
    def test_clear_resets_edges(self):
        emitter = EdgeEmitter()
        emitter.calls("a", "b")
        assert len(emitter.edges) == 1
        emitter.clear()
        assert len(emitter.edges) == 0

    def test_clear_resets_node_types(self):
        emitter = EdgeEmitter()
        emitter.tag_node("n1", "FUNCTION")
        emitter.clear()
        assert emitter.node_types == {}

    def test_clear_resets_stats(self):
        emitter = EdgeEmitter()
        emitter.calls("a", "b")
        emitter.clear()
        assert emitter.stats() == {"extracted": 0, "inferred": 0, "ambiguous": 0}

    def test_clear_returns_self(self):
        emitter = EdgeEmitter()
        assert emitter.clear() is emitter


class TestConfidenceTierValues:
    def test_extracted_confidence(self):
        emitter = EdgeEmitter()
        emitter.calls("a", "b", confidence=ConfidenceTier.EXTRACTED)
        d = emitter.as_dicts()[0]
        assert d["confidence"] == "EXTRACTED"
        assert d["confidence_score"] == 1.0

    def test_inferred_confidence(self):
        emitter = EdgeEmitter()
        emitter.calls("a", "b", confidence=ConfidenceTier.INFERRED, confidence_score=0.7)
        d = emitter.as_dicts()[0]
        assert d["confidence"] == "INFERRED"
        assert d["confidence_score"] == 0.7

    def test_ambiguous_confidence(self):
        emitter = EdgeEmitter()
        emitter.calls("a", "b", confidence=ConfidenceTier.AMBIGUOUS, confidence_score=0.3)
        d = emitter.as_dicts()[0]
        assert d["confidence"] == "AMBIGUOUS"
        assert d["confidence_score"] == 0.3

    def test_default_score_when_not_provided(self):
        emitter = EdgeEmitter()
        emitter.calls("a", "b", confidence=ConfidenceTier.INFERRED)
        d = emitter.as_dicts()[0]
        assert d["confidence_score"] == 0.7
