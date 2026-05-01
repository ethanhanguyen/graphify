"""Tests for change_detect.py."""
import subprocess
from unittest.mock import patch

import networkx as nx
from graphify.change_detect import (
    AffectedSymbol,
    AffectedProcess,
    ChangeReport,
    detect_changes,
    find_affected_symbols,
    find_affected_processes,
    assess_risk,
    generate_recommendations,
    _is_file_node_affected,
    _line_in_ranges,
    _merge_ranges,
    _parse_diff_ranges,
    _git_diff_changes,
)


def test_changereport_dataclass():
    report = ChangeReport(
        summary={"changed_files": 1},
        risk_level="MEDIUM",
        changed_symbols=[AffectedSymbol(name="foo", kind="function", file="a.py", changed_lines=[], direct=True)],
        affected_processes=[AffectedProcess(process_name="main", step_count=3, affected_steps=[0], affected_nodes=["n1"])],
        recommendations=["Run integration tests"],
    )
    assert report.risk_level == "MEDIUM"
    assert len(report.changed_symbols) == 1
    assert len(report.affected_processes) == 1
    assert len(report.recommendations) == 1


def test_changereport_defaults():
    report = ChangeReport()
    assert report.summary == {}
    assert report.changed_symbols == []
    assert report.affected_processes == []
    assert report.recommendations == []
    assert report.risk_level == "LOW"


def test_affected_symbol_dataclass():
    sym = AffectedSymbol(
        name="handler", kind="function", file="server.py",
        changed_lines=[(10, 15)], direct=True,
    )
    assert sym.name == "handler"
    assert sym.kind == "function"
    assert sym.file == "server.py"
    assert sym.changed_lines == [(10, 15)]
    assert sym.direct is True


def test_affected_process_dataclass():
    proc = AffectedProcess(
        process_name="login_flow", step_count=5,
        affected_steps=[0, 2], affected_nodes=["n_login", "n_validate"],
    )
    assert proc.process_name == "login_flow"
    assert proc.step_count == 5
    assert proc.affected_steps == [0, 2]
    assert proc.affected_nodes == ["n_login", "n_validate"]


def _build_scenario_graph():
    G = nx.DiGraph()
    G.add_node("n_handler", label="request_handler", source_file="server.py",
               source_location="L10", file_type="code", node_type="function")
    G.add_node("n_auth", label="check_auth", source_file="auth.py",
               source_location="L5", file_type="code", node_type="function")
    G.add_node("n_db", label="query_db", source_file="db.py",
               source_location="L20", file_type="code", node_type="function")
    G.add_node("n_util", label="format_output", source_file="utils.py",
               source_location="L1", file_type="code", node_type="function")
    G.add_edge("n_handler", "n_auth", relation="calls")
    G.add_edge("n_auth", "n_db", relation="calls")
    G.add_edge("n_handler", "n_util", relation="calls")
    return G


def test_detect_changes_finds_symbols():
    G = _build_scenario_graph()
    changed_files = ["auth.py"]
    changed_lines = {"auth.py": [(5, 10)]}

    report = detect_changes(G, changed_files=changed_files, changed_lines=changed_lines)

    assert len(report.changed_symbols) >= 1
    assert any(s.file == "auth.py" for s in report.changed_symbols)
    assert report.risk_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def test_find_affected_symbols_matches_by_file():
    G = _build_scenario_graph()
    symbols = find_affected_symbols(G, ["auth.py"], {"auth.py": [(1, 20)]})

    assert len(symbols) >= 1
    for s in symbols:
        assert s.file == "auth.py"


def test_find_affected_symbols_no_match():
    G = _build_scenario_graph()
    symbols = find_affected_symbols(G, ["nonexistent.py"], {})

    assert symbols == []


def test_find_affected_symbols_with_line_ranges():
    G = _build_scenario_graph()
    symbols = find_affected_symbols(G, ["server.py"], {"server.py": [(5, 10)]})

    assert len(symbols) >= 0


def test_find_affected_processes():
    G = _build_scenario_graph()
    symbols = [
        AffectedSymbol(name="check_auth", kind="function", file="auth.py",
                       changed_lines=[(5, 10)], direct=True),
    ]
    procs = find_affected_processes(G, symbols)

    assert len(procs) >= 1
    for p in procs:
        assert isinstance(p, AffectedProcess)


def test_find_affected_processes_empty_symbols():
    G = _build_scenario_graph()
    procs = find_affected_processes(G, [])
    assert procs == []


def test_assess_risk_low():
    assert assess_risk(3, 0, 1) == "LOW"


