from __future__ import annotations

import networkx as nx

from graphify.search.bm25 import BM25Index
from graphify.search.fusion import reciprocal_rank_fusion
from graphify.search.grouping import group_by_process


class SearchOrchestrator:
    def __init__(self, graph: nx.Graph):
        self._graph = graph
        self._bm25 = BM25Index(graph)
        self._embeddings = None

    def _ensure_embeddings(self) -> None:
        if self._embeddings is not None:
            return
        try:
            from graphify.search.embeddings import EmbeddingIndex
            self._embeddings = EmbeddingIndex(self._graph)
        except ImportError:
            self._embeddings = False

    def search(self, query_text: str, options: dict | None = None) -> dict:
        opts = {
            "bm25_weight": 0.4,
            "semantic_weight": 0.4,
            "process_weight": 0.2,
            "limit": 20,
            "min_confidence": 0.5,
        }
        if options:
            opts.update(options)

        bm25_results = self._bm25.search(query_text, top_k=100)

        self._ensure_embeddings()
        semantic_results: list = []
        if self._embeddings and self._embeddings is not False:
            semantic_results = self._embeddings.search(query_text, top_k=100)

        if not semantic_results:
            fused = [(nid, score) for nid, score in bm25_results]
        else:
            fused = reciprocal_rank_fusion(bm25_results, semantic_results, k=60)

        limited = [(nid, score) for nid, score in fused[: opts["limit"]]]

        groups = group_by_process(limited, self._graph)

        return {
            "results": limited,
            "processes": groups.get("processes", {}),
            "orphaned": groups.get("orphaned", []),
            "mode": "hybrid" if semantic_results else "bm25",
            "total_candidates": len(fused),
        }

    def update(self, added_nodes: list | None = None, removed_nodes: list | None = None) -> None:
        added = added_nodes or []
        removed = removed_nodes or []
        self._bm25.incremental_update(added, removed)
        if self._embeddings and self._embeddings is not False:
            self._embeddings.incremental_update(self._graph, added + removed)


def hybrid_search(query_text: str, graph, options: dict | None = None) -> dict:
    orch = SearchOrchestrator(graph)
    return orch.search(query_text, options)


def build_orchestrator(graph: nx.Graph, use_embeddings: bool = False) -> SearchOrchestrator:
    orch = SearchOrchestrator(graph)
    if not use_embeddings:
        orch._embeddings = False
    return orch
