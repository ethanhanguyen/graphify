from __future__ import annotations
import json
import time
from pathlib import Path
import networkx as nx
from networkx.readwrite import json_graph

from graphify.registry import get_repo


class GraphPool:
    def __init__(self, max_open: int = 5, ttl_minutes: int = 5):
        self._pool: dict[str, tuple[nx.Graph, float]] = {}
        self._max_open = max_open
        self._ttl_seconds = ttl_minutes * 60

    def _graph_path(self, repo_id: str) -> Path | None:
        entry = get_repo(repo_id)
        if not entry:
            return None
        return Path(entry.path) / "graphify-out" / "graph.json"

    def get_graph(self, repo_id: str) -> nx.Graph | None:
        self.evict_expired()
        if repo_id in self._pool:
            G, _ = self._pool[repo_id]
            self._pool[repo_id] = (G, time.monotonic())
            return G
        graph_path = self._graph_path(repo_id)
        if not graph_path or not graph_path.exists():
            return None
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        try:
            G = json_graph.node_link_graph(data, edges="links")
        except TypeError:
            G = json_graph.node_link_graph(data)
        if len(self._pool) >= self._max_open:
            oldest = min(self._pool, key=lambda k: self._pool[k][1])
            del self._pool[oldest]
        self._pool[repo_id] = (G, time.monotonic())
        return G

    def evict(self, repo_id: str) -> None:
        if repo_id in self._pool:
            del self._pool[repo_id]

    def evict_expired(self) -> int:
        now = time.monotonic()
        expired = [rid for rid, (_, ts) in self._pool.items() if now - ts > self._ttl_seconds]
        for rid in expired:
            del self._pool[rid]
        return len(expired)

    def close(self) -> None:
        self._pool.clear()
