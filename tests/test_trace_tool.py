"""Tests for trace MCP tool logic."""
import networkx as nx
from graphify.entry_points import EntryPoint, detect_entry_points
from graphify.processes import trace_process, Process


def _build_call_chain_graph():
    G = nx.DiGraph()
    G.add_node("n_auth", label="authenticate", source_file="auth.py",
               source_location="L5", language="python", file_type="code")
    G.add_node("n_db", label="db_lookup", source_file="db.py",
               source_location="L10", language="python", file_type="code")
    G.add_node("n_cache", label="cache_get", source_file="cache.py",
               source_location="L15", language="python", file_type="code")
    G.add_node("n_log", label="log_request", source_file="log.py",
               source_location="L1", language="python", file_type="code")
    G.add_edge("n_auth", "n_db", relation="calls")
    G.add_edge("n_db", "n_cache", relation="calls")
    G.add_edge("n_auth", "n_log", relation="calls")
    return G


def test_trace_finds_entry_by_label():
    G = _build_call_chain_graph()
    ep = None
    for nid, ndata in G.nodes(data=True):
        if "authenticate" in ndata.get("label", ""):
            sl = ndata.get("source_location", "0")
            line = int(sl.replace("L", ""))
            ep = EntryPoint(
                name=ndata.get("label", nid),
                kind="EVENT",
                file=ndata.get("source_file", ""),
                line=line,
                language=ndata.get("language", ""),
            )
            break
    assert ep is not None
    proc = trace_process(ep, G, max_depth=20)
    assert proc.total_steps >= 4
    assert proc.max_depth >= 2
    labels = {s.label for s in proc.steps}
    assert "authenticate" in labels
    assert "db_lookup" in labels
    assert "cache_get" in labels
    assert "log_request" in labels


def test_trace_on_missing_entry_point_returns_empty_process():
    G = _build_call_chain_graph()
    ep = EntryPoint(
        name="nonexistent_func", kind="EVENT", file="nowhere.py",
        line=0, language="python",
    )
    proc = trace_process(ep, G)
    assert proc.total_steps == 0
    assert proc.name == "nonexistent_func"


def test_trace_respects_max_depth_in_tool_scenario():
    G = _build_call_chain_graph()
    ep = None
    for nid, ndata in G.nodes(data=True):
        if "authenticate" in ndata.get("label", ""):
            sl = ndata.get("source_location", "0")
            line = int(sl.replace("L", ""))
            ep = EntryPoint(
                name=ndata.get("label", nid),
                kind="EVENT",
                file=ndata.get("source_file", ""),
                line=line,
                language=ndata.get("language", ""),
            )
            break
    proc = trace_process(ep, G, max_depth=1)
    assert proc.total_steps >= 2
    assert proc.max_depth <= 1


def test_trace_with_entry_points_from_extractions():
    G = nx.DiGraph()
    G.add_node("n_login", label="app.get('/login')", source_file="auth.py",
               source_location="L3", language="typescript", file_type="code")
    G.add_node("n_verify", label="verify_password", source_file="auth.py",
               source_location="L15", language="typescript", file_type="code")
    G.add_edge("n_login", "n_verify", relation="calls")

    extractions = [
        {
            "id": "n_login", "label": "app.get('/login')", "source_file": "auth.py",
            "source_location": "L3", "tree_sitter_type": "call_expression",
            "language": "typescript",
        },
    ]
    eps = detect_entry_points(G, extractions)
    assert len({ep.name for ep in eps}) > 0

    for ep in eps:
        proc = trace_process(ep, G)
        assert proc.total_steps >= 1
