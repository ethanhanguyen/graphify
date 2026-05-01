from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from graphify.call_dag import (
    CallEdge,
    CallResolutionDAG,
    run_call_resolution,
)
from graphify.code_schema import ConfidenceTier


def _extraction(nodes=None, edges=None):
    return {
        "nodes": nodes or [
            {"id": "n_main", "label": "main()", "file_type": "code", "source_file": "test.py"},
            {"id": "n_worker", "label": "Worker.run()", "file_type": "code", "source_file": "test.py"},
        ],
        "edges": edges or [
            {"source": "n_main", "target": "n_worker", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "test.py", "source_location": "L3", "weight": 1.0},
        ],
    }


class TestCallEdge:
    def test_dataclass_creation(self):
        edge = CallEdge(
            source="n_a",
            target="n_b",
            confidence=ConfidenceTier.INFERRED,
            confidence_score=0.8,
            source_file="test.py",
            source_location="L10",
        )
        assert edge.source == "n_a"
        assert edge.target == "n_b"
        assert edge.confidence == ConfidenceTier.INFERRED
        assert edge.confidence_score == 0.8

    def test_defaults(self):
        edge = CallEdge(source="n_a", target="n_b")
        assert edge.confidence == ConfidenceTier.EXTRACTED
        assert edge.confidence_score == 1.0
        assert edge.source_file == ""


