from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

_providers: dict[str, LanguageCallProvider] = {}


class LanguageCallProvider(ABC):
    @abstractmethod
    def import_resolver(self, file_path: Path, import_name: str, all_files: dict[str, list[str]]) -> Optional[str]:
        ...

    @abstractmethod
    def call_extractor(self, parsed_ast, source_bytes: bytes, config) -> list[dict]:
        ...

    @abstractmethod
    def receiver_inferrer(self, call_node, enclosing_class: Optional[str], source_bytes: bytes) -> Optional[str]:
        ...

    @abstractmethod
    def mro_strategy(self) -> str:
        ...

    @abstractmethod
    def import_semantics(self) -> str:
        ...


def register_provider(language: str, provider: LanguageCallProvider) -> None:
    _providers[language] = provider


def get_provider(language: str) -> Optional[LanguageCallProvider]:
    return _providers.get(language)


def languages_with_providers() -> list[str]:
    return list(_providers.keys())
