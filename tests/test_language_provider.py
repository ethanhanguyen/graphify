from __future__ import annotations

import pytest
from pathlib import Path

from graphify.language_provider import (
    LanguageCallProvider,
    register_provider,
    get_provider,
    languages_with_providers,
)


class _ConcreteProvider(LanguageCallProvider):
    def import_resolver(self, file_path, import_name, all_files):
        return str(file_path / import_name)

    def call_extractor(self, parsed_ast, source_bytes, config):
        return []

    def receiver_inferrer(self, call_node, enclosing_class, source_bytes):
        return None

    def mro_strategy(self):
        return "c3"

    def import_semantics(self):
        return "named"


def test_cannot_instantiate_directly():
    with pytest.raises(TypeError):
        LanguageCallProvider()  # type: ignore[abstract]


def test_register_and_get_provider():
    provider = _ConcreteProvider()
    register_provider("testlang", provider)
    assert get_provider("testlang") is provider


def test_get_unregistered_returns_none():
    assert get_provider("no_such_language") is None


def test_languages_with_providers():
    provider = _ConcreteProvider()
    register_provider("testlang2", provider)
    langs = languages_with_providers()
    assert "testlang" in langs
    assert "testlang2" in langs


def test_concrete_subclass_import_resolver():
    provider = _ConcreteProvider()
    result = provider.import_resolver(Path("/src"), "Util", {})
    assert result == "/src/Util"


def test_concrete_subclass_call_extractor():
    provider = _ConcreteProvider()
    assert provider.call_extractor(None, b"", None) == []


def test_concrete_subclass_receiver_inferrer():
    provider = _ConcreteProvider()
    assert provider.receiver_inferrer(None, None, b"") is None


def test_concrete_subclass_mro_strategy():
    provider = _ConcreteProvider()
    assert provider.mro_strategy() == "c3"


def test_concrete_subclass_import_semantics():
    provider = _ConcreteProvider()
    assert provider.import_semantics() == "named"
