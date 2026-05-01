"""Tests for detect_changes MCP tool logic."""
import networkx as nx
from graphify.change_detect import (
    detect_changes,
    ChangeReport,
)


def _build_process_graph():
    G = nx.DiGraph()
    G.add_node("n_main", label="main", source_file="main.py",
               source_location="L1", file_type="code", node_type="function", language="python")
    G.add_node("n_auth", label="auth_login", source_file="auth.py",
               source_location="L12", file_type="code", node_type="function", language="python")
    G.add_node("n_db", label="db_connect", source_file="db.py",
               source_location="L5", file_type="code", node_type="function", language="python")
    G.add_node("n_cache", label="cache_store", source_file="cache.py",
               source_location="L8", file_type="code", node_type="function", language="python")
    G.add_node("n_log", label="log_request", source_file="log.py",
               source_location="L1", file_type="code", node_type="function", language="python")
    G.add_edge("n_main", "n_auth", relation="calls")
    G.add_edge("n_auth", "n_db", relation="calls")
    G.add_edge("n_auth", "n_cache", relation="calls")
    G.add_edge("n_main", "n_log", relation="calls")
    return G


def test_detect_changes_returns_report_with_required_fields():
    G = _build_process_graph()
    changed_files = ["auth.py", "db.py"]
    changed_lines = {"auth.py": [(6, 15)], "db.py": [(1, 10)]}

    report = detect_changes(G, changed_files=changed_files, changed_lines=changed_lines)

    assert isinstance(report, ChangeReport)
    assert hasattr(report, "risk_level")
    assert hasattr(report, "changed_symbols")
    assert hasattr(report, "affected_processes")
    assert hasattr(report, "recommendations")
    assert isinstance(report.risk_level, str)
    assert isinstance(report.changed_symbols, list)
    assert isinstance(report.affected_processes, list)
    assert isinstance(report.recommendations, list)


def test_detect_changes_finds_affected_symbols_for_changed_files():
    G = _build_process_graph()
    changed_files = ["auth.py"]
    changed_lines = {"auth.py": [(10, 15)]}

    report = detect_changes(G, changed_files=changed_files, changed_lines=changed_lines)

    assert len(report.changed_symbols) >= 1
    auth_symbols = [s for s in report.changed_symbols if s.file == "auth.py"]
    assert len(auth_symbols) >= 1


def test_detect_changes_with_no_changes():
    G = _build_process_graph()
    changed_files = []
    changed_lines = {}

    report = detect_changes(G, changed_files=changed_files, changed_lines=changed_lines)

    assert report.risk_level == "LOW"
    assert len(report.changed_symbols) == 0
    assert len(report.affected_processes) == 0


def test_detect_changes_summary_has_required_keys():
    G = _build_process_graph()
    changed_files = ["auth.py"]
    changed_lines = {"auth.py": [(10, 15)]}

    report = detect_changes(G, changed_files=changed_files, changed_lines=changed_lines)

    assert "changed_files" in report.summary
    assert "affected_symbols" in report.summary
    assert "affected_processes" in report.summary
    assert "risk_level" in report.summary


def test_detect_changes_finds_direct_and_indirect_symbols():
    G = _build_process_graph()
    changed_files = ["auth.py", "log.py"]
    changed_lines = {"auth.py": [(10, 15)], "log.py": [(1, 5)]}

    report = detect_changes(G, changed_files=changed_files, changed_lines=changed_lines)

    direct = [s for s in report.changed_symbols if s.direct]
    assert len(direct) >= 2


def test_detect_changes_generates_recommendations():
    G = _build_process_graph()
    changed_files = ["main.py", "auth.py", "db.py", "cache.py", "log.py"]
    changed_lines = {f: [(1, 10)] for f in changed_files}

    report = detect_changes(G, changed_files=changed_files, changed_lines=changed_lines)

    assert len(report.recommendations) > 0


def test_detect_changes_affected_processes_have_valid_data():
    G = _build_process_graph()
    changed_files = ["auth.py"]
    changed_lines = {"auth.py": [(10, 15)]}

    report = detect_changes(G, changed_files=changed_files, changed_lines=changed_lines)

    for proc in report.affected_processes:
        assert isinstance(proc.process_name, str)
        assert isinstance(proc.step_count, int)
        assert isinstance(proc.affected_steps, list)
        assert isinstance(proc.affected_nodes, list)
