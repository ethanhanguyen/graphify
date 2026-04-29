"""Cross-file call resolution — resolve call targets across file boundaries."""
from __future__ import annotations

from pathlib import Path

from graphify.receiver import ExtractedCallSite


def resolve_call_chain_across_files(
    calls: list[ExtractedCallSite],
    current_file: Path,
    all_files: list[Path],
    G,
) -> list[dict]:
    results: list[dict] = []
    current_file_nodes = _nodes_for_file(G, str(current_file))

    for call in calls:
        resolved = _resolve_single_call(call, current_file, all_files, G, current_file_nodes)
        if resolved:
            results.append(resolved)
    return results


def _nodes_for_file(G, file_path: str) -> dict[str, dict]:
    nodes: dict[str, dict] = {}
    for nid, data in G.nodes(data=True):
        if data.get("source_file") == file_path:
            nodes[nid] = data
    return nodes


def _resolve_single_call(
    call: ExtractedCallSite,
    current_file: Path,
    all_files: list[Path],
    G,
    file_nodes: dict[str, dict],
) -> dict | None:
    local_target = _find_in_local_file(call.name, file_nodes)
    if local_target:
        return {
            "caller": None,
            "callee": local_target,
            "call_site_line": call.line,
            "confidence": "EXTRACTED",
            "resolution_steps": ["extract", "local_lookup"],
            "name": call.name,
        }

    if call.in_class and call.receiver in ("self", "this", "cls", None):
        if call.receiver is None:
            receiver = call.in_class
            method_target = _find_method_in_class(G, call.name, receiver)
            if method_target:
                return {
                    "caller": None,
                    "callee": method_target,
                    "call_site_line": call.line,
                    "confidence": "EXTRACTED",
                    "resolution_steps": ["extract", "infer_receiver", "local_class_lookup"],
                    "name": call.name,
                }

    import_target = _resolve_import_for_call(call.name, current_file, all_files)
    if import_target:
        target_nodes = _nodes_for_file(G, import_target)
        target = _find_in_local_file(call.name, target_nodes)
        if target:
            return {
                "caller": None,
                "callee": target,
                "call_site_line": call.line,
                "confidence": "INFERRED",
                "resolution_steps": ["extract", "import_resolve", "cross_file_lookup"],
                "name": call.name,
                "resolved_file": import_target,
            }

    if call.in_class:
        from graphify.mro import resolve_method_by_mro
        lang = _detect_language(str(current_file))
        mro_target = resolve_method_by_mro(call.name, call.in_class, G, lang)
        if mro_target:
            return {
                "caller": None,
                "callee": mro_target,
                "call_site_line": call.line,
                "confidence": "INFERRED",
                "resolution_steps": ["extract", "infer_receiver", "mro_walk"],
                "name": call.name,
            }

    return None


def _find_in_local_file(name: str, file_nodes: dict[str, dict]) -> str | None:
    search_label = f"{name}()"
    search_label_alt = f".{name}()"
    for nid, data in file_nodes.items():
        label = data.get("label", "").lower()
        if label == search_label.lower() or label == search_label_alt.lower():
            return nid
    return None


def _find_method_in_class(G, method_name: str, class_nid: str) -> str | None:
    search_label = f".{method_name}()"
    for neighbor in G.neighbors(class_nid):
        label = G.nodes[neighbor].get("label", "").lower()
        if label == search_label.lower():
            return neighbor
    return None


def _resolve_import_for_call(name: str, from_file: Path, all_files: list[Path]) -> str | None:
    from graphify.imports import resolve_import, ImportSemantics
    lang = _detect_language(str(from_file))
    if lang in ("python", "typescript", "javascript"):
        result = resolve_import(name, from_file, all_files, ImportSemantics.NAMED, lang)
        if result and not result.is_external:
            return result.module_path
    return None


def _detect_language(file_path: str) -> str:
    ext_map = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".go": "go",
        ".java": "java",
    }
    for ext, lang in ext_map.items():
        if file_path.endswith(ext):
            return lang
    return "unknown"
