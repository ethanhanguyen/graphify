"""Import resolution — resolve import statements to target files/symbols across languages."""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ImportSemantics(Enum):
    NAMED = "named"
    WILDCARD_LEAF = "wildcard_leaf"
    WILDCARD_TRANSITIVE = "wildcard_transitive"
    NAMESPACE = "namespace"


@dataclass
class ImportTarget:
    module_path: str
    symbol: str | None = None
    is_external: bool = False
    confidence: str = "EXTRACTED"


def resolve_import(
    target: str,
    from_file: Path,
    all_files: list[Path],
    semantics: ImportSemantics,
    language: str,
) -> ImportTarget | None:
    if language == "python":
        return _resolve_python_import(target, from_file, all_files, semantics)
    elif language in ("typescript", "javascript"):
        return _resolve_typescript_import(target, from_file, all_files, semantics)
    elif language == "go":
        return _resolve_go_import(target, from_file, all_files, semantics)
    elif language == "java":
        return _resolve_java_import(target, from_file, all_files, semantics)
    return None


def _file_matches(target: str, candidate: Path, suffixes: tuple[str, ...]) -> bool:
    for suffix in suffixes:
        test_path = candidate.with_suffix(suffix)
        if test_path.exists():
            return True
    return candidate.with_suffix(suffixes[0]).exists() if candidate.suffix else False


def _resolve_python_import(
    target: str,
    from_file: Path,
    all_files: list[Path],
    semantics: ImportSemantics,
) -> ImportTarget | None:
    file_set = {str(f) for f in all_files}
    from_dir = from_file.parent

    if semantics == ImportSemantics.NAMESPACE:
        parts = target.lstrip(".").split(".")
        if target.startswith("."):
            dots = len(target) - len(target.lstrip("."))
            base = from_dir
            for _ in range(dots - 1):
                base = base.parent
            target_path = base / "/".join(parts) if parts else base
            candidate = target_path / "__init__.py"
            if str(candidate) in file_set:
                return ImportTarget(module_path=str(candidate), is_external=False)
            candidate = target_path.with_suffix(".py")
            if str(candidate) in file_set:
                return ImportTarget(module_path=str(candidate), is_external=False)
            return None

        path_str = "/".join(parts) + ".py"
        for f in all_files:
            if str(f).endswith(path_str) or str(f).endswith("/".join(parts) + "/__init__.py"):
                return ImportTarget(module_path=str(f), is_external=False)
        return ImportTarget(module_path=".".join(parts), is_external=True)

    elif semantics == ImportSemantics.NAMED:
        parts = target.lstrip(".").split(".")
        symbol = parts[-1] if parts else target
        module = ".".join(parts[:-1]) if len(parts) > 1 else ""

        if target.startswith("."):
            dots = len(target) - len(target.lstrip("."))
            base = from_dir
            for _ in range(dots - 1):
                base = base.parent
            if module:
                rel_path = base / "/".join(module.split(".")) / "__init__.py"
            else:
                rel_path = base
            candidate = rel_path
            if str(candidate) in file_set:
                return ImportTarget(module_path=str(candidate), symbol=symbol, is_external=False)
            candidate = rel_path.with_suffix(".py") if rel_path.is_dir() or not rel_path.suffix else rel_path
            if str(candidate) in file_set:
                return ImportTarget(module_path=str(candidate), symbol=symbol, is_external=False)
            candidate = rel_path.with_name("__init__.py") if rel_path.is_dir() else rel_path
            return ImportTarget(module_path=str(candidate), is_external=True)

        path_str = "/".join(module.split(".")) + ".py" if module else ""
        for f in all_files:
            if path_str and str(f).endswith(path_str):
                return ImportTarget(module_path=str(f), symbol=symbol, is_external=False)
            if not module and str(f).endswith("__init__.py"):
                parent_dir = str(from_dir)
                parent_parts = parent_dir.rstrip("/").split("/")
                f_parts = str(f).rstrip("/").split("/")
                if f_parts[:-1] == parent_parts:
                    return ImportTarget(module_path=str(f), symbol=symbol, is_external=False)
        return ImportTarget(module_path=".".join(parts), is_external=True)

    else:
        parts = target.lstrip(".").split(".")
        if target.startswith("."):
            dots = len(target) - len(target.lstrip("."))
            base = from_dir
            for _ in range(dots - 1):
                base = base.parent
            target_path = base / "/".join(parts) if parts else base
            candidate = target_path / "__init__.py"
            if str(candidate) in file_set:
                return ImportTarget(module_path=str(candidate), is_external=False)
            candidate = target_path.with_suffix(".py")
            if str(candidate) in file_set:
                return ImportTarget(module_path=str(candidate), is_external=False)
            return None

        path_str = "/".join(parts) + ".py"
        for f in all_files:
            if str(f).endswith(path_str):
                return ImportTarget(module_path=str(f), is_external=False)
        return ImportTarget(module_path=".".join(parts), is_external=True)


