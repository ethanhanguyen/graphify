# Query result cache with content-hash based targeted invalidation
#
# Two layers:
# 1. LRU in-memory cache for query results (fast, bounded memory)
# 2. Content-hash tracking for targeted invalidation when files change
#
# When a file changes, only cache entries that depend on that file's
# content-hash are evicted — other cached results remain valid.
#
from __future__ import annotations
import hashlib
import json
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

_MAX_CACHE_SIZE = 256


class QueryCache:
    def __init__(self, max_size: int = _MAX_CACHE_SIZE) -> None:
        self._max_size = max_size
        self._store: OrderedDict[str, tuple[str, Any]] = OrderedDict()
        self._file_entries: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    def _make_key(self, tool_name: str, arguments: dict) -> str:
        raw = json.dumps({"tool": tool_name, "args": arguments}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, tool_name: str, arguments: dict, file_hashes: dict[str, str] | None = None) -> Any | None:
        key = self._make_key(tool_name, arguments)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            stored_hashes_str, result = entry
            if file_hashes is not None and stored_hashes_str:
                stored = json.loads(stored_hashes_str)
                if not _hash_match(stored, file_hashes):
                    self._store.pop(key, None)
                    return None
            self._store.move_to_end(key)
            return result

    def set(self, tool_name: str, arguments: dict, result: Any, file_hashes: dict[str, str] | None = None) -> None:
        key = self._make_key(tool_name, arguments)
        hashes_str = json.dumps(file_hashes or {}, sort_keys=True)
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (hashes_str, result)
            if file_hashes:
                for fname in file_hashes:
                    self._file_entries.setdefault(fname, set()).add(key)
            if len(self._store) > self._max_size:
                old_key = next(iter(self._store))
                self._store.pop(old_key)

    def invalidate_file(self, filepath: str) -> int:
        with self._lock:
            keys = self._file_entries.pop(filepath, set())
            for key in keys:
                self._store.pop(key, None)
            return len(keys)

    def invalidate_all(self) -> int:
        with self._lock:
            count = len(self._store)
            self._store.clear()
            self._file_entries.clear()
            return count

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)

    @property
    def hit_rate(self) -> dict:
        with self._lock:
            return {"cached_entries": len(self._store), "tracked_files": len(self._file_entries)}

    def get_file_dependents_for_cache(self, filepath: str) -> set[str] | None:
        with self._lock:
            return self._file_entries.get(filepath)


def _hash_match(stored: dict[str, str], current: dict[str, str]) -> bool:
    for fname, old_hash in stored.items():
        new_hash = current.get(fname)
        if new_hash is None or new_hash != old_hash:
            return False
    return True


_global_cache: QueryCache | None = None
_global_cache_lock = threading.Lock()


def get_cache() -> QueryCache:
    global _global_cache
    if _global_cache is None:
        with _global_cache_lock:
            if _global_cache is None:
                _global_cache = QueryCache()
    return _global_cache


def reseed_cache(graph_path: str | Path = "graphify-out/graph.json") -> dict[str, str]:
    """Build file_hash map for the current graph's source files.

    Walks graph.json, collects all source_file entries, computes their
    content hashes, and returns a dict of {filepath: hash} for use with
    cache.set(). If graph.json doesn't exist, returns empty dict.
    """
    from graphify.cache import file_hash as _fh

    p = Path(graph_path)
    hashes: dict[str, str] = {}
    if not p.exists():
        return hashes
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        seen: set[str] = set()
        for node in data.get("nodes", []):
            src = node.get("source_file", "")
            if src and src not in seen:
                seen.add(src)
                fpath = Path(src)
                if fpath.is_file():
                    try:
                        hashes[src] = _fh(fpath)
                    except OSError:
                        pass
    except (json.JSONDecodeError, OSError):
        pass
    return hashes
