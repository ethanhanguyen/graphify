from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import networkx as nx


class EmbeddingIndex:
    def __init__(self, graph: nx.Graph, model_name: str = "all-MiniLM-L6-v2"):
        self._graph = graph
        self._model_name = model_name
        self._model = None
        self._embeddings: dict[str, np.ndarray] = {}
        self._node_hashes: dict[str, str] = {}
        self._embed_dir = Path("graphify-out/embeddings")
        self._shard_size = 500
        self._loaded = False

    def _load_model(self) -> bool:
        if self._model is not None:
            return True
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
            return True
        except ImportError:
            print("[graphify] sentence-transformers not installed. Semantic search disabled.", file=sys.stderr)
            return False

    def _node_text(self, data: dict) -> str:
        label = data.get("label", "")
        ftype = data.get("file_type", "")
        return f"{label} {ftype}".strip()

    def _node_hash(self, data: dict) -> str:
        text = self._node_text(data)
        return hashlib.sha1(text.encode()).hexdigest()

    def embed_node(self, node_data: dict) -> Optional[np.ndarray]:
        if node_data.get("file_type") != "code":
            return None
        if not self._load_model():
            return None
        text = self._node_text(node_data)
        if not text:
            return None
        return self._model.encode([text], normalize_embeddings=True)[0].astype(np.float32)

    def build(self) -> None:
        if not self._load_model():
            return
        self._embed_dir.mkdir(parents=True, exist_ok=True)
        code_nodes = [
            (nid, data) for nid, data in self._graph.nodes(data=True)
            if data.get("file_type") == "code"
        ]
        if not code_nodes:
            return
        texts = [self._node_text(data) for _, data in code_nodes]
        vecs = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        for (nid, data), vec in zip(code_nodes, vecs):
            self._embeddings[nid] = vec.astype(np.float32)
            self._node_hashes[nid] = self._node_hash(data)
        self._persist()
        self._loaded = True

    def _persist(self) -> None:
        keys = list(self._embeddings.keys())
        shard_idx = 0
        for i in range(0, len(keys), self._shard_size):
            shard_keys = keys[i:i + self._shard_size]
            shard_data = {
                "model": self._model_name,
                "embeddings": {k: self._embeddings[k].tolist() for k in shard_keys},
                "hashes": {k: self._node_hashes[k] for k in shard_keys},
            }
            shard_path = self._embed_dir / f"shard_{shard_idx:04d}.json"
            shard_path.write_text(json.dumps(shard_data))
            shard_idx += 1
        meta = {
            "model": self._model_name,
            "num_shards": shard_idx,
            "shard_size": self._shard_size,
        }
        (self._embed_dir / "meta.json").write_text(json.dumps(meta))

    def _load_shards(self) -> None:
        self._embeddings.clear()
        self._node_hashes.clear()
        meta_path = self._embed_dir / "meta.json"
        if not meta_path.exists():
            return
        meta = json.loads(meta_path.read_text())
        for i in range(meta.get("num_shards", 0)):
            shard_path = self._embed_dir / f"shard_{i:04d}.json"
            if not shard_path.exists():
                continue
            shard = json.loads(shard_path.read_text())
            for k, v in shard.get("embeddings", {}).items():
                self._embeddings[k] = np.array(v, dtype=np.float32)
            self._node_hashes.update(shard.get("hashes", {}))
        self._loaded = True

    def search(self, query_text: str, top_k: int = 100) -> list[tuple[str, float]]:
        if not self._loaded:
            self._load_shards()
        if not self._embeddings:
            if not self._load_model():
                return []
            self.build()
            if not self._embeddings:
                return []
        if not self._load_model():
            return []
        q_vec = self._model.encode([query_text], normalize_embeddings=True)[0].astype(np.float32)
        return self.search_shard(q_vec, list(self._embeddings.keys()))[:top_k]

    def search_shard(self, query_embedding: np.ndarray, shard: list[str]) -> list[tuple[str, float]]:
        keys = [k for k in shard if k in self._embeddings]
        if not keys:
            return []
        mat = np.stack([self._embeddings[k] for k in keys])
        scores = np.dot(mat, query_embedding)
        order = np.argsort(scores)[::-1].tolist()
        return [(keys[i], float(scores[i])) for i in order]

    def incremental_update(self, graph: nx.Graph, changed_node_ids: list) -> None:
        self._graph = graph
        if not self._loaded:
            self._load_shards()
        if not self._embeddings and not self._load_model():
            return
        if not self._embeddings:
            self.build()
            return
        need_embed = []
        for nid in changed_node_ids:
            if nid not in self._graph:
                self._embeddings.pop(nid, None)
                self._node_hashes.pop(nid, None)
                continue
            data = self._graph.nodes[nid]
            if data.get("file_type") != "code":
                self._embeddings.pop(nid, None)
                self._node_hashes.pop(nid, None)
                continue
            new_hash = self._node_hash(data)
            old_hash = self._node_hashes.get(nid)
            if new_hash != old_hash:
                need_embed.append((nid, data))
        if need_embed and self._load_model():
            texts = [self._node_text(d) for _, d in need_embed]
            vecs = self._model.encode(texts, normalize_embeddings=True)
            for (nid, data), vec in zip(need_embed, vecs):
                self._embeddings[nid] = vec.astype(np.float32)
                self._node_hashes[nid] = self._node_hash(data)
            self._persist()