class TestCallResolutionDAG:
    def test_initialization(self):
        dag = CallResolutionDAG([Path("a.py")], [_extraction()], "python")
        assert dag.language == "python"
        assert len(dag.files) == 1
        assert dag.call_sites == []
        assert dag.edges == []

    def test_stage_extract(self):
        dag = CallResolutionDAG([Path("test.py")], [_extraction()], "python")
        dag.stage_extract()
        assert dag.stats["extract"] > 0
        assert len(dag.call_sites) > 0

    def test_stage_extract_skips_errors(self):
        dag = CallResolutionDAG(
            [Path("bad.py")],
            [{"error": "parse failed"}],
            "python",
        )
        dag.stage_extract()
        assert dag.stats["extract"] == 0

    def test_stage_classify(self):
        dag = CallResolutionDAG([Path("test.py")], [_extraction()], "python")
        dag.stage_extract()
        dag.stage_classify()
        assert dag.stats["classify"] > 0
        assert len(dag.classified) > 0

    def test_stage_classify_constructor(self):
        nodes = [
            {"id": "n_main", "label": "main()", "file_type": "code", "source_file": "test.py"},
            {"id": "n_Foo", "label": "Foo", "file_type": "code", "source_file": "test.py"},
        ]
        edges = [
            {"source": "n_main", "target": "n_Foo", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "test.py", "source_location": "L1", "weight": 1.0},
        ]
        dag = CallResolutionDAG([Path("test.py")], [{"nodes": nodes, "edges": edges}], "python")
        dag.stage_extract()
        dag.stage_classify()
        assert dag.stats.get("classify_constructor", 0) > 0

    def test_stage_classify_method(self):
        nodes = [
            {"id": "n_main", "label": "main()", "file_type": "code", "source_file": "test.py"},
            {"id": "n_m", "label": "obj.method()", "file_type": "code", "source_file": "test.py"},
        ]
        edges = [
            {"source": "n_main", "target": "n_m", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "test.py", "source_location": "L2", "weight": 1.0},
        ]
        dag = CallResolutionDAG([Path("test.py")], [{"nodes": nodes, "edges": edges}], "python")
        dag.stage_extract()
        dag.stage_classify()
        assert dag.stats.get("classify_method", 0) > 0

    def test_stage_infer_receiver(self):
        dag = CallResolutionDAG([Path("test.py")], [_extraction()], "python")
        dag.stage_extract()
        dag.stage_classify()
        dag.stage_infer_receiver()
        assert dag.stats["infer_receiver"] >= 0

    def test_stage_resolve_target(self):
        nodes = [
            {"id": "n_main", "label": "main()", "file_type": "code", "source_file": "test.py"},
            {"id": "n_worker", "label": "worker()", "file_type": "code", "source_file": "test.py"},
        ]
        edges = [
            {"source": "n_main", "target": "n_worker", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "test.py", "source_location": "L3", "weight": 1.0},
        ]
        ext = {"nodes": nodes, "edges": edges}
        dag = CallResolutionDAG([Path("test.py")], [ext], "python")
        dag.stage_extract()
        dag.stage_classify()
        dag.stage_infer_receiver()
        dag.stage_select_dispatch()
        dag.stage_resolve_target()
        assert dag.stats["resolve_target"] > 0

    def test_run_returns_edges_and_stats(self):
        dag = CallResolutionDAG([Path("test.py")], [_extraction()], "python")
        edges, stats = dag.run()
        assert isinstance(edges, list)
        assert isinstance(stats, dict)
        assert "extract" in stats

    def test_run_call_resolution(self):
        files = [Path("test.py")]
        extractions = [_extraction()]
        edges, stats = run_call_resolution(files, extractions, "python")
        assert isinstance(edges, list)
        assert isinstance(stats, dict)

    def test_multiple_files(self):
        nodes_a = [
            {"id": "n_a_main", "label": "a_main()", "file_type": "code", "source_file": "a.py"},
            {"id": "n_a_helper", "label": "helper()", "file_type": "code", "source_file": "a.py"},
        ]
        edges_a = [
            {"source": "n_a_main", "target": "n_a_helper", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "a.py", "source_location": "L1", "weight": 1.0},
        ]
        nodes_b = [
            {"id": "n_b_main", "label": "b_main()", "file_type": "code", "source_file": "b.py"},
        ]
        edges_b = [
            {"source": "n_b_main", "target": "n_a_helper", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "b.py", "source_location": "L5", "weight": 1.0},
        ]
        files = [Path("a.py"), Path("b.py")]
        extractions = [
            {"nodes": nodes_a, "edges": edges_a},
            {"nodes": nodes_b, "edges": edges_b},
        ]
        edges, stats = run_call_resolution(files, extractions, "python")
        assert stats["extract"] > 0

    def test_edges_are_call_edge_dicts(self):
        dag = CallResolutionDAG([Path("test.py")], [_extraction()], "python")
        edges, _ = dag.run()
        for e in edges:
            assert "source" in e
            assert "target" in e
            assert "relation" in e
            assert e["relation"] == "calls"

    def test_stage_emit_edge_dedup(self):
        dag = CallResolutionDAG([Path("test.py")], [_extraction()], "python")
        dag.stage_extract()
        dag.stage_classify()
        dag.stage_infer_receiver()
        dag.stage_select_dispatch()
        dag.stage_resolve_target()
        edges1 = dag.stage_emit_edge()
        edges2 = dag.stage_emit_edge()
        assert edges1 == edges2

    def test_self_calls_filtered(self):
        nodes = [
            {"id": "n_rec", "label": "recurse()", "file_type": "code", "source_file": "test.py"},
        ]
        edges_in = [
            {"source": "n_rec", "target": "n_rec", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "test.py", "source_location": "L7", "weight": 1.0},
        ]
        ext = {"nodes": nodes, "edges": edges_in}
        dag = CallResolutionDAG([Path("test.py")], [ext], "python")
        edges, _ = dag.run()
        for e in edges:
            assert e["source"] != e["target"]

    def test_java_extraction(self):
        nodes = [
            {"id": "n_main", "label": "main()", "file_type": "code", "source_file": "App.java"},
            {"id": "n_service", "label": "Service.process()", "file_type": "code", "source_file": "App.java"},
        ]
        edges = [
            {"source": "n_main", "target": "n_service", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "App.java", "source_location": "L10", "weight": 1.0},
        ]
        ext = {"nodes": nodes, "edges": edges}
        dag = CallResolutionDAG([Path("App.java")], [ext], "java")
        edges, stats = dag.run()
        assert isinstance(edges, list)

    def test_go_extraction(self):
        nodes = [
            {"id": "n_main", "label": "main()", "file_type": "code", "source_file": "main.go"},
            {"id": "n_helper", "label": "helper()", "file_type": "code", "source_file": "main.go"},
        ]
        edges = [
            {"source": "n_main", "target": "n_helper", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "main.go", "source_location": "L3", "weight": 1.0},
        ]
        ext = {"nodes": nodes, "edges": edges}
        dag = CallResolutionDAG([Path("main.go")], [ext], "go")
        edges, stats = dag.run()
        assert isinstance(edges, list)

    def test_typescript_extraction(self):
        nodes = [
            {"id": "n_main", "label": "main()", "file_type": "code", "source_file": "index.ts"},
            {"id": "n_util", "label": "util()", "file_type": "code", "source_file": "index.ts"},
        ]
        edges = [
            {"source": "n_main", "target": "n_util", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "index.ts", "source_location": "L1", "weight": 1.0},
        ]
        ext = {"nodes": nodes, "edges": edges}
        dag = CallResolutionDAG([Path("index.ts")], [ext], "typescript")
        edges, stats = dag.run()
        assert isinstance(edges, list)