def _resolve_typescript_import(
    target: str,
    from_file: Path,
    all_files: list[Path],
    semantics: ImportSemantics,
) -> ImportTarget | None:
    file_set = {str(f) for f in all_files}
    from_dir = from_file.parent

    if semantics == ImportSemantics.NAMESPACE:
        if target.startswith("."):
            resolved = os.path.normpath(from_dir / target)
            for suffix in (".ts", ".tsx", ".js", ".jsx"):
                candidate = Path(resolved + suffix)
                if str(candidate) in file_set:
                    return ImportTarget(module_path=str(candidate), is_external=False)
            candidate = Path(resolved) / "index.ts"
            if str(candidate) in file_set:
                return ImportTarget(module_path=str(candidate), is_external=False)
            return ImportTarget(module_path=target, is_external=True)
        return ImportTarget(module_path=target, is_external=True)

    elif semantics == ImportSemantics.NAMED:
        module_path = target
        symbol = None
        parts = target.lstrip(".").split(".")
        if len(parts) > 1:
            module_path = ".".join(parts[:-1])
            symbol = parts[-1]

        if target.startswith("."):
            resolved = os.path.normpath(from_dir / module_path)
            for suffix in (".ts", ".tsx", ".js", ".jsx"):
                candidate_file = Path(resolved + suffix)
                if str(candidate_file) in file_set:
                    return ImportTarget(module_path=str(candidate_file), symbol=symbol, is_external=False)
            return ImportTarget(module_path=target, is_external=True)

        for f in all_files:
            for suffix in (".ts", ".tsx", ".js", ".jsx"):
                if str(f).endswith("/" + module_path + suffix):
                    return ImportTarget(module_path=str(f), symbol=symbol, is_external=False)
        return ImportTarget(module_path=target, is_external=True)

    elif semantics == ImportSemantics.WILDCARD_LEAF:
        if target.startswith("."):
            resolved = os.path.normpath(from_dir / target)
            for suffix in (".ts", ".tsx", ".js", ".jsx"):
                candidate_file = Path(resolved + suffix)
                if str(candidate_file) in file_set:
                    return ImportTarget(module_path=str(candidate_file), is_external=False)
            return ImportTarget(module_path=target, is_external=True)
        return ImportTarget(module_path=target, is_external=True)

    else:
        if target.startswith("."):
            resolved = os.path.normpath(from_dir / target)
            for suffix in (".ts", ".tsx", ".js", ".jsx"):
                candidate_file = Path(resolved + suffix)
                if str(candidate_file) in file_set:
                    return ImportTarget(module_path=str(candidate_file), is_external=False)
            return None
        return ImportTarget(module_path=target, is_external=True)


def _resolve_go_import(
    target: str,
    from_file: Path,
    all_files: list[Path],
    semantics: ImportSemantics,
) -> ImportTarget | None:
    if target.startswith("."):
        return ImportTarget(module_path=target, is_external=False)
    parts = target.split("/")
    if len(parts) >= 2:
        return ImportTarget(module_path=target, is_external=True)
    return ImportTarget(module_path=target, is_external=True)


def _resolve_java_import(
    target: str,
    from_file: Path,
    all_files: list[Path],
    semantics: ImportSemantics,
) -> ImportTarget | None:
    parts = target.split(".")
    last = parts[-1]

    for f in all_files:
        if str(f).endswith(last + ".java"):
            return ImportTarget(module_path=str(f), symbol=last, is_external=False)

    jdk_packages = ("java.", "javax.", "jakarta.", "org.w3c.", "com.sun.", "sun.")
    if any(target.startswith(p) for p in jdk_packages):
        return ImportTarget(module_path=".".join(parts[:-1]), is_external=True)

    return ImportTarget(module_path=".".join(parts[:-1]), symbol=last, is_external=True)
