"""Tests for processes.py."""
import networkx as nx
from graphify.entry_points import EntryPoint
from graphify.processes import (
    ProcessStep,
    Process,
    trace_process,
    trace_all_entry_points,
    trace_changed_nodes,
)


def _build_call_graph(edges):
    """Build a DiGraph with 'calls' relation edges."""
    G = nx.DiGraph()
    for src, tgt in edges:
        G.add_node(src, label=src, source_file=f"{src}.py", source_location="L1")
        G.add_node(tgt, label=tgt, source_file=f"{tgt}.py", source_location="L1")
        G.add_edge(src, tgt, relation="calls")
    return G


def test_processstep_dataclass():
    ps = ProcessStep(
        node_id="n1", label="foo", file="a.py", line=42, depth=2,
        callers=["n0"], callees=["n2", "n3"],
    )
    assert ps.node_id == "n1"
    assert ps.label == "foo"
    assert ps.file == "a.py"
    assert ps.line == 42
    assert ps.depth == 2
    assert ps.callers == ["n0"]
    assert ps.callees == ["n2", "n3"]


def test_processstep_defaults():
    ps = ProcessStep(node_id="n1", label="foo", file="a.py", line=0, depth=0)
    assert ps.callers == []
    assert ps.callees == []


def test_process_dataclass():
    ep = EntryPoint(name="main", kind="CLI", file="main.py", line=1, language="python")
    p = Process(
        name="main", entry_point=ep, total_steps=3, max_depth=2,
        language="python", cyclomatic_complexity=2, external_touches=1,
    )
    assert p.name == "main"
    assert p.entry_point == ep
    assert p.total_steps == 3
    assert p.max_depth == 2
    assert p.language == "python"
    assert p.cyclomatic_complexity == 2
    assert p.external_touches == 1


def test_process_defaults():
    ep = EntryPoint(name="main", kind="CLI", file="main.py", line=1, language="python")
    p = Process(name="main", entry_point=ep)
    assert p.steps == []
    assert p.total_steps == 0
    assert p.max_depth == 0
    assert p.framework == ""
    assert p.confidence == 1.0
    assert p.cyclomatic_complexity == 0
    assert p.external_touches == 0


def test_trace_process_simple_chain():
    G = _build_call_graph([("A", "B"), ("B", "C")])
    G.nodes["A"]["source_file"] = "entry.py"
    G.nodes["B"]["source_file"] = "entry.py"
    G.nodes["C"]["source_file"] = "other.py"

    ep = EntryPoint(name="A", kind="CLI", file="entry.py", line=1, language="python")
    proc = trace_process(ep, G)

    assert proc.total_steps == 3
    assert proc.max_depth == 2
    labels = [s.label for s in proc.steps]
    assert labels == ["A", "B", "C"]
    assert proc.steps[0].depth == 0
    assert proc.steps[1].depth == 1
    assert proc.steps[2].depth == 2
    assert proc.external_touches == 1


def test_trace_process_respects_max_depth():
    G = _build_call_graph([("A", "B"), ("B", "C"), ("C", "D"), ("D", "E")])
    G.nodes["A"]["source_file"] = "entry.py"
    for n in "ABCDE":
        G.nodes[n]["source_file"] = "entry.py"

    ep = EntryPoint(name="A", kind="CLI", file="entry.py", line=1, language="python")
    proc = trace_process(ep, G, max_depth=2)

    assert proc.total_steps == 3
    depths = [s.depth for s in proc.steps]
    assert max(depths) <= 2


def test_trace_process_respects_max_nodes():
    G = _build_call_graph([("A", "B"), ("B", "C"), ("C", "D"), ("D", "E")])

    ep = EntryPoint(name="A", kind="CLI", file="A.py", line=1, language="python")
    proc = trace_process(ep, G, max_nodes=2)

    assert proc.total_steps == 2


def test_trace_process_handles_cycles():
    G = _build_call_graph([("A", "B"), ("B", "A")])
    G.nodes["A"]["source_file"] = "cycle.py"
    G.nodes["B"]["source_file"] = "cycle.py"

    ep = EntryPoint(name="A", kind="CLI", file="cycle.py", line=1, language="python")
    proc = trace_process(ep, G)

    assert proc.total_steps == 2
    labels = {s.label for s in proc.steps}
    assert labels == {"A", "B"}