def test_classify_self_receiver():
    from graphify.call_extractors import ExtractedCallSite
    nodes = [{"id": "n_main", "label": "main()", "file_type": "code", "source_file": "test.py"}]
    ext = {"nodes": nodes, "edges": []}
    dag = CallResolutionDAG([Path("test.py")], [ext], "python")
    cs = ExtractedCallSite(
        caller_nid="n_main", caller_file="test.py",
        callee_name="helper", callee_receiver="self",
        is_constructor=False, arity=0, source_location="L5", confidence=1.0
    )
    dag.call_sites = [cs]
    dag.stage_classify()
    assert dag.stats.get("classify_direct", 0) >= 1

def test_classify_anonymous():
    from graphify.call_extractors import ExtractedCallSite
    nodes = [{"id": "n_main", "label": "main()", "file_type": "code", "source_file": "test.py"}]
    ext = {"nodes": nodes, "edges": []}
    dag = CallResolutionDAG([Path("test.py")], [ext], "python")
    cs = ExtractedCallSite(
        caller_nid="n_main", caller_file="test.py",
        callee_name="", callee_receiver="",
        is_constructor=False, arity=0, source_location="L5", confidence=1.0
    )
    dag.call_sites = [cs]
    dag.stage_classify()
    assert dag.stats.get("classify_anonymous", 0) >= 1

def test_classify_dotted_method():
    from graphify.call_extractors import ExtractedCallSite
    nodes = [{"id": "n_main", "label": "main()", "file_type": "code", "source_file": "test.py"}]
    ext = {"nodes": nodes, "edges": []}
    dag = CallResolutionDAG([Path("test.py")], [ext], "python")
    cs = ExtractedCallSite(
        caller_nid="n_main", caller_file="test.py",
        callee_name="obj.method", callee_receiver="",
        is_constructor=False, arity=0, source_location="L5", confidence=1.0
    )
    dag.call_sites = [cs]
    dag.stage_classify()
    assert dag.stats.get("classify_method", 0) >= 1

