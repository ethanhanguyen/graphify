"""Tests for graphify.mro — Method Resolution Order across languages."""
from __future__ import annotations

import pytest

from graphify.mro import (
    MROStrategy,
    MRO_FOR_LANGUAGE,
    get_parent_classes,
    build_class_hierarchy,
    resolve_method_by_mro,
    _class_has_method,
    _mro_first_wins,
    _c3_linearize,
)
from graphify.build import build_from_json


def _make_test_graph():
    extraction = {
        "nodes": [
            {"id": "animal", "label": "Animal", "node_type": "CLASS", "source_file": "test.py"},
            {"id": "animal_speak", "label": ".speak()", "node_type": "METHOD", "source_file": "test.py"},
            {"id": "mammal", "label": "Mammal", "node_type": "CLASS", "source_file": "test.py"},
            {"id": "dog", "label": "Dog", "node_type": "CLASS", "source_file": "test.py"},
            {"id": "dog_bark", "label": ".bark()", "node_type": "METHOD", "source_file": "test.py"},
            {"id": "cat", "label": "Cat", "node_type": "CLASS", "source_file": "test.py"},
            {"id": "cat_meow", "label": ".meow()", "node_type": "METHOD", "source_file": "test.py"},
        ],
        "edges": [
            {"source": "mammal", "target": "animal", "relation": "extends", "confidence": "EXTRACTED"},
            {"source": "dog", "target": "mammal", "relation": "extends", "confidence": "EXTRACTED"},
            {"source": "cat", "target": "animal", "relation": "extends", "confidence": "EXTRACTED"},
            {"source": "animal", "target": "animal_speak", "relation": "method", "confidence": "EXTRACTED"},
            {"source": "dog", "target": "dog_bark", "relation": "method", "confidence": "EXTRACTED"},
            {"source": "cat", "target": "cat_meow", "relation": "method", "confidence": "EXTRACTED"},
        ],
    }
    return build_from_json(extraction)


class TestMROStrategyEnum:
    def test_enum_values(self):
        assert MROStrategy.FIRST_WINS.value == "first_wins"
        assert MROStrategy.C3.value == "c3"
        assert MROStrategy.RUBY_MIXIN.value == "ruby_mixin"
        assert MROStrategy.NONE.value == "none"


class TestMROForLanguage:
    def test_mro_for_language_map(self):
        assert MRO_FOR_LANGUAGE["python"] == MROStrategy.C3
        assert MRO_FOR_LANGUAGE["typescript"] == MROStrategy.FIRST_WINS
        assert MRO_FOR_LANGUAGE["javascript"] == MROStrategy.FIRST_WINS
        assert MRO_FOR_LANGUAGE["go"] == MROStrategy.NONE
        assert MRO_FOR_LANGUAGE["java"] == MROStrategy.FIRST_WINS
        assert MRO_FOR_LANGUAGE["rust"] == MROStrategy.NONE
        assert MRO_FOR_LANGUAGE["cpp"] == MROStrategy.FIRST_WINS


class TestGetParentClasses:
    def test_get_parent_classes(self):
        G = _make_test_graph()
        parents = get_parent_classes(G, "mammal")
        assert "animal" in parents

    def test_get_parent_classes_no_parents(self):
        G = _make_test_graph()
        parents = get_parent_classes(G, "animal")
        assert parents == []


class TestClassHasMethod:
    def test_class_has_method_found(self):
        G = _make_test_graph()
        assert _class_has_method(G, "animal", "speak") is True

    def test_class_has_method_not_found(self):
        G = _make_test_graph()
        assert _class_has_method(G, "animal", "bark") is False

    def test_class_has_method_missing_class(self):
        G = _make_test_graph()
        assert _class_has_method(G, "nonexistent", "foo") is False


class TestMROFirstWins:
    def test_mro_first_wins(self):
        G = _make_test_graph()
        result = _mro_first_wins(G, "mammal", "speak")
        assert result == "animal"

    def test_mro_first_wins_own_method(self):
        G = _make_test_graph()
        result = _mro_first_wins(G, "animal", "speak")
        assert result == "animal"

    def test_mro_first_wins_not_found(self):
        G = _make_test_graph()
        result = _mro_first_wins(G, "cat", "bark")
        assert result is None


class TestC3Linearize:
    def test_mro_c3_simple(self):
        G = _make_test_graph()
        result = _c3_linearize(G, "dog", set(), [])
        assert "animal" in result
        assert "mammal" in result
        assert "dog" in result


class TestResolveMethodByMRO:
    def test_resolve_method_by_mro_first_wins(self):
        G = _make_test_graph()
        result = resolve_method_by_mro("speak", "dog", G, "java")
        assert result == "animal"

    def test_resolve_method_by_mro_c3(self):
        G = _make_test_graph()
        result = resolve_method_by_mro("speak", "mammal", G, "python")
        assert result == "animal"

    def test_mro_no_inheritance(self):
        G = _make_test_graph()
        result = resolve_method_by_mro("foo", "animal", G, "go")
        assert result is None

    def test_resolve_method_inherited(self):
        G = _make_test_graph()
        result = resolve_method_by_mro("speak", "dog", G, "typescript")
        assert result == "animal"

    def test_resolve_method_unknown_language(self):
        G = _make_test_graph()
        result = resolve_method_by_mro("speak", "animal", G, "ruby")
        assert result == "animal"


class TestBuildClassHierarchy:
    def test_build_class_hierarchy(self):
        G = _make_test_graph()
        h = build_class_hierarchy(G)
        assert "mammal" in h
        assert "animal" in h["mammal"]
        assert "dog" in h