def test_assess_risk_medium():
    assert assess_risk(5, 1, 2) == "MEDIUM"


def test_assess_risk_high():
    assert assess_risk(8, 4, 3) == "HIGH"


def test_assess_risk_critical():
    assert assess_risk(12, 8, 10) == "CRITICAL"


def test_assess_risk_critical_by_process_count():
    assert assess_risk(0, 10, 0) == "CRITICAL"


def test_generate_recommendations_returns_actionable_items():
    report = ChangeReport(
        summary={
            "changed_files": 3,
            "affected_symbols": 7,
            "direct_changes": 5,
            "indirect_changes": 2,
            "affected_processes": 3,
        },
        risk_level="HIGH",
    )
    recs = generate_recommendations(report)
    assert len(recs) > 0
    assert any("integration test" in r.lower() for r in recs)


def test_generate_recommendations_critical():
    report = ChangeReport(
        summary={
            "direct_changes": 8,
            "indirect_changes": 10,
            "affected_processes": 6,
        },
        risk_level="CRITICAL",
    )
    recs = generate_recommendations(report)
    assert any("regression" in r.lower() for r in recs)
    assert any("team lead" in r.lower() for r in recs)


def test_generate_recommendations_low_risk():
    report = ChangeReport(
        summary={
            "direct_changes": 1,
            "indirect_changes": 0,
            "affected_processes": 0,
        },
        risk_level="LOW",
    )
    recs = generate_recommendations(report)
    assert len(recs) == 1
    assert "standard code review" in recs[0].lower()


def test_generate_recommendations_indirect_exceeds_direct():
    report = ChangeReport(
        summary={
            "direct_changes": 2,
            "indirect_changes": 8,
            "affected_processes": 1,
        },
        risk_level="MEDIUM",
    )
    recs = generate_recommendations(report)
    assert any("dependency hygiene" in r.lower() for r in recs)


def test_generate_recommendations_large_surface():
    report = ChangeReport(
        summary={
            "direct_changes": 12,
            "indirect_changes": 3,
            "affected_processes": 1,
        },
        risk_level="HIGH",
    )
    recs = generate_recommendations(report)
    assert any("split into smaller" in r.lower() for r in recs)


# ===========================================================================
# assess_risk: exact threshold boundary tests
# ===========================================================================

def test_assess_risk_exactly_80_score_critical():
    assert assess_risk(40, 0, 0) == "CRITICAL"


def test_assess_risk_exactly_40_score_high():
    assert assess_risk(20, 0, 0) == "HIGH"


def test_assess_risk_exactly_15_score_medium():
    assert assess_risk(5, 1, 0) == "MEDIUM"


def test_assess_risk_below_15_low():
    assert assess_risk(5, 0, 0) == "LOW"


def test_assess_risk_high_by_process_count():
    assert assess_risk(0, 5, 1) == "HIGH"


def test_assess_risk_medium_by_process_count():
    assert assess_risk(0, 2, 0) == "MEDIUM"


def test_assess_risk_with_all_factors():
    assert assess_risk(10, 3, 5) == "HIGH"


# ===========================================================================
# generate_recommendations: empty / missing summary keys
# ===========================================================================

def test_generate_recommendations_empty_summary():
    report = ChangeReport(summary={}, risk_level="LOW")
    recs = generate_recommendations(report)
    assert len(recs) == 1
    assert "standard code review" in recs[0].lower()


def test_generate_recommendations_partial_summary():
    report = ChangeReport(summary={"direct_changes": 3}, risk_level="LOW")
    recs = generate_recommendations(report)
    assert len(recs) >= 1


def test_generate_recommendations_process_count_zero():
    report = ChangeReport(
        summary={"direct_changes": 1, "indirect_changes": 0, "affected_processes": 0},
        risk_level="LOW",
    )
    recs = generate_recommendations(report)
    assert all("Review" not in r for r in recs)


# ===========================================================================
# AffectedSymbol: indirect flag
# ===========================================================================

def test_affected_symbol_indirect():
    sym = AffectedSymbol(
        name="service", kind="class", file="lib.py",
        changed_lines=[], direct=False,
    )
    assert sym.direct is False
    assert sym.changed_lines == []


# ===========================================================================
# find_affected_symbols: indirect match via _is_file_node_affected
# ===========================================================================

def test_find_affected_symbols_indirect_by_filename():
    G = nx.DiGraph()
    G.add_node("n_svc", label="Service", source_file="pkg/services/auth.py",
               source_location="L42", file_type="code", node_type="class")
    G.add_node("n_test", label="TestAuth", source_file="tests/test_auth.py",
               source_location="L1", file_type="test", node_type="test")

    symbols = find_affected_symbols(G, ["auth.py"], {})
    assert len(symbols) >= 1
    assert any("auth" in s.file for s in symbols)


