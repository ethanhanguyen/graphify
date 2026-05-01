import networkx as nx

from graphify.search.grouping import group_by_process


def _make_process_graph():
    G = nx.Graph()
    G.add_node("proc1", label="Tokenization Pipeline", description="Converts text to tokens")
    G.add_node("n1", label="Tokenizer", community=1)
    G.add_node("n2", label="Normalizer", community=1)
    G.add_node("n3", label="Standalone Utility", community=2)
    G.add_node("proc2", label="Inference Pipeline", description="Runs model inference")
    G.add_node("n4", label="Model Runner", community=3)
    G.add_node("n5", label="Output Formatter", community=3)
    G.add_node("n6", label="Output Formatter v2", community=4)
    G.add_edge("proc1", "n1", relation="step_in_process")
    G.add_edge("proc1", "n2", relation="step_in_process")
    G.add_edge("proc2", "n4", relation="step_in_process")
    G.add_edge("proc2", "n5", relation="step_in_process")
    G.add_edge("proc2", "n6", relation="step_in_process")
    return G


def _make_multigraph():
    MG = nx.MultiGraph()
    MG.add_node("proc", label="Build", description="Build process")
    MG.add_node("s1", label="Compile")
    MG.add_node("s2", label="Link")
    MG.add_edge("proc", "s1", key=0, relation="step_in_process")
    MG.add_edge("proc", "s2", key=0, relation="step_in_process")
    return MG


def test_group_by_process_returns_processes():
    G = _make_process_graph()
    results = [("n1", 0.9), ("n2", 0.7)]
    grouped = group_by_process(results, G)
    assert "processes" in grouped
    assert "proc1" in grouped["processes"]
    assert grouped["processes"]["proc1"]["process_name"] == "Tokenization Pipeline"


def test_group_by_process_orphaned():
    G = _make_process_graph()
    results = [("n1", 0.9), ("n3", 0.5)]
    grouped = group_by_process(results, G)
    assert len(grouped["orphaned"]) == 1
    assert grouped["orphaned"][0][0] == "n3"


def test_group_by_process_returns_summary_text():
    G = _make_process_graph()
    results = [("n1", 0.9)]
    grouped = group_by_process(results, G)
    proc = grouped["processes"]["proc1"]
    assert proc["summary_text"] == "Converts text to tokens"


def test_group_by_process_priority_score():
    G = _make_process_graph()
    results = [("n1", 0.9)]
    grouped = group_by_process(results, G)
    proc = grouped["processes"]["proc1"]
    assert proc["priority_score"] == 0.5


def test_group_by_process_cross_community_false():
    G = _make_process_graph()
    results = [("n1", 0.9), ("n2", 0.7)]
    grouped = group_by_process(results, G)
    proc = grouped["processes"]["proc1"]
    assert not proc["cross_community"]
    assert proc["communities"] == [1]


def test_group_by_process_cross_community_true():
    G = _make_process_graph()
    results = [("n4", 0.9), ("n5", 0.7), ("n6", 0.6)]
    grouped = group_by_process(results, G)
    proc = grouped["processes"]["proc2"]
    assert proc["cross_community"]
    assert proc["communities"] == [3, 4]


def test_group_by_process_priority_full_hit():
    G = _make_process_graph()
    results = [("n1", 0.9), ("n2", 0.7)]
    grouped = group_by_process(results, G)
    proc = grouped["processes"]["proc1"]
    assert proc["priority_score"] == 1.0


def test_group_by_process_symbols_in_output():
    G = _make_process_graph()
    results = [("n1", 0.9), ("n2", 0.7)]
    grouped = group_by_process(results, G)
    proc = grouped["processes"]["proc1"]
    assert set(proc["symbols"]) == {"n1", "n2"}


def test_group_by_process_multigraph():
    MG = _make_multigraph()
    results = [("s1", 0.9)]
    grouped = group_by_process(results, MG)
    assert "proc" in grouped["processes"]


def test_group_by_process_empty_results():
    G = _make_process_graph()
    grouped = group_by_process([], G)
    assert grouped["processes"] == {}
    assert grouped["orphaned"] == []
