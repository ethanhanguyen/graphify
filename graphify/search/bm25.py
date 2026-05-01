from __future__ import annotations

import re
import math
from collections import defaultdict

import networkx as nx


class BM25Index:
    def __init__(self, graph: nx.Graph):
        self._graph = graph
        self._k1 = 1.5
        self._b = 0.75
        self._docs: dict[str, str] = {}
        self._term_freqs: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._doc_lengths: dict[str, int] = {}
        self._df: dict[str, int] = defaultdict(int)
        self._avgdl = 0.0
        self._N = 0
        self._build(graph)
        graph.graph["bm25_index"] = self

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        text = text.lower()
        text = text.replace("_", " ")
        text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
        text = re.sub(r"[^a-z0-9\s]", "", text)
        return [t for t in text.split() if len(t) >= 2]

    def _build(self, graph: nx.Graph) -> None:
        for nid, data in graph.nodes(data=True):
            parts = [data.get("label", "")]
            src = data.get("source_file", "")
            if src:
                parts.append(src)
            docstring = data.get("docstring") or data.get("documentation", "")
            if docstring:
                parts.append(docstring)
            text = " ".join(parts)
            tokens = self._tokenize(text)
            if not tokens:
                continue
            self._docs[nid] = text
            self._doc_lengths[nid] = len(tokens)
            seen: set[str] = set()
            for token in tokens:
                self._term_freqs[token][nid] += 1
                if token not in seen:
                    seen.add(token)
                    self._df[token] += 1
            self._N += 1
        if self._N > 0:
            self._avgdl = sum(self._doc_lengths.values()) / self._N

    def search(self, query: str, top_k: int = 100) -> list[tuple[str, float]]:
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []
        scores: dict[str, float] = defaultdict(float)
        for token in set(query_tokens):
            df = self._df.get(token, 0)
            if df == 0:
                continue
            idf = math.log((self._N - df + 0.5) / (df + 0.5) + 1.0)
            for nid, tf in self._term_freqs.get(token, {}).items():
                doc_len = self._doc_lengths[nid]
                numerator = tf * (self._k1 + 1)
                denominator = tf + self._k1 * (1 - self._b + self._b * doc_len / self._avgdl)
                scores[nid] += idf * numerator / denominator
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return ranked[:top_k]

    def _add_node(self, nid: str) -> None:
        data = self._graph.nodes.get(nid)
        if not data:
            return
        parts = [data.get("label", "")]
        src = data.get("source_file", "")
        if src:
            parts.append(src)
        docstring = data.get("docstring") or data.get("documentation", "")
        if docstring:
            parts.append(docstring)
        text = " ".join(parts)
        tokens = self._tokenize(text)
        if not tokens:
            return
        self._docs[nid] = text
        self._doc_lengths[nid] = len(tokens)
        seen: set[str] = set()
        for token in tokens:
            self._term_freqs[token][nid] += 1
            if token not in seen:
                seen.add(token)
                self._df[token] += 1
        self._N += 1
        self._avgdl = sum(self._doc_lengths.values()) / self._N if self._N > 0 else 0.0

    def _remove_node(self, nid: str) -> None:
        if nid not in self._docs:
            return
        text = self._docs.pop(nid, "")
        tokens = self._tokenize(text)
        self._doc_lengths.pop(nid, None)
        for token in set(tokens):
            if token in self._term_freqs:
                self._term_freqs[token].pop(nid, None)
                if not self._term_freqs[token]:
                    del self._term_freqs[token]
                self._df[token] = max(0, self._df[token] - 1)
                if self._df[token] <= 0:
                    self._df.pop(token, None)
        self._N = max(0, self._N - 1)
        self._avgdl = sum(self._doc_lengths.values()) / self._N if self._N > 0 else 0.0

    def incremental_update(self, added_nodes: list, removed_nodes: list) -> None:
        for nid in removed_nodes:
            self._remove_node(nid)
        for nid in added_nodes:
            self._remove_node(nid)
            self._add_node(nid)
