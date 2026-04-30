"""Tests for graphify/processes.py - process tracing engine."""
from __future__ import annotations
import json
import pytest
import networkx as nx

from graphify.processes import (
    EntryPoint,
    Process,
    ProcessStep,
    detect_entry_points,
    trace_process,
    build_processes,
    cluster_processes,
    detect_changes,
    assess_risk,
    write_processes_json,
)


def _make_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node("n1", label="handle_root()", source_file="handlers.py",
               source_location="L10", node_type="FUNCTION", visibility="public")
    G.add_node("n2", label="AuthMiddleware", source_file="middleware.py",
               source_location="L5", node_type="CLASS")
    G.add_node("n2b", label="LoggerMiddleware", source_file="logging.py",
               source_location="L8", node_type="CLASS")
    G.add_node("n3", label="do_auth()", source_file="auth.py",
               source_location="L20", node_type="FUNCTION")
    G.add_node("n4", label="query_db()", source_file="db.py",
               source_location="L30", node_type="FUNCTION")
    G.add_node("n5", label="main()", source_file="main.py",
               source_location="L1", node_type="FUNCTION")
    G.add_node("n6", label="test_login()", source_file="test_auth.py",
               source_location="L5", node_type="FUNCTION")
    G.add_node("n7", label="cron_cleanup", source_file="tasks.py",
               source_location="L15", node_type="FUNCTION")
    G.add_node("n8", label="isolated_func()", source_file="util.py",
               source_location="L1", node_type="FUNCTION")
    G.add_node("n9", label="log_handler()", source_file="handlers.py",
               source_location="L25", node_type="FUNCTION")
    G.add_edge("n1", "n3", relation="calls", confidence="EXTRACTED",
               confidence_score=1.0)
    G.add_edge("n3", "n4", relation="calls", confidence="EXTRACTED",
               confidence_score=1.0)
    G.add_edge("n2", "n3", relation="calls", confidence="INFERRED",
               confidence_score=0.7)
    G.add_edge("n5", "n1", relation="calls", confidence="EXTRACTED",
               confidence_score=1.0)
    G.add_edge("n1", "n9", relation="calls", confidence="INFERRED",
               confidence_score=0.7)
    G.add_edge("n1", "n2", relation="handles_route", confidence="EXTRACTED",
               route="/root", method="GET")
    return G


def _make_cycle_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node("a", label="a()", source_file="a.py", source_location="L1",
               node_type="FUNCTION")
    G.add_node("b", label="b()", source_file="b.py", source_location="L1",
               node_type="FUNCTION")
    G.add_node("c", label="c()", source_file="c.py", source_location="L1",
               node_type="FUNCTION")
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED",
               confidence_score=1.0)
    G.add_edge("b", "c", relation="calls", confidence="EXTRACTED",
               confidence_score=1.0)
    G.add_edge("c", "a", relation="calls", confidence="EXTRACTED",
               confidence_score=1.0)
    return G


class TestDetectEntryPoints:
    def test_finds_route_handlers(self):
        G = _make_graph()
        entries = detect_entry_points(G)
        route_entries = [e for e in entries if e.kind == "route_handler"]
        assert len(route_entries) >= 1
        route = route_entries[0]
        assert route.node_id == "n1"
        assert route.route == "/root"
        assert route.method == "GET"

    def test_finds_cli_main(self):
        G = _make_graph()
        entries = detect_entry_points(G)
        main_entries = [e for e in entries if e.kind == "cli_main"]
        assert len(main_entries) >= 1
        assert any(e.node_id == "n5" for e in main_entries)

    def test_finds_tests(self):
        G = _make_graph()
        entries = detect_entry_points(G)
        test_entries = [e for e in entries if e.kind == "test"]
        assert len(test_entries) >= 1
        assert any(e.node_id == "n6" for e in test_entries)

    def test_finds_middleware(self):
        G = _make_graph()
        entries = detect_entry_points(G)
        mw = [e for e in entries if e.kind == "middleware"]
        assert len(mw) >= 1
        assert any("middleware" in e.label.lower() for e in mw)

    def test_finds_cron(self):
        G = _make_graph()
        entries = detect_entry_points(G)
        cron_entries = [e for e in entries if e.kind == "cron"]
        assert len(cron_entries) >= 1
        assert any(e.node_id == "n7" for e in cron_entries)

    def test_sorted_by_score_desc(self):
        G = _make_graph()
        entries = detect_entry_points(G)
        scores = [e.score for e in entries]
        assert scores == sorted(scores, reverse=True)