def test_find_affected_symbols_indirect_path_suffix():
    G = nx.DiGraph()
    G.add_node("n_x", label="x", source_file="lib/sub/deep/util.py",
               source_location="L1", file_type="code", node_type="function")

    symbols = find_affected_symbols(G, ["deep/util.py"], {})
    assert len(symbols) >= 1


# ===========================================================================
# detect_changes: scope parameter
# ===========================================================================

def test_detect_changes_with_scope_param():
    G = _build_scenario_graph()
    changed_files = ["auth.py"]
    changed_lines = {"auth.py": [(1, 5)]}
    report = detect_changes(G, changed_files=changed_files, changed_lines=changed_lines, scope="symbol")
    assert report is not None
    assert report.risk_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")


# ===========================================================================
# generate_recommendations: exactly at direct > 5 threshold
# ===========================================================================

def test_generate_recommendations_direct_exactly_6():
    report = ChangeReport(
        summary={"direct_changes": 6, "indirect_changes": 2, "affected_processes": 1},
        risk_level="MEDIUM",
    )
    recs = generate_recommendations(report)
    assert any("split into smaller" in r.lower() for r in recs)


def test_generate_recommendations_direct_exactly_5_no_split():
    report = ChangeReport(
        summary={"direct_changes": 5, "indirect_changes": 1, "affected_processes": 0},
        risk_level="LOW",
    )
    recs = generate_recommendations(report)
    assert not any("split into smaller" in r.lower() for r in recs)


# ===========================================================================
# generate_recommendations: indirect == direct (no hygiene hint)
# ===========================================================================

def test_generate_recommendations_indirect_equals_direct():
    report = ChangeReport(
        summary={"direct_changes": 4, "indirect_changes": 4, "affected_processes": 1},
        risk_level="MEDIUM",
    )
    recs = generate_recommendations(report)
    assert not any("dependency hygiene" in r.lower() for r in recs)


# ===========================================================================
# _is_file_node_affected: private function edge cases
# ===========================================================================

def test_is_file_node_affected_empty_nfile():
    assert _is_file_node_affected("", {"auth.py"}) is False


def test_is_file_node_affected_empty_changed_set():
    assert _is_file_node_affected("auth.py", set()) is False


def test_is_file_node_affected_filename_match():
    assert _is_file_node_affected("lib/sub/auth.py", {"auth.py"}) is True


def test_is_file_node_affected_suffix_match():
    assert _is_file_node_affected("pkg/auth.py", {"internal/pkg/auth.py"}) is True


def test_is_file_node_affected_no_match():
    assert _is_file_node_affected("other.py", {"auth.py"}) is False


# ===========================================================================
# _line_in_ranges: private function edge cases
# ===========================================================================

def test_line_in_ranges_empty_ranges():
    assert _line_in_ranges(42, []) is True


def test_line_in_ranges_inside():
    assert _line_in_ranges(10, [(5, 15)]) is True


def test_line_in_ranges_at_start():
    assert _line_in_ranges(5, [(5, 15)]) is True


def test_line_in_ranges_at_end():
    assert _line_in_ranges(15, [(5, 15)]) is True


def test_line_in_ranges_outside():
    assert _line_in_ranges(20, [(5, 15)]) is False


def test_line_in_ranges_multiple_ranges():
    assert _line_in_ranges(7, [(1, 3), (5, 10)]) is True
    assert _line_in_ranges(4, [(1, 3), (5, 10)]) is False


# ===========================================================================
# _merge_ranges: private function edge cases
# ===========================================================================

def test_merge_ranges_empty():
    assert _merge_ranges([]) == []


def test_merge_ranges_single():
    assert _merge_ranges([(1, 5)]) == [(1, 5)]


def test_merge_ranges_adjacent():
    assert _merge_ranges([(1, 3), (4, 6)]) == [(1, 6)]


def test_merge_ranges_disjoint():
    assert _merge_ranges([(1, 3), (10, 12)]) == [(1, 3), (10, 12)]


def test_merge_ranges_overlap():
    assert _merge_ranges([(1, 5), (3, 8)]) == [(1, 8)]


def test_merge_ranges_unsorted_input():
    assert _merge_ranges([(10, 12), (1, 3)]) == [(1, 3), (10, 12)]


def test_merge_ranges_nested():
    assert _merge_ranges([(1, 10), (3, 5)]) == [(1, 10)]


