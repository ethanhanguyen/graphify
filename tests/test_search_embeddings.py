import numpy as np
import networkx as nx

from graphify.search.embeddings import EmbeddingIndex


def _make_graph():
    G = nx.Graph()
    G.add_node("n1", label="Token Embedding", file_type="code", source_file="embed.py")
    G.add_node("n2", label="Attention", file_type="code", source_file="attn.py")
    G.add_node("n3", label="Design Doc", file_type="document", source_file="design.md")
    G.add_node("n4", label="", file_type="code", source_file="empty.py")
    return G


def test_init_without_sentence_transformers():
    G = _make_graph()
    idx = EmbeddingIndex(G)
    assert idx._model is None
    assert not idx._loaded
    assert idx._embeddings == {}


def test_search_returns_empty_without_model():
    G = _make_graph()
    idx = EmbeddingIndex(G)
    results = idx.search("attention")
    assert results == []


def test_node_text_formatting():
    G = _make_graph()
    idx = EmbeddingIndex(G)
    text = idx._node_text({"label": "Foo", "file_type": "code"})
    assert text == "Foo code"


def test_node_text_empty():
    G = _make_graph()
    idx = EmbeddingIndex(G)
    text = idx._node_text({})
    assert text == ""


def test_node_hash_consistent():
    G = _make_graph()
    idx = EmbeddingIndex(G)
    h1 = idx._node_hash({"label": "Foo", "file_type": "code"})
    h2 = idx._node_hash({"label": "Foo", "file_type": "code"})
    assert h1 == h2


def test_node_hash_differs():
    G = _make_graph()
    idx = EmbeddingIndex(G)
    h1 = idx._node_hash({"label": "Foo", "file_type": "code"})
    h2 = idx._node_hash({"label": "Bar", "file_type": "code"})
    assert h1 != h2


def test_embed_node_skips_non_code():
    G = _make_graph()
    idx = EmbeddingIndex(G)
    result = idx.embed_node({"label": "Doc", "file_type": "document"})
    assert result is None


def test_embed_node_no_model_returns_none():
    G = _make_graph()
    idx = EmbeddingIndex(G)
    result = idx.embed_node({"label": "Foo", "file_type": "code"})
    assert result is None


def test_build_without_model_does_nothing():
    G = _make_graph()
    idx = EmbeddingIndex(G)
    idx.build()
    assert idx._embeddings == {}


def test_load_model_fails_without_package():
    G = _make_graph()
    idx = EmbeddingIndex(G)
    assert not idx._load_model()


def test_search_shard_keys_filtered():
    G = _make_graph()
    idx = EmbeddingIndex(G)
    idx._embeddings = {"a": None}
    q = np.array([0.1, 0.2], dtype=np.float32)
    result = idx.search_shard(q, [])
    assert result == []


def test_search_shard_no_valid_keys():
    G = _make_graph()
    idx = EmbeddingIndex(G)
    idx._embeddings = {}
    q = np.array([0.1], dtype=np.float32)
    result = idx.search_shard(q, ["x"])
    assert result == []
