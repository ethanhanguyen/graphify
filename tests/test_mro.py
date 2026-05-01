from __future__ import annotations

from graphify.mro import (
    C3Linearization,
    FirstWins,
    NoneMRO,
    build_class_hierarchy,
    get_mro_strategy,
)


class TestC3Linearization:
    def test_simple_case(self):
        mro = C3Linearization()
        hierarchy = {
            "Child": ["Parent"],
            "Parent": [],
            "Child.method": set(),
            "Parent.method": set(),
        }
        result = mro.resolve("method", "Child", hierarchy)
        assert result is not None
        nid, confidence = result
        assert confidence == 1.0
        assert nid == "Child.method"

    def test_diamond_inheritance(self):
        mro = C3Linearization()
        hierarchy = {
            "D": ["B", "C"],
            "B": ["A"],
            "C": ["A"],
            "A": [],
            "A.method": set(),
            "D.method": set(),
        }
        result = mro.resolve("method", "D", hierarchy)
        assert result is not None
        nid, conf = result
        assert conf == 1.0
        assert nid == "D.method"

    def test_no_bases(self):
        mro = C3Linearization()
        hierarchy = {"Solo": []}
        result = mro.resolve("method", "Solo", hierarchy)
        assert result is None

    def test_multi_level(self):
        mro = C3Linearization()
        hierarchy = {
            "C": ["B"],
            "B": ["A"],
            "A": [],
            "A.method": set(),
        }
        result = mro.resolve("method", "C", hierarchy)
        assert result is not None
        nid, conf = result
        assert nid == "A.method"
        assert conf == 0.7

    def test_lowercase_normalization(self):
        mro = C3Linearization()
        hierarchy = {
            "Child": ["Parent"],
            "Parent": [],
            "parent.method": set(),
        }
        result = mro.resolve("method", "Child", hierarchy)
        assert result is not None
        nid, _ = result
        assert nid == "parent.method"


class TestFirstWins:
    def test_first_match_wins(self):
        fw = FirstWins()
        hierarchy = {
            "Child": ["Parent1", "Parent2"],
            "Parent1": [],
            "Parent2": [],
            "parent1.method": set(),
            "parent2.method": set(),
        }
        result = fw.resolve("method", "Child", hierarchy)
        assert result is not None
        nid, _ = result
        assert nid == "parent1.method"

    def test_no_bases_returns_none(self):
        fw = FirstWins()
        hierarchy = {"Lone": []}
        result = fw.resolve("method", "Lone", hierarchy)
        assert result is None

    def test_recursive_fallback(self):
        fw = FirstWins()
        hierarchy = {
            "C": ["B"],
            "B": ["A"],
            "A": [],
            "a.method": set(),
        }
        result = fw.resolve("method", "C", hierarchy)
        assert result is not None
        nid, _ = result
        assert nid == "a.method"


class TestNoneMRO:
    def test_always_returns_none(self):
        nm = NoneMRO()
        hierarchy = {"A": ["B"], "B": []}
        result = nm.resolve("method", "A", hierarchy)
        assert result is None


class TestBuildClassHierarchy:
    def test_extracts_extends_edges(self):
        extractions = [
            {
                "nodes": [
                    {"id": "n_child", "label": "Child", "file_type": "code", "source_file": "a.py"},
                    {"id": "n_parent", "label": "Parent", "file_type": "code", "source_file": "a.py"},
                ],
                "edges": [
                    {"source": "n_child", "target": "n_parent", "relation": "extends",
                     "confidence": "EXTRACTED", "source_file": "a.py", "weight": 1.0},
                ],
            }
        ]
        h = build_class_hierarchy(extractions)
        assert "n_child" in h
        assert "n_parent" in h["n_child"]

    def test_no_extend_edges_returns_nodes(self):
        extractions = [
            {
                "nodes": [
                    {"id": "n_A", "label": "A", "file_type": "code", "source_file": "a.py"},
                ],
                "edges": [],
            }
        ]
        h = build_class_hierarchy(extractions)
        assert "n_A" in h
        assert h["n_A"] == []

    def test_multiple_extractions(self):
        extractions = [
            {"nodes": [{"id": "n_A", "label": "A"}], "edges": []},
            {"nodes": [{"id": "n_B", "label": "B"}], "edges": [
                {"source": "n_B", "target": "n_A", "relation": "inherits",
                 "confidence": "EXTRACTED", "source_file": "b.py", "weight": 1.0}
            ]},
        ]
        h = build_class_hierarchy(extractions)
        assert "n_A" in h["n_B"]


class TestGetMROStrategy:
    def test_python_returns_c3(self):
        assert isinstance(get_mro_strategy("python"), C3Linearization)

    def test_java_returns_first_wins(self):
        assert isinstance(get_mro_strategy("java"), FirstWins)

    def test_javascript_returns_first_wins(self):
        assert isinstance(get_mro_strategy("javascript"), FirstWins)

    def test_typescript_returns_first_wins(self):
        assert isinstance(get_mro_strategy("typescript"), FirstWins)

    def test_go_returns_none_mro(self):
        assert isinstance(get_mro_strategy("go"), NoneMRO)

    def test_ruby_returns_c3(self):
        assert isinstance(get_mro_strategy("ruby"), C3Linearization)

    def test_unknown_language_returns_first_wins(self):
        assert isinstance(get_mro_strategy("haskell"), FirstWins)

    def test_c_returns_none_mro(self):
        assert isinstance(get_mro_strategy("c"), NoneMRO)

    def test_rust_returns_none_mro(self):
        assert isinstance(get_mro_strategy("rust"), NoneMRO)

    def test_dart_returns_first_wins(self):
        assert isinstance(get_mro_strategy("dart"), FirstWins)
