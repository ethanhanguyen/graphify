from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class MROStrategy(ABC):
    @abstractmethod
    def resolve(
        self, method_name: str, class_name: str, class_hierarchy: dict[str, list[str]]
    ) -> Optional[tuple[str, float]]:
        ...


class C3Linearization(MROStrategy):
    def resolve(
        self, method_name: str, class_name: str, class_hierarchy: dict[str, list[str]]
    ) -> Optional[tuple[str, float]]:
        linearization = self._c3_linearize(class_name, class_hierarchy)
        if not linearization:
            return None
        for cls_name in linearization:
            cls_key = cls_name.lower()
            nid_candidates = [
                f"{cls_name}.{method_name}",
                f"{cls_key}.{method_name}",
            ]
            for nid in nid_candidates:
                if nid in class_hierarchy:
                    confidence = 1.0 if cls_name.lower() == class_name.lower() else 0.7
                    return (nid, confidence)
        return None

    def _c3_linearize(self, class_name: str, class_hierarchy: dict[str, list[str]]) -> list[str]:
        bases = class_hierarchy.get(class_name, [])
        if not bases:
            return [class_name]
        linearizations = [self._c3_linearize(b, class_hierarchy) for b in bases]
        result: list[str] = [class_name]
        while True:
            candidates: list[str] = []
            for lin in linearizations:
                if lin:
                    head = lin[0]
                    if all(head not in other[1:] for other in linearizations if head not in other):
                        candidates.append(head)
                        break
            if not candidates:
                for lin in linearizations:
                    if lin:
                        result.extend(lin)
                break
            head = candidates[0]
            if head not in result:
                result.append(head)
            for lin in linearizations:
                if lin and lin[0] == head:
                    lin.pop(0)
        return result


class FirstWins(MROStrategy):
    def resolve(
        self, method_name: str, class_name: str, class_hierarchy: dict[str, list[str]]
    ) -> Optional[tuple[str, float]]:
        bases = class_hierarchy.get(class_name, [])
        if not bases:
            return None
        for base in bases:
            base_key = base.lower()
            nid = f"{base_key}.{method_name}"
            if nid in class_hierarchy:
                return (nid, 0.8)
        for base in bases:
            result = self.resolve(method_name, base, class_hierarchy)
            if result:
                return result
        return None


class NoneMRO(MROStrategy):
    def resolve(
        self, method_name: str, class_name: str, class_hierarchy: dict[str, list[str]]
    ) -> Optional[tuple[str, float]]:
        return None


def build_class_hierarchy(extraction_results: list[dict]) -> dict[str, list[str]]:
    hierarchy: dict[str, list[str]] = {}
    for result in extraction_results:
        for edge in result.get("edges", []):
            if edge.get("relation") in ("extends", "inherits", "implements"):
                child = edge.get("source", "")
                parent = edge.get("target", "")
                if child and parent:
                    hierarchy.setdefault(child, []).append(parent)
        for node in result.get("nodes", []):
            nid = node.get("id", "")
            if nid not in hierarchy:
                hierarchy.setdefault(nid, [])
    return hierarchy


_MRO_MAP: dict[str, MROStrategy] = {
    "python": C3Linearization(),
    "java": FirstWins(),
    "javascript": FirstWins(),
    "typescript": FirstWins(),
    "go": NoneMRO(),
    "csharp": FirstWins(),
    "ruby": C3Linearization(),
    "c": NoneMRO(),
    "cpp": C3Linearization(),
    "rust": NoneMRO(),
    "kotlin": FirstWins(),
    "scala": FirstWins(),
    "php": FirstWins(),
    "swift": FirstWins(),
    "lua": NoneMRO(),
    "dart": FirstWins(),
    "elixir": NoneMRO(),
    "zig": NoneMRO(),
}


def get_mro_strategy(language: str) -> MROStrategy:
    return _MRO_MAP.get(language, FirstWins())