class TestTraceProcess:
    def test_follows_calls_edges(self):
        G = _make_graph()
        entry = EntryPoint(node_id="n5", label="main()", kind="cli_main",
                          score=7.0, file="main.py")
        proc = trace_process(G, entry, max_depth=20)
        nids = {s.node_id for s in proc.steps}
        assert "n5" in nids
        assert "n1" in nids
        assert "n3" in nids
        assert "n4" in nids
        assert "n9" in nids

    def test_handles_cycles(self):
        G = _make_cycle_graph()
        entry = EntryPoint(node_id="a", label="a()", kind="cli_main",
                          score=7.0, file="a.py")
        proc = trace_process(G, entry, max_depth=20)
        nids = {s.node_id for s in proc.steps}
        assert "a" in nids
        assert "b" in nids
        assert "c" in nids
        assert len(proc.steps) == 3

    def test_respects_max_depth(self):
        G = _make_graph()
        entry = EntryPoint(node_id="n5", label="main()", kind="cli_main",
                          score=7.0, file="main.py")
        proc = trace_process(G, entry, max_depth=1)
        nids = {s.node_id for s in proc.steps}
        assert "n5" in nids
        assert "n1" in nids
        assert "n3" not in nids

    def test_marks_branching(self):
        G = _make_graph()
        entry = EntryPoint(node_id="n5", label="main()", kind="cli_main",
                          score=7.0, file="main.py")
        proc = trace_process(G, entry, max_depth=20)
        for s in proc.steps:
            if s.node_id == "n1":
                assert s.is_branching is True


class TestBuildProcesses:
    def test_returns_processes(self):
        G = _make_graph()
        procs = build_processes(G)
        assert len(procs) > 0
        assert all(isinstance(p, Process) for p in procs)


class TestClusterProcesses:
    def test_deduplicates_overlapping(self):
        G = _make_graph()
        entry_a = EntryPoint(node_id="n1", label="handle_root()",
                            kind="route_handler", score=10.0, file="handlers.py")
        entry_b = EntryPoint(node_id="n5", label="main()", kind="cli_main",
                            score=7.0, file="main.py")
        proc_a = trace_process(G, entry_a, max_depth=20)
        proc_b = trace_process(G, entry_b, max_depth=20)
        clusters = cluster_processes([proc_a, proc_b])
        assert len(clusters) > 0

    def test_identical_processes_same_cluster(self):
        G = _make_graph()
        entry = EntryPoint(node_id="n5", label="main()", kind="cli_main",
                          score=7.0, file="main.py")
        proc_a = trace_process(G, entry, max_depth=20)
        proc_b = trace_process(G, entry, max_depth=20)
        clusters = cluster_processes([proc_a, proc_b])
        assert any(len(c) == 2 for c in clusters)

    def test_empty_returns_empty(self):
        assert cluster_processes([]) == []


class TestDetectChanges:
    def test_detects_changed_files(self):
        G = _make_graph()
        procs = build_processes(G)
        result = detect_changes(G, procs,
                               changed_files=["auth.py", "middleware.py"])
        assert result["summary"]["changed_count"] == 2
        assert result["summary"]["risk_level"] in ("LOW", "MEDIUM", "HIGH")
        assert len(result["changed_symbols"]) > 0
        assert len(result["recommendations"]) > 0

    def test_no_changes_defaults_to_empty(self):
        G = _make_graph()
        procs = build_processes(G)
        result = detect_changes(G, procs)
        assert result["summary"]["changed_count"] == 0
        assert result["summary"]["risk_level"] == "LOW"


class TestAssessRisk:
    def test_low_risk(self):
        assert assess_risk(2, 1) == "LOW"

    def test_medium_risk(self):
        assert assess_risk(10, 2) == "MEDIUM"

    def test_high_risk(self):
        assert assess_risk(30, 5) == "HIGH"

    def test_medium_risk_from_processes(self):
        assert assess_risk(1, 5) == "MEDIUM"


class TestWriteProcessesJson:
    def test_writes_file(self, tmp_path):
        G = _make_graph()
        procs = build_processes(G)
        out = tmp_path / "processes.json"
        write_processes_json(procs, str(out))
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) > 0
        assert "id" in data[0]
        assert "steps" in data[0]