def test_resolve_target_with_imports():
    nodes_a = [
        {"id": "n_a_main", "label": "main()", "file_type": "code", "source_file": "a.py"},
    ]
    edges_a = [
        {"source": "n_a_main", "target": "b_helper", "relation": "imports_from",
         "confidence": "EXTRACTED", "source_file": "a.py", "source_location": "L1", "weight": 1.0},
        {"source": "n_a_main", "target": "helper", "relation": "calls",
         "confidence": "EXTRACTED", "source_file": "a.py", "source_location": "L2", "weight": 1.0},
    ]
    nodes_b = [
        {"id": "n_b_helper", "label": "helper()", "file_type": "code", "source_file": "b.py"},
    ]
    edges_b = []
    files = [Path("a.py"), Path("b.py")]
    extractions = [
        {"nodes": nodes_a, "edges": edges_a},
        {"nodes": nodes_b, "edges": edges_b},
    ]
    dag = CallResolutionDAG(files, extractions, "python")
    dag.stage_extract()
    dag.stage_classify()
    dag.stage_infer_receiver()
    dag.stage_select_dispatch()
    dag.stage_resolve_target()
    assert dag.stats["resolve_target"] >= 0

def test_resolve_global_fallback():
    nodes_a = [
        {"id": "n_a_caller", "label": "caller()", "file_type": "code", "source_file": "a.py"},
    ]
    edges_a = [
        {"source": "n_a_caller", "target": "remote", "relation": "calls",
         "confidence": "EXTRACTED", "source_file": "a.py", "source_location": "L2", "weight": 1.0},
    ]
    nodes_b = [
        {"id": "n_b_remote", "label": "remote()", "file_type": "code", "source_file": "b.py"},
    ]
    edges_b = []
    files = [Path("a.py"), Path("b.py")]
    extractions = [
        {"nodes": nodes_a, "edges": edges_a},
        {"nodes": nodes_b, "edges": edges_b},
    ]
    dag = CallResolutionDAG(files, extractions, "python")
    dag.stage_extract()
    dag.stage_classify()
    dag.stage_infer_receiver()
    dag.stage_select_dispatch()
    dag.stage_resolve_target()
    assert dag.stats["resolve_target"] >= 0

def test_emit_edge_handles_duplicate():
    nodes = [
        {"id": "n_main", "label": "main()", "file_type": "code", "source_file": "test.py"},
        {"id": "n_sub", "label": "sub()", "file_type": "code", "source_file": "test.py"},
    ]
    edges = [
        {"source": "n_main", "target": "n_sub", "relation": "calls",
         "confidence": "EXTRACTED", "source_file": "test.py", "source_location": "L1", "weight": 1.0},
    ]
    ext = {"nodes": nodes, "edges": edges}
    dag = CallResolutionDAG([Path("test.py")], [ext], "python")
    dag.edges = [
        CallEdge(source="n_main", target="n_sub", confidence=ConfidenceTier.EXTRACTED,
                 confidence_score=1.0, source_file="test.py", source_location="L1"),
        CallEdge(source="n_main", target="n_sub", confidence=ConfidenceTier.EXTRACTED,
                 confidence_score=1.0, source_file="test.py", source_location="L1"),
    ]
    result = dag.stage_emit_edge()
    assert len(result) == 1

def test_resolve_target_mro_path():
    from graphify.mro import NoneMRO
    nodes = [
        {"id": "n_caller", "label": "this.run()", "file_type": "code", "source_file": "test.py"},
        {"id": "n_base_worker", "label": "Base.worker()", "file_type": "code", "source_file": "test.py"},
    ]
    edges = [
        {"source": "n_caller", "target": "worker", "relation": "calls",
         "confidence": "EXTRACTED", "source_file": "test.py", "source_location": "L1", "weight": 1.0},
    ]
    ext = {"nodes": nodes, "edges": edges}
    dag = CallResolutionDAG([Path("test.py")], [ext], "python")
    dag.stage_extract()
    dag.stage_classify()
    dag.stage_infer_receiver()
    dag._mro_strategy = NoneMRO()
    dag._class_hierarchy = {"Base": ["Object"]}
    dag.stage_select_dispatch()
    if dag.call_sites:
        dag.call_sites[0].callee_receiver = "Base"
    dag.stage_resolve_target()
    assert dag.stats["select_dispatch"] >= 1
