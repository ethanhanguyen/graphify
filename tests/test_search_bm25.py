import networkx as nx

from graphify.search.bm25 import BM25Index


def _make_graph():
    G = nx.Graph()
    G.add_node("n1", label="Token Embedding Layer", source_file="embed.py", docstring="Converts tokens to dense vectors")
    G.add_node("n2", label="Attention Mechanism", source_file="attention.py", docstring="Computes scaled dot-product attention")
    G.add_node("n3", label="Data Loader", source_file="data.py", docstring="Streams batches from disk")
    G.add_node("n4", label="optimizer", source_file="", docstring="")
    G.add_node("n5", label="", source_file="", docstring="")
    return G


def test_bm25_init_adds_to_graph():
    G = _make_graph()
    idx = BM25Index(G)
    assert "bm25_index" in G.graph
    assert G.graph["bm25_index"] is idx


def test_bm25_init_builds_docs():
    G = _make_graph()
    idx = BM25Index(G)
    assert idx._N == 4
    assert idx._avgdl > 0
    assert "n1" in idx._docs


def test_search_returns_relevant():
    G = _make_graph()
    idx = BM25Index(G)
    results = idx.search("attention mechanism")
    assert len(results) > 0
    assert results[0][0] == "n2"


def test_search_returns_node_ids():
    G = _make_graph()
    idx = BM25Index(G)
    results = idx.search("token embedding")
    ids = {r[0] for r in results}
    assert "n1" in ids


def test_search_empty_query():
    G = _make_graph()
    idx = BM25Index(G)
    results = idx.search("")
    assert results == []


def test_search_no_matches():
    G = _make_graph()
    idx = BM25Index(G)
    results = idx.search("zzznotexist")
    assert results == []


def test_incremental_update_adds_node():
    G = _make_graph()
    idx = BM25Index(G)
    G.add_node("n_new", label="New Component", source_file="new.py", docstring="A fresh node")
    idx.incremental_update(["n_new"], [])
    results = idx.search("new component")
    assert len(results) > 0
    assert results[0][0] == "n_new"


def test_incremental_update_removes_node():
    G = _make_graph()
    idx = BM25Index(G)
    assert "n1" in idx._docs
    idx.incremental_update([], ["n1"])
    assert "n1" not in idx._docs
    results = idx.search("token embedding")
    ids = {r[0] for r in results}
    assert "n1" not in ids
