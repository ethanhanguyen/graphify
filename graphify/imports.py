from __future__ import annotations

from pathlib import Path
from typing import Optional

from graphify.language_provider import get_provider


def _resolve_named(target_name: str, from_file: Path, all_files: dict[str, list[str]]) -> Optional[str]:
    basename = target_name.rsplit(".", 1)[-1] if "." in target_name else target_name
    candidates = all_files.get(basename, [])
    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    from_parts = from_file.parts
    scored = []
    for c in candidates:
        c_parts = Path(c).parts
        common = 0
        for a, b in zip(from_parts[::-1], c_parts[::-1]):
            if a == b:
                common += 1
            else:
                break
        scored.append((common, c))
    scored.sort(reverse=True, key=lambda x: x[0])
    return scored[0][1]


def _resolve_wildcard_leaf(target_name: str, from_file: Path, all_files: dict[str, list[str]], suffix_index: dict[str, list[str]] | None = None) -> Optional[str]:
    suffix = f"/{target_name}"
    if suffix_index:
        matches = suffix_index.get(suffix, []) + suffix_index.get(f"{suffix}.py", [])
        alt_suffix = f"/{target_name.replace('.', '/')}"
        matches += suffix_index.get(alt_suffix, [])
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]
        from_parts = from_file.parts
        scored = [(sum(1 for a, b in zip(from_parts[::-1], Path(m).parts[::-1]) if a == b), m) for m in matches]
        scored.sort(reverse=True, key=lambda x: x[0])
        return scored[0][1]

    matches = []
    for file_list in all_files.values():
        for f in file_list:
            if f.endswith(suffix) or f.endswith(f"{suffix}.py"):
                matches.append(f)
            elif f.endswith(f"/{target_name.replace('.', '/')}"):
                matches.append(f)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    from_parts = from_file.parts
    scored = [(sum(1 for a, b in zip(from_parts[::-1], Path(m).parts[::-1]) if a == b), m) for m in matches]
    scored.sort(reverse=True, key=lambda x: x[0])
    return scored[0][1]


def _resolve_wildcard_transitive(target_name: str, from_file: Path, all_files: dict[str, list[str]], stem_index: dict[str, list[str]] | None = None) -> Optional[str]:
    if stem_index:
        candidates = stem_index.get(target_name, [])
    else:
        candidates = []
        for file_list in all_files.values():
            for f in file_list:
                if Path(f).stem == target_name:
                    candidates.append(f)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    from_parts = from_file.parts
    scored = [(sum(1 for a, b in zip(from_parts[::-1], Path(c).parts[::-1]) if a == b), c) for c in candidates]
    scored.sort(reverse=True, key=lambda x: x[0])
    return scored[0][1]


def _resolve_namespace(target_name: str, from_file: Path, all_files: dict[str, list[str]], namespace_index: dict[str, list[str]] | None = None) -> Optional[str]:
    dotted_name = target_name.replace(".", "/")
    if namespace_index:
        candidates = []
        for key, files in namespace_index.items():
            if key.endswith(dotted_name):
                candidates.extend(files)
            elif dotted_name in key and (key.endswith(f"{dotted_name}.py") or key.endswith(f"{dotted_name}/__init__.py")):
                candidates.extend(files)
    else:
        candidates = []
        for file_list in all_files.values():
            for f in file_list:
                f_norm = f.replace("\\", "/")
                if f_norm.endswith(dotted_name):
                    candidates.append(f)
                elif dotted_name in f_norm:
                    if f_norm.endswith(f"{dotted_name}.py") or f_norm.endswith(f"{dotted_name}/__init__.py"):
                        candidates.append(f)
    if not candidates:
        return None
    return candidates[0]


def resolve_import(target_name: str, from_file: Path, all_files: dict[str, list[str]], language: str, suffix_index: dict[str, list[str]] | None = None, stem_index: dict[str, list[str]] | None = None, namespace_index: dict[str, list[str]] | None = None) -> Optional[str]:
    result = _resolve_named(target_name, from_file, all_files)
    if result:
        return result

    result = _resolve_wildcard_leaf(target_name, from_file, all_files, suffix_index)
    if result:
        return result

    result = _resolve_wildcard_transitive(target_name, from_file, all_files, stem_index)
    if result:
        return result

    provider = get_provider(language)
    if provider and provider.import_semantics() == "namespace":
        return _resolve_namespace(target_name, from_file, all_files, namespace_index)

    return None


def build_import_graph(files: list[Path], parsed_files: dict[str, dict]) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {}
    for file_path in files:
        key = str(file_path)
        graph.setdefault(key, [])
        pf = parsed_files.get(key)
        if not pf:
            continue
        for edge in pf.get("edges", []):
            if edge.get("relation") in ("imports", "imports_from"):
                tgt = edge.get("target", "")
                if tgt and tgt not in graph[key]:
                    graph[key].append(tgt)
    return graph


def resolve_all_imports(
    file_path: Path,
    imports: list[dict],
    all_files: dict[str, list[str]],
    language: str,
    suffix_index: dict[str, list[str]] | None = None,
    stem_index: dict[str, list[str]] | None = None,
    namespace_index: dict[str, list[str]] | None = None,
) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for imp in imports:
        import_name = imp.get("name") or imp.get("source") or imp.get("target") or ""
        if not import_name:
            continue
        result = resolve_import(import_name, file_path, all_files, language, suffix_index, stem_index, namespace_index)
        if result:
            resolved[import_name] = result
    return resolved
