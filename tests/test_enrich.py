from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
from graphify.build import enrich_by_language, build_from_json

FIXTURES = Path(__file__).parent / "fixtures"


def _ext_a():
    return {
        "nodes": [
            {"id": "n_foo_func", "label": "foo()", "file_type": "code", "source_file": "a.py", "source_location": "L1", "node_type": "function", "language": "python"},
            {"id": "n_bar_func", "label": "bar()", "file_type": "code", "source_file": "a.py", "source_location": "L5", "node_type": "function", "language": "python"},
            {"id": "n_file_a", "label": "a.py", "file_type": "code", "source_file": "a.py", "source_location": "", "node_type": "file", "language": "python"},
        ],
        "edges": [
            {"source": "n_bar_func", "target": "n_foo_func", "relation": "calls", "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": "a.py", "source_location": "L6", "weight": 1.0},
        ],
        "raw_calls": [
            {"caller_nid": "n_bar_func", "callee": "foo", "source_file": "a.py", "source_location": "L6", "is_member_call": False, "caller_label": "bar()"},
        ],
    }


def _ext_b():
    return {
        "nodes": [
            {"id": "n_main_func", "label": "main()", "file_type": "code", "source_file": "b.py", "source_location": "L1", "node_type": "function", "language": "python"},
            {"id": "n_file_b", "label": "b.py", "file_type": "code", "source_file": "b.py", "source_location": "", "node_type": "file", "language": "python"},
        ],
        "edges": [
            {"source": "n_main_func", "target": "n_bar_func", "relation": "calls", "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": "b.py", "source_location": "L2", "weight": 1.0},
            {"source": "n_file_b", "target": "n_file_a", "relation": "imports", "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": "b.py", "weight": 1.0},
        ],
        "raw_calls": [
            {"caller_nid": "n_main_func", "callee": "bar", "source_file": "b.py", "source_location": "L2", "is_member_call": False, "caller_label": "main()"},
        ],
    }


def _merged_extraction():
    return {
        "nodes": _ext_a()["nodes"] + _ext_b()["nodes"],
        "edges": _ext_a()["edges"] + _ext_b()["edges"],
    }


def test_enrich_by_language_adds_calls_edges():
    G = build_from_json(_merged_extraction())
    edges_before = G.number_of_edges()

    files = [Path("a.py"), Path("b.py")]
    exts = [_ext_a(), _ext_b()]
    G = enrich_by_language(G, files, exts)

    assert G.number_of_edges() >= edges_before
    crs = G.graph.get("call_resolution_stats", {})
    assert crs.get("resolved", 0) > 0


def test_enrich_by_language_skips_unknown_language():
    G = build_from_json(_merged_extraction())

    files = [Path("test.xyz")]
    G = enrich_by_language(G, files, [_ext_a()])

    crs = G.graph.get("call_resolution_stats", {})
    assert crs.get("skipped", {}).get("unknown", 0) > 0


def test_enrich_by_language_preserves_existing_edges():
    G = build_from_json(_merged_extraction())
    edges_before = set()
    for u, v in G.edges():
        edges_before.add((u, v))

    G = enrich_by_language(G, [], [])

    edges_after = set()
    for u, v in G.edges():
        edges_after.add((u, v))
    assert edges_before.issubset(edges_after)


def test_enrich_by_language_records_call_stats():
    G = build_from_json(_merged_extraction())
    files = [Path("a.py"), Path("b.py")]
    exts = [_ext_a(), _ext_b()]
    G = enrich_by_language(G, files, exts)

    crs = G.graph.get("call_resolution_stats", {})
    assert "resolved" in crs
    assert "total" in crs
    assert crs["resolved"] <= crs["total"]


def test_enrich_by_language_process_stats_structured():
    G = build_from_json(_merged_extraction())
    files = [Path("a.py"), Path("b.py")]
    exts = [_ext_a(), _ext_b()]
    G = enrich_by_language(G, files, exts)

    ps = G.graph.get("process_stats", {})
    assert "traced" in ps
    assert "total_steps" in ps
    assert ps["traced"] >= 0


def test_enrich_by_language_adds_step_in_process_edges():
    G = build_from_json(_merged_extraction())
    files = [Path("a.py"), Path("b.py")]
    exts = [_ext_a(), _ext_b()]
    G = enrich_by_language(G, files, exts)

    step_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("relation") == "step_in_process"]
    if step_edges:
        for u, v in step_edges:
            d = G.get_edge_data(u, v)
            assert isinstance(d, dict)
            assert d.get("confidence") == "INFERRED"
            assert d.get("confidence_score") == 0.8


def test_enrich_by_language_empty_inputs():
    G = nx.Graph()
    G = enrich_by_language(G, [], [])
    assert G.number_of_nodes() == 0
    assert G.number_of_edges() == 0


def test_enrich_by_language_skips_over_max_files():
    G = build_from_json(_merged_extraction())
    files = [Path(f"f{i}.py") for i in range(10001)]
    exts = [_ext_a()] * 10001
    G = enrich_by_language(G, files, exts)

    crs = G.graph.get("call_resolution_stats", {})
    assert crs.get("skipped", {}).get("python", 0) > 0
