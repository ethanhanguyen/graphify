"""BM25 keyword search on symbol names, file paths, docstrings.

Built at graph load time. Incrementally updateable.
Pure Python — no external deps.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: dict[str, str] = {}
        self.doc_lengths: dict[str, int] = {}
        self.avg_doc_length: float = 0.0
        self.inverted_index: dict[str, dict[str, int]] = defaultdict(dict)
        self.doc_count_per_term: dict[str, int] = defaultdict(int)
        self.total_docs: int = 0

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", text.lower())

    def add_document(self, doc_id: str, text: str) -> None:
        self.documents[doc_id] = text
        tokens = self._tokenize(text)
        self.doc_lengths[doc_id] = len(tokens)
        self.total_docs += 1
        total_len = sum(self.doc_lengths.values())
        self.avg_doc_length = total_len / max(1, self.total_docs)

        term_freq: dict[str, int] = {}
        for t in tokens:
            term_freq[t] = term_freq.get(t, 0) + 1

        for term, freq in term_freq.items():
            self.inverted_index[term][doc_id] = freq
            self.doc_count_per_term[term] = self.doc_count_per_term.get(term, 0) + 1

    def remove_document(self, doc_id: str) -> None:
        if doc_id not in self.documents:
            return
        text = self.documents.pop(doc_id)
        tokens = set(self._tokenize(text))
        self.total_docs -= 1
        total_len = sum(self.doc_lengths.values())
        self.avg_doc_length = total_len / max(1, self.total_docs)
        del self.doc_lengths[doc_id]

        for term in tokens:
            inv = self.inverted_index.get(term, {})
            inv.pop(doc_id, None)
            if not inv:
                self.inverted_index.pop(term, None)
                self.doc_count_per_term.pop(term, None)
            else:
                self.doc_count_per_term[term] = len(inv)

    def search(self, query: str, top_k: int = 20) -> list[tuple[str, float]]:
        query_terms = self._tokenize(query)
        scored: dict[str, float] = defaultdict(float)
        N = max(1, self.total_docs)

        for term in query_terms:
            inv = self.inverted_index.get(term, {})
            df = len(inv)
            idf = math.log(1 + (N - df + 0.5) / (df + 0.5))

            for doc_id, tf in inv.items():
                dl = self.doc_lengths.get(doc_id, 0)
                avgdl = max(1.0, self.avg_doc_length)
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * dl / avgdl)
                scored[doc_id] += idf * numerator / denominator

        return sorted(scored.items(), key=lambda x: x[1], reverse=True)[:top_k]

    def index_from_graph(self, G) -> None:
        for nid, data in G.nodes(data=True):
            label = data.get("label", "")
            signature = data.get("signature", "")
            docstring = data.get("docstring", "")
            source_file = data.get("source_file", "")
            node_type = data.get("node_type", data.get("file_type", ""))
            text = f"{label} {signature} {docstring} {source_file} {node_type}"
            self.add_document(nid, text)
