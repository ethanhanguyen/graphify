"""Semantic vector embeddings for code symbols.

Uses deterministic random projections (no ML deps required).
For production, swap in sentence-transformers via optional dependency.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

EMBEDDING_DIM = 384

_CODE_NODE_TYPES = {
    "FUNCTION", "CLASS", "METHOD", "INTERFACE", "ENUM", "TYPE_ALIAS",
    "CONSTRUCTOR", "STRUCT", "TRAIT", "NAMESPACE", "MODULE",
    "ROUTE", "TOOL", "PROCESS",
}


def _import_numpy():
    try:
        import numpy as np
        return np
    except ImportError:
        return None


def _pseudorandom_vector(seed: int, dim: int) -> list[float]:
    rng = _import_numpy()
    if rng is not None:
        gen = rng.random.RandomState(seed)
        return [float(v) for v in gen.normal(0, 1, dim)]
    import random
    r = random.Random(seed)
    return [r.gauss(0, 1) for _ in range(dim)]


def _l2_normalize(vec: list[float]) -> list[float]:
    norm_sq = sum(v * v for v in vec)
    norm = math.sqrt(norm_sq)
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def _hash_seed(text: str) -> int:
    h = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") % (2**32)


def generate_embedding(text: str, dimensions: int = EMBEDDING_DIM, seed: int = 42) -> list[float]:
    text_seed = _hash_seed(text)
    proj = _pseudorandom_vector(text_seed, dimensions)
    return _l2_normalize(proj)


def node_embedding_text(node_data: dict) -> str:
    label = node_data.get("label", "")
    signature = node_data.get("signature", "")
    docstring = node_data.get("docstring", "")
    parts = [label]
    if signature:
        parts.append(signature)
    if docstring:
        parts.append(docstring)
    return " ".join(parts)


_NON_CODE_FILETYPES = {"markdown", "image", "video", "pdf", "office", "audio", "text"}


def generate_embeddings(G, dimensions: int = EMBEDDING_DIM) -> dict[str, list[float]]:
    embeddings: dict[str, list[float]] = {}
    for nid, data in G.nodes(data=True):
        nt = data.get("node_type", "")
        ft = data.get("file_type", "")
        if nt in ("FILE", "CONCEPT", "UNKNOWN"):
            continue
        if ft in _NON_CODE_FILETYPES:
            continue
        text = node_embedding_text(data)
        if not text.strip():
            continue
        embeddings[nid] = generate_embedding(text, dimensions)
    return embeddings


def compute_cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError("Vectors must have same length")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def search_by_embedding(
    query_text: str,
    embeddings: dict[str, list[float]],
    top_k: int = 20,
) -> list[tuple[str, float]]:
    if not embeddings:
        return []
    query = generate_embedding(query_text)
    scored = [(nid, compute_cosine(query, emb)) for nid, emb in embeddings.items()]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def save_embeddings(embeddings: dict[str, list[float]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    items = sorted(embeddings.items())
    batch_size = 10000
    for i in range(0, len(items), batch_size):
        batch = dict(items[i : i + batch_size])
        shard_path = output_dir / f"embeddings_{i // batch_size:04d}.json"
        shard_path.write_text(json.dumps(batch), encoding="utf-8")


def load_embeddings(input_dir: Path) -> dict[str, list[float]]:
    if not input_dir.exists():
        return {}
    result: dict[str, list[float]] = {}
    for shard_path in sorted(input_dir.glob("embeddings_*.json")):
        data = json.loads(shard_path.read_text(encoding="utf-8"))
        result.update(data)
    return result


def compute_node_hash(G, node_id: str) -> str:
    data = G.nodes.get(node_id, {})
    text = node_embedding_text(data)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
