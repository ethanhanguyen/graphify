# Agent hook integration - PreToolUse and PostToolUse hooks
#
# PreToolUseHook: Enriches agent searches with graph context before
# a tool like grep/find is used. Injects community context and god
# node information to guide search decisions.
#
# PostToolUseHook: Detects file changes after tool execution,
# invalidates relevant cache entries, and prompts reindexing.
#
from __future__ import annotations

import json
import hashlib
import threading
from pathlib import Path
from typing import Any


class PreToolUseHook:
    def __init__(self, graph_path: str | Path = "graphify-out/graph.json") -> None:
        self._graph_path = Path(graph_path)
        self._last_graph_hash: str = ""
        self._last_context: str = ""
        self._lock = threading.Lock()

    def _load_graph_context(self) -> str:
        p = self._graph_path
        if not p.exists():
            return ""
        try:
            raw = p.read_bytes()
            h = hashlib.sha256(raw).hexdigest()
            with self._lock:
                if h == self._last_graph_hash and self._last_context:
                    return self._last_context
                self._last_graph_hash = h
            data = json.loads(raw.decode(errors="replace"))
            context = _build_pre_tool_context(data)
            with self._lock:
                self._last_context = context
            return context
        except (json.JSONDecodeError, OSError):
            return ""

    def apply(self, tool_name: str, arguments: dict) -> str | None:
        search_tools = {"grep", "rg", "find", "fd", "ack", "ag", "ls", "glob"}
        if tool_name.lower() not in search_tools and not _is_search_command(tool_name, arguments):
            return None
        context = self._load_graph_context()
        if not context:
            return None
        return f"graphify: Knowledge graph context for this repo:\n{context}"


class PostToolUseHook:
    def __init__(
        self,
        graph_path: str | Path = "graphify-out/graph.json",
        cache_path: str | Path = "graphify-out/cache",
    ) -> None:
        self._graph_path = Path(graph_path)
        self._cache_path = Path(cache_path)
        self._lock = threading.Lock()
        self._tracked_hashes: dict[str, str] = {}

    def _snapshot_files(self, filepaths: list[str]) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for fp in filepaths:
            p = Path(fp)
            if p.is_file():
                try:
                    from graphify.cache import file_hash
                    hashes[fp] = file_hash(p)
                except OSError:
                    pass
        return hashes

    def detect_changes(self, tool_name: str, result: Any = None) -> list[str]:
        file_change_tools = {"write", "edit", "edit_file", "bash", "run", "exec"}
        if tool_name.lower() not in file_change_tools:
            return []
        changed: list[str] = []
        current = self._snapshot_files(list(self._tracked_hashes.keys()))
        with self._lock:
            for fp, old_h in self._tracked_hashes.items():
                new_h = current.get(fp)
                if new_h is not None and new_h != old_h:
                    changed.append(fp)
                    self._tracked_hashes[fp] = new_h
        return changed

    def invalidate_affected(self, changed_files: list[str]) -> dict[str, int]:
        from graphify.query_cache import get_cache

        cache = get_cache()
        invalidated = 0
        for fp in changed_files:
            n = cache.invalidate_file(fp)
            invalidated += n
        return {"invalidated_cache_entries": invalidated, "changed_files": len(changed_files)}

    def track_files(self, filepaths: list[str]) -> None:
        with self._lock:
            for fp in filepaths:
                if fp not in self._tracked_hashes:
                    p = Path(fp)
                    if p.is_file():
                        try:
                            from graphify.cache import file_hash
                            self._tracked_hashes[fp] = file_hash(p)
                        except OSError:
                            pass

    def handle_post_tool(self, tool_name: str, result: Any = None) -> str | None:
        if tool_name.lower() in ("write", "edit", "edit_file"):
            changed = self.detect_changes(tool_name, result)
            if changed:
                info = self.invalidate_affected(changed)
                return (f"graphify: {len(changed)} file(s) changed. "
                        f"Cache invalidated ({info['invalidated_cache_entries']} entries). "
                        f"Run graphify update to reindex.")
        return None


def _is_search_command(tool_name: str, arguments: dict) -> bool:
    if tool_name.lower() not in ("bash", "run"):
        return False
    cmd = arguments.get("command", "")
    if isinstance(cmd, str):
        parts = cmd.split()
        if parts:
            first = parts[0].lower()
            return first in ("grep", "rg", "find", "fd", "ack", "ag")
    return False


def _build_pre_tool_context(data: dict) -> str:
    lines: list[str] = []
    nodes = data.get("nodes", [])
    edges_data = data.get("edges", data.get("links", []))
    total_nodes = len(nodes)
    total_edges = len(edges_data)

    lines.append(f"Read graphify-out/GRAPH_REPORT.md for full context.")
    lines.append(f"Graph: {total_nodes} nodes, {total_edges} edges.")

    god_candidates: list[tuple[int, str]] = []
    degree_map: dict[str, int] = {}
    for edge in edges_data:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src:
            degree_map[src] = degree_map.get(src, 0) + 1
        if tgt:
            degree_map[tgt] = degree_map.get(tgt, 0) + 1

    for node in nodes:
        nid = node.get("id", "")
        label = node.get("label", nid)
        deg = degree_map.get(nid, 0)
        if deg > 2:
            god_candidates.append((deg, label))

    god_candidates.sort(reverse=True)
    top = god_candidates[:8]
    if top:
        lines.append("Top concepts: " + ", ".join(label for _, label in top))

    comms: dict[int, int] = {}
    for node in nodes:
        cid = node.get("community")
        if cid is not None:
            comms[int(cid)] = comms.get(int(cid), 0) + 1
    lines.append(f"{len(comms)} communities detected.")

    return "\n".join(lines)
