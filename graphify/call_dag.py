"""6-stage call resolution DAG — orchestrate call extraction, inference, and resolution."""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

from graphify.call_extractors import extract_calls_from_ast, ExtractedCallSite
from graphify.receiver import infer_receiver
from graphify.cross_file import resolve_call_chain_across_files


@dataclass
class ResolvedCall:
    caller_id: str
    callee_id: str
    call_site_line: int
    edge_type: str = "calls"
    confidence: str = "EXTRACTED"
    resolution_steps: list[str] = field(default_factory=list)


def resolve_call_graph(files: list[Path], G) -> tuple[list[ResolvedCall], int]:
    resolved: list[ResolvedCall] = []
    unresolved_count = 0
    all_files = files
    file_paths = {str(f) for f in all_files}

    for file_path in files:
        if not file_path.exists():
            continue
        ext = file_path.suffix
        lang = _extension_to_language(ext)
        if lang is None:
            continue

        caller_nodes = _get_file_callers(G, str(file_path))
        if not caller_nodes:
            continue

        try:
            parsed = _parse_file(file_path, lang)
            if parsed is None:
                continue
            source = file_path.read_bytes()
        except Exception:
            continue

        calls = extract_calls_from_ast(parsed, lang, source)
        if not calls:
            continue

        for call in calls:
            caller_id = _find_caller_for_call(call, caller_nodes, G)

            if caller_id is None and call.in_class:
                for nid, data in caller_nodes.items():
                    if call.in_class and nid.endswith("_" + call.in_class.lower()):
                        caller_id = nid
                        break

            cross_results = resolve_call_chain_across_files(
                [call], file_path, all_files, G
            )

            if cross_results:
                for cr in cross_results:
                    resolved.append(ResolvedCall(
                        caller_id=caller_id or "unknown",
                        callee_id=cr["callee"],
                        call_site_line=call.line,
                        edge_type="calls",
                        confidence=cr.get("confidence", "INFERRED"),
                        resolution_steps=cr.get("resolution_steps", []),
                    ))
            else:
                unresolved_count += 1

    return resolved, unresolved_count


def _get_file_callers(G, file_path: str) -> dict[str, dict]:
    nodes: dict[str, dict] = {}
    for nid, data in G.nodes(data=True):
        if data.get("source_file") == file_path:
            label = data.get("label", "")
            if label.endswith("()") or label.startswith(".") and label.endswith("()"):
                nodes[nid] = data
    return nodes


def _find_caller_for_call(call: ExtractedCallSite, caller_nodes: dict[str, dict], G) -> str | None:
    callee_label = f"{call.name}()"
    callee_label_method = f".{call.name}()"

    for caller_nid, data in caller_nodes.items():
        label = data.get("label", "")

        if call.in_class and data.get("node_type") in ("METHOD", "FUNCTION", "CONSTRUCTOR"):
            for neighbor in G.neighbors(caller_nid):
                neighbor_label = G.nodes[neighbor].get("label", "").lower()
                if neighbor_label in (callee_label_method.lower(), callee_label.lower()):
                    return caller_nid

    for nid, data in G.nodes(data=True):
        label = data.get("label", "").lower()
        if label == callee_label.lower() or label == callee_label_method.lower():
            return nid

    return None


def _parse_file(file_path: Path, language: str):
    configs = {
        "python": ("tree_sitter_python", "language"),
        "typescript": ("tree_sitter_typescript", "language_typescript"),
        "javascript": ("tree_sitter_javascript", "language"),
        "go": ("tree_sitter_go", "language"),
        "java": ("tree_sitter_java", "language"),
    }
    try:
        mod_name, lang_fn = configs.get(language, (None, None))
        if not mod_name:
            return None
        mod = importlib.import_module(mod_name)
        from tree_sitter import Language, Parser
        fn = getattr(mod, lang_fn)
        language_obj = Language(fn())
        parser = Parser(language_obj)
        source = file_path.read_bytes()
        return parser.parse(source)
    except ImportError:
        return None
    except Exception:
        return None


def _extension_to_language(ext: str) -> str | None:
    ext_map = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".go": "go",
        ".java": "java",
    }
    return ext_map.get(ext)


def emit_call_edges(resolved: list[ResolvedCall]) -> list[dict]:
    edges: list[dict] = []
    for rc in resolved:
        if rc.caller_id == "unknown":
            continue
        edges.append({
            "source": rc.caller_id,
            "target": rc.callee_id,
            "relation": rc.edge_type,
            "confidence": rc.confidence,
            "confidence_score": 1.0 if rc.confidence == "EXTRACTED" else 0.7,
            "weight": 1.0,
            "source_location": f"L{rc.call_site_line}",
        })
    return edges