def test_trace_process_handles_callers_and_callees():
    G = nx.DiGraph()
    G.add_node("A", label="A", source_file="a.py", source_location="L1")
    G.add_node("B", label="B", source_file="b.py", source_location="L1")
    G.add_node("C", label="C", source_file="c.py", source_location="L1")
    G.add_edge("A", "B", relation="calls")
    G.add_edge("B", "C", relation="calls")

    ep = EntryPoint(name="A", kind="CLI", file="a.py", line=1, language="python")
    proc = trace_process(ep, G)

    assert proc.cyclomatic_complexity >= 1
    assert proc.total_steps == 3


def test_trace_process_non_call_edges_ignored():
    G = nx.DiGraph()
    G.add_node("A", label="A", source_file="a.py", source_location="L1")
    G.add_node("B", label="B", source_file="b.py", source_location="L1")
    G.add_node("C", label="C", source_file="c.py", source_location="L1")
    G.add_edge("A", "B", relation="calls")
    G.add_edge("B", "C", relation="references")

    ep = EntryPoint(name="A", kind="CLI", file="a.py", line=1, language="python")
    proc = trace_process(ep, G)

    assert proc.total_steps == 2
    assert "C" not in {s.label for s in proc.steps}


def test_trace_process_missing_start_node():
    G = _build_call_graph([("X", "Y")])

    ep = EntryPoint(name="Z", kind="CLI", file="nonexistent.py", line=1, language="python")
    proc = trace_process(ep, G)

    assert proc.total_steps == 0
    assert proc.name == "Z"


def test_trace_all_entry_points_returns_sorted():
    G = nx.DiGraph()
    G.add_node("A", label="A", source_file="a.py", source_location="L1")
    G.add_node("B", label="B", source_file="a.py", source_location="L5")
    G.add_node("C", label="C", source_file="c.py", source_location="L1")
    G.add_node("D", label="D", source_file="c.py", source_location="L5")
    G.add_node("E", label="E", source_file="c.py", source_location="L10")
    G.add_edge("A", "B", relation="calls")
    G.add_edge("C", "D", relation="calls")
    G.add_edge("D", "E", relation="calls")

    eps = [
        EntryPoint(name="A", kind="CLI", file="a.py", line=1, language="python"),
        EntryPoint(name="C", kind="CLI", file="c.py", line=1, language="python"),
    ]
    procs = trace_all_entry_points(eps, G)

    assert len(procs) == 2
    assert procs[0].total_steps >= procs[1].total_steps


def test_trace_all_entry_points_skips_empty():
    G = _build_call_graph([("A", "B")])

    eps = [
        EntryPoint(name="X", kind="CLI", file="nonexistent.py", line=1, language="python"),
    ]
    procs = trace_all_entry_points(eps, G)

    assert procs == []


def test_trace_changed_nodes_finds_affected():
    G = nx.DiGraph()
    G.add_node("root", label="root_handler", source_file="main.py", source_location="L1",
               node_type="function", language="python")
    G.add_node("mid", label="middleware", source_file="utils.py", source_location="L5",
               node_type="function", language="python")
    G.add_node("leaf", label="db_query", source_file="db.py", source_location="L10",
               node_type="function", language="python")
    G.add_edge("root", "mid", relation="calls")
    G.add_edge("mid", "leaf", relation="calls")

    procs = trace_changed_nodes(G, ["utils.py"])

    assert len(procs) >= 1


def test_trace_changed_nodes_no_matches():
    G = _build_call_graph([("A", "B")])

    procs = trace_changed_nodes(G, ["nonexistent.py"])

    assert procs == []


def test_trace_changed_nodes_finds_root_by_changed_file():
    G = nx.DiGraph()
    G.add_node("root", label="root", source_file="main.py", source_location="L1",
               node_type="function", language="python")
    G.add_node("child", label="child", source_file="main.py", source_location="L5",
               node_type="function", language="python")
    G.add_edge("root", "child", relation="calls")

    procs = trace_changed_nodes(G, ["main.py"])

    assert len(procs) >= 1
    names = {p.name for p in procs}
    assert "root" in names
