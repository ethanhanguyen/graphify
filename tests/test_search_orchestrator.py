import networkx as nx

from graphify.search import SearchOrchestrator, hybrid_search


def _make_graph():
    G = nx.Graph()
    G.add_node("n1", label="Token Embedding Layer", source_file="embed.py", docstring="Converts tokens to dense vectors", community=1)
    G.add_node("n2", label="Attention Mechanism", source_file="attention.py", docstring="Computes scaled dot-product attention", community=1)
    G.add_node("n3", label="Data Loader", source_file="data.py", docstring="Streams batches from disk", community=2)
    G.add_node("proc1", label="Embed Pipeline", description="Embeds input data")
    G.add_edge("proc1", "n1", relation="step_in_process")
    G.add_edge("proc2", "n2", relation="step_in_process", confidence="INFERRED")
    return G


def test_orchestrator_init():
    G = _make_graph()
    orch = SearchOrchestrator(G)
    assert orch._graph is G
    assert orch._bm25 is not None
    assert orch._embeddings is None


def test_hybrid_search_falls_back_to_bm25():
    G = _make_graph()
    result = hybrid_search("attention mechanism", G)
    assert result["mode"] == "bm25"
    assert len(result["results"]) > 0


def test_hybrid_search_result_structure():
    G = _make_graph()
    result = hybrid_search("token embedding", G)
    assert "results" in result
    assert "processes" in result
    assert "orphaned" in result
    assert "mode" in result
    assert "total_candidates" in result


def test_hybrid_search_limit():
    G = _make_graph()
    result = hybrid_search("embedding attention loader", G, {"limit": 2})
    assert len(result["results"]) <= 2


def test_hybrid_search_no_matches():
    G = _make_graph()
    result = hybrid_search("zzznotexist", G)
    assert result["results"] == []
    assert result["orphaned"] == []
    assert result["processes"] == {}


def test_hybrid_search_process_grouping():
    G = _make_graph()
    result = hybrid_search("token embedding", G)
    assert "proc1" in result["processes"]


def test_orchestrator_update():
    G = _make_graph()
    orch = SearchOrchestrator(G)
    G.add_node("n_new", label="New Component", source_file="new.py", docstring="A new node")
    orch.update(added_nodes=["n_new"])
    result = orch.search("new component")
    assert len(result["results"]) > 0
    assert result["results"][0][0] == "n_new"


def test_hybrid_search_orphaned_has_references():
    G = _make_graph()
    result = hybrid_search("data loader", G)
    ids = {r[0] for r in result["results"]}
    assert "n3" in ids


def test_hybrid_search_min_confidence():
    G = _make_graph()
    result = hybrid_search("attention", G, {"min_confidence": 0.9})
    assert isinstance(result["results"], list)

def test_hybrid_search_with_semantic_mock():
    G = _make_graph()
    orch = SearchOrchestrator(G)
    orch._ensure_embeddings()
    assert orch._embeddings is not None
    orch._ensure_embeddings()
    assert orch._embeddings is not None

def test_orchestrator_update_no_embeddings():
    G = _make_graph()
    orch = SearchOrchestrator(G)
    orch.update(added_nodes=["n1"], removed_nodes=[])
    orch.update()


def test_hybrid_search_options_merge():
    G = _make_graph()
    result = hybrid_search("test", G, {"limit": 1, "min_confidence": 0.3})
    assert len(result["results"]) <= 1

def test_hybrid_search_default_options():
    G = _make_graph()
    result = hybrid_search("test", G)
    assert "results" in result

def test_semantic_fusion_path():
    from graphify.search.fusion import reciprocal_rank_fusion
    bm25 = [("n1", 2.5), ("n2", 1.0), ("n3", 0.5)]
    sem = [("n2", 0.9), ("n1", 0.7)]
    fused = reciprocal_rank_fusion(bm25, sem, k=60)
    assert len(fused) == 3

def test_search_with_process_grouping_empty():
    G = nx.Graph()
    G.add_node("x", label="zzz_nonexistent_item")
    result = hybrid_search("this_definitely_wont_match_anything", G)
    assert result["processes"] == {}