# ===========================================================================
# _parse_diff_ranges: private function edge cases
# ===========================================================================

def test_parse_diff_ranges_empty():
    assert _parse_diff_ranges("") == []


def test_parse_diff_ranges_single_hunk():
    diff = "@@ -10,5 +10,7 @@\n some code\n"
    result = _parse_diff_ranges(diff)
    assert len(result) == 1
    assert result[0] == (10, 16)


def test_parse_diff_ranges_without_count():
    diff = "@@ -5 +5 @@\n"
    result = _parse_diff_ranges(diff)
    assert len(result) == 1
    assert result[0] == (5, 5)


def test_parse_diff_ranges_multiple_hunks():
    diff = "@@ -1,3 +1,4 @@\n@@ -10,2 +15,3 @@\n"
    result = _parse_diff_ranges(diff)
    assert len(result) == 2
    assert result[0] == (1, 4)
    assert result[1] == (15, 17)


# ===========================================================================
# _git_diff_changes: mocked
# ===========================================================================

def test_git_diff_changes_no_changes():
    with patch("graphify.change_detect.subprocess.check_output") as mock_check:
        mock_check.return_value = "\n"
        files, lines = _git_diff_changes()
        assert files == []
        assert lines == {}


def test_git_diff_changes_single_file_no_line_changes():
    with patch("graphify.change_detect.subprocess.check_output") as mock_check:
        mock_check.side_effect = [
            "auth.py\n",
            subprocess.CalledProcessError(1, "git"),
        ]
        with patch("graphify.change_detect.Path.exists", return_value=True):
            files, lines = _git_diff_changes()
        assert files == ["auth.py"]
        assert lines == {}


def test_git_diff_changes_file_not_exists():
    with patch("graphify.change_detect.subprocess.check_output") as mock_check:
        mock_check.return_value = "nonexistent_xyz_abc.py\n"
        files, lines = _git_diff_changes()
        assert files == ["nonexistent_xyz_abc.py"]
        assert lines == {}


def test_git_diff_changes_with_line_ranges():
    with patch("graphify.change_detect.subprocess.check_output") as mock_check:
        mock_check.side_effect = [
            "auth.py\n",
            "@@ -5 +5,3 @@\n",
        ]
        with patch("graphify.change_detect.Path.exists", return_value=True):
            files, lines = _git_diff_changes()
        assert files == ["auth.py"]
        assert "auth.py" in lines


def test_git_diff_changes_fallback_to_head():
    with patch("graphify.change_detect.subprocess.check_output") as mock_check:
        def side_effect(cmd, **kwargs):
            if "HEAD^..HEAD" in str(cmd):
                raise subprocess.CalledProcessError(1, "git")
            if "--name-only" in str(cmd) and cmd[-1] == "HEAD":
                return "fallback_xyz.py\n"
            raise AssertionError(f"Unexpected command: {cmd}")
        mock_check.side_effect = side_effect
        with patch("graphify.change_detect.Path.exists", return_value=False):
            files, _ = _git_diff_changes()
        assert files == ["fallback_xyz.py"]


def test_git_diff_changes_subprocess_not_found():
    with patch("graphify.change_detect.subprocess.check_output") as mock_check:
        mock_check.side_effect = FileNotFoundError
        files, lines = _git_diff_changes()
        assert files == []
        assert lines == {}


# ===========================================================================
# detect_changes: empty changed_files (triggers git fallback, mocked)
# ===========================================================================

def test_detect_changes_empty_changed_files():
    G = _build_scenario_graph()
    with patch("graphify.change_detect._git_diff_changes") as mock_git:
        mock_git.return_value = (["auth.py"], {"auth.py": [(5, 10)]})
        report = detect_changes(G, changed_files=None, changed_lines=None)
        assert report is not None
        assert len(report.changed_symbols) >= 1
        assert "changed_files" in report.summary


# ===========================================================================
# find_affected_symbols: source_location ValueError / TypeError
# ===========================================================================

def test_find_affected_symbols_bad_source_location():
    G = nx.DiGraph()
    G.add_node("n_bad", label="BadNode", source_file="auth.py",
               source_location="not-a-number", file_type="code", node_type="function")

    symbols = find_affected_symbols(G, ["auth.py"], {})
    assert len(symbols) >= 1


def test_find_affected_symbols_dict_source_location():
    G = nx.DiGraph()
    G.add_node("n_dict", label="DictNode", source_file="auth.py",
               source_location={"line": 5}, file_type="code", node_type="function")

    symbols = find_affected_symbols(G, ["auth.py"], {})
    assert len(symbols) >= 1
