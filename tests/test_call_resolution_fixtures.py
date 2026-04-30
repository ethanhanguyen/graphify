"""Integration tests for call resolution using fixture repos."""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.imports import ImportSemantics, ImportTarget, resolve_import
from graphify.receiver import ExtractedCallSite, infer_receiver, is_constructor_call
from graphify.mro import MROStrategy, MRO_FOR_LANGUAGE
from graphify.call_dag import resolve_call_graph, emit_call_edges, ResolvedCall
from graphify.build import build_from_json

FIXTURES = Path(__file__).parent / "fixtures" / "call_resolution"


class TestPythonFixtureCalls:
    def test_resolve_python_calls(self):
        py_fixture = FIXTURES / "python"
        files = list(py_fixture.glob("*.py"))
        assert len(files) > 0, "No fixture files found"

        extraction = {
            "nodes": [
                {"id": "helper_func", "label": "helper_func()", "node_type": "FUNCTION",
                 "source_file": str(files[0])},
                {"id": "Calculator", "label": "Calculator", "node_type": "CLASS",
                 "source_file": str(files[0])},
                {"id": "AdvancedCalc", "label": "AdvancedCalc", "node_type": "CLASS",
                 "source_file": str(files[0])},
            ],
            "edges": [],
        }
        G = build_from_json(extraction)

        resolved, unresolved = resolve_call_graph(files, G)
        assert isinstance(resolved, list)
        assert isinstance(unresolved, int)

    def test_fixture_files_exist(self):
        python_fixtures = list((FIXTURES / "python").glob("*.py"))
        ts_fixtures = list((FIXTURES / "typescript").glob("*.ts"))
        assert len(python_fixtures) > 0, "Python fixtures missing"
        assert len(ts_fixtures) > 0, "TypeScript fixtures missing"


class TestResolveCrossFileCalls:
    def test_resolve_cross_file_python_imports(self, tmp_path):
        mod_file = tmp_path / "utils.py"
        mod_file.write_text("def helper(): pass")
        caller = tmp_path / "main.py"
        caller.write_text("from utils import helper")
        files = [mod_file, caller]

        target = resolve_import("utils.helper", caller, files, ImportSemantics.NAMED, "python")
        assert target is not None
        assert target.symbol == "helper"

    def test_resolve_typescript_calls(self):
        ts_fixture = FIXTURES / "typescript"
        files = list(ts_fixture.glob("*.ts"))
        assert len(files) > 0

        result = resolve_import(
            "service", files[0], files, ImportSemantics.NAMED, "typescript"
        )
        assert result is not None


class TestReceiverInferenceIntegration:
    def test_resolve_method_chains(self):
        call = ExtractedCallSite(
            name="doWork", receiver="self", arity=0, line=10,
            in_class="my_service"
        )
        graph_nodes = {"my_service": {"label": "MyService", "node_type": "CLASS"}}
        receiver = infer_receiver(call, "my_service", graph_nodes)
        assert receiver == "my_service"

        parent_call = ExtractedCallSite(
            name="doWork", receiver="super", arity=0, line=20,
            in_class="child_service"
        )
        graph_nodes_with_parent = {
            "child_service": {"label": "ChildService", "node_type": "CLASS", "extends": "parent_service"},
            "parent_service": {"label": "ParentService", "node_type": "CLASS"},
        }
        parent_receiver = infer_receiver(parent_call, "child_service", graph_nodes_with_parent)
        assert parent_receiver == "parent_service"


class TestUnresolvedCount:
    def test_unresolved_count(self):
        extraction = {"nodes": [], "edges": []}
        G = build_from_json(extraction)

        resolved, unresolved = resolve_call_graph([], G)
        assert resolved == []
        assert unresolved == 0


class TestEmitCallEdges:
    def test_emit_call_edges(self):
        resolved = [
            ResolvedCall(
                caller_id="calc_compute",
                callee_id="helper_func",
                call_site_line=20,
                edge_type="calls",
                confidence="EXTRACTED",
                resolution_steps=["extract", "local_lookup"],
            ),
            ResolvedCall(
                caller_id="calc_compute",
                callee_id="calc_add",
                call_site_line=21,
                edge_type="calls",
                confidence="EXTRACTED",
                resolution_steps=["extract", "local_lookup"],
            ),
        ]
        edges = emit_call_edges(resolved)
        assert len(edges) == 2
        assert edges[0]["source"] == "calc_compute"
        assert edges[0]["target"] == "helper_func"
        assert edges[0]["relation"] == "calls"
        assert edges[0]["confidence"] == "EXTRACTED"
        assert edges[0]["confidence_score"] == 1.0

    def test_emit_call_edges_skips_unknown(self):
        resolved = [
            ResolvedCall(
                caller_id="unknown",
                callee_id="some_target",
                call_site_line=10,
            ),
            ResolvedCall(
                caller_id="func_a",
                callee_id="func_b",
                call_site_line=15,
                confidence="INFERRED",
            ),
        ]
        edges = emit_call_edges(resolved)
        assert len(edges) == 1
        assert edges[0]["confidence"] == "INFERRED"
        assert edges[0]["confidence_score"] == 0.7


class TestExtractedCallSite:
    def test_extracted_call_site_defaults(self):
        call = ExtractedCallSite(name="foo")
        assert call.name == "foo"
        assert call.receiver is None
        assert call.arity == 0
        assert call.line == 0
        assert call.in_class is None
        assert call.is_dynamic is False
        assert call.full_call_text == ""


class TestImportResolutionEdgeCases:
    def test_empty_file_list(self, tmp_path):
        caller = tmp_path / "main.py"
        caller.write_text("")
        result = resolve_import("foo", caller, [], ImportSemantics.NAMED, "python")
        assert result is not None
        assert result.is_external is True

    def test_go_import(self, tmp_path):
        caller = tmp_path / "main.go"
        caller.write_text("")
        result = resolve_import(
            "fmt.Println", caller, [], ImportSemantics.NAMED, "go"
        )
        assert result is not None
        assert result.is_external is True

    def test_java_jdk_import(self, tmp_path):
        caller = tmp_path / "App.java"
        caller.write_text("")
        result = resolve_import(
            "java.util.ArrayList", caller, [], ImportSemantics.NAMED, "java"
        )
        assert result is not None
        assert result.is_external is True


class TestCrossFileUnit:
    def test_nodes_for_file(self):
        from graphify.cross_file import _nodes_for_file
        from graphify.build import build_from_json
        extraction = {
            "nodes": [
                {"id": "func_a", "label": "func_a()", "source_file": "/test/a.py", "file_type": "code"},
                {"id": "func_b", "label": "func_b()", "source_file": "/test/b.py", "file_type": "code"},
            ],
            "edges": [],
        }
        G = build_from_json(extraction)
        nodes = _nodes_for_file(G, "/test/a.py")
        assert "func_a" in nodes
        assert len(nodes) == 1

    def test_find_in_local_file(self):
        from graphify.cross_file import _find_in_local_file
        nodes = {"func_a": {"label": "func_a()", "node_type": "FUNCTION"}}
        result = _find_in_local_file("func_a", nodes)
        assert result == "func_a"

    def test_find_in_local_file_fallback_method(self):
        from graphify.cross_file import _find_in_local_file
        nodes = {"my_class_my_method": {"label": ".my_method()", "node_type": "METHOD"}}
        result = _find_in_local_file("my_method", nodes)
        assert result == "my_class_my_method"

    def test_detect_language(self):
        from graphify.cross_file import _detect_language
        assert _detect_language("test.py") == "python"
        assert _detect_language("test.ts") == "typescript"
        assert _detect_language("test.tsx") == "typescript"
        assert _detect_language("test.js") == "javascript"
        assert _detect_language("test.jsx") == "javascript"
        assert _detect_language("test.go") == "go"
        assert _detect_language("test.java") == "java"
        assert _detect_language("test.rs") == "unknown"

    def test_resolve_call_chain_empty_calls(self):
        from graphify.cross_file import resolve_call_chain_across_files
        from graphify.build import build_from_json
        from pathlib import Path
        extraction = {"nodes": [], "edges": []}
        G = build_from_json(extraction)
        result = resolve_call_chain_across_files([], Path("test.py"), [], G)
        assert result == []


class TestCallDAGUnit:
    def test_resolve_call_graph_empty_files(self):
        from graphify.call_dag import resolve_call_graph
        from graphify.build import build_from_json
        extraction = {"nodes": [], "edges": []}
        G = build_from_json(extraction)
        resolved, unresolved = resolve_call_graph([], G)
        assert resolved == []
        assert unresolved == 0

    def test_resolve_call_graph_nonexistent_file(self):
        from graphify.call_dag import resolve_call_graph
        from graphify.build import build_from_json
        from pathlib import Path
        extraction = {"nodes": [], "edges": []}
        G = build_from_json(extraction)
        resolved, unresolved = resolve_call_graph([Path("/nonexistent/path.py")], G)
        assert resolved == []
        assert unresolved == 0

    def test_resolve_call_graph_unsupported_extension(self):
        from graphify.call_dag import resolve_call_graph
        from graphify.build import build_from_json
        from pathlib import Path
        import tempfile
        extraction = {"nodes": [], "edges": []}
        G = build_from_json(extraction)
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write("hello")
            tmp_name = f.name
        try:
            resolved, unresolved = resolve_call_graph([Path(tmp_name)], G)
            assert resolved == []
            assert unresolved == 0
        finally:
            import os
            os.unlink(tmp_name)

    def test_get_file_callers(self):
        from graphify.call_dag import _get_file_callers
        from graphify.build import build_from_json
        extraction = {
            "nodes": [
                {"id": "func_a", "label": "doWork()", "source_file": "/test/a.py", "file_type": "code"},
                {"id": "class_b", "label": "MyClass", "source_file": "/test/b.py", "file_type": "code"},
            ],
            "edges": [],
        }
        G = build_from_json(extraction)
        callers = _get_file_callers(G, "/test/a.py")
        assert "func_a" in callers

    def test_extension_to_language(self):
        from graphify.call_dag import _extension_to_language
        assert _extension_to_language(".py") == "python"
        assert _extension_to_language(".ts") == "typescript"
        assert _extension_to_language(".tsx") == "typescript"
        assert _extension_to_language(".js") == "javascript"
        assert _extension_to_language(".jsx") == "javascript"
        assert _extension_to_language(".go") == "go"
        assert _extension_to_language(".java") == "java"
        assert _extension_to_language(".rs") is None
        assert _extension_to_language(".txt") is None


class TestResolvedCall:
    def test_resolved_call_dataclass(self):
        from graphify.call_dag import ResolvedCall
        rc = ResolvedCall(
            caller_id="func_a",
            callee_id="func_b",
            call_site_line=42,
            edge_type="calls",
            confidence="EXTRACTED",
            resolution_steps=["extract", "local_lookup"],
        )
        assert rc.caller_id == "func_a"
        assert rc.callee_id == "func_b"
        assert rc.call_site_line == 42
        assert rc.edge_type == "calls"
        assert rc.confidence == "EXTRACTED"
        assert rc.resolution_steps == ["extract", "local_lookup"]


class TestFindMethodInClass:
    def test_find_method_in_class(self):
        from graphify.cross_file import _find_method_in_class
        from graphify.build import build_from_json
        extraction = {
            "nodes": [
                {"id": "my_class", "label": "MyClass", "node_type": "CLASS", "source_file": "test.py", "file_type": "code"},
                {"id": "my_class_my_method", "label": ".my_method()", "node_type": "METHOD", "source_file": "test.py", "file_type": "code"},
            ],
            "edges": [
                {"source": "my_class", "target": "my_class_my_method", "relation": "method", "confidence": "EXTRACTED"},
            ],
        }
        G = build_from_json(extraction)
        result = _find_method_in_class(G, "my_method", "my_class")
        assert result == "my_class_my_method"

    def test_find_method_in_class_not_found(self):
        from graphify.cross_file import _find_method_in_class
        from graphify.build import build_from_json
        extraction = {
            "nodes": [
                {"id": "my_class", "label": "MyClass", "node_type": "CLASS", "source_file": "test.py", "file_type": "code"},
            ],
            "edges": [],
        }
        G = build_from_json(extraction)
        result = _find_method_in_class(G, "missing_method", "my_class")
        assert result is None


class TestResolveSingleCall:
    def test_resolve_single_call_local(self, tmp_path):
        from graphify.cross_file import _resolve_single_call
        from graphify.build import build_from_json
        from graphify.receiver import ExtractedCallSite
        extraction = {
            "nodes": [
                {"id": "main_multiply", "label": "multiply()", "source_file": str(tmp_path / "test.py"), "file_type": "code"},
            ],
            "edges": [],
        }
        G = build_from_json(extraction)
        file_nodes = {"main_multiply": {"label": "multiply()", "node_type": "FUNCTION"}}
        call = ExtractedCallSite(name="multiply", arity=0, line=5, in_class=None)
        result = _resolve_single_call(call, tmp_path / "test.py", [], G, file_nodes)
        assert result is not None
        assert result["callee"] == "main_multiply"

    def test_resolve_single_call_not_found(self, tmp_path):
        from graphify.cross_file import _resolve_single_call
        from graphify.build import build_from_json
        from graphify.receiver import ExtractedCallSite
        extraction = {"nodes": [], "edges": []}
        G = build_from_json(extraction)
        call = ExtractedCallSite(name="missing_func", arity=0, line=5, in_class=None)
        result = _resolve_single_call(call, tmp_path / "test.py", [], G, {})
        assert result is None

    def test_resolve_single_call_method_in_class(self, tmp_path):
        from graphify.cross_file import _resolve_single_call
        from graphify.build import build_from_json
        from graphify.receiver import ExtractedCallSite
        extraction = {
            "nodes": [
                {"id": "my_class", "label": "MyClass", "node_type": "CLASS", "source_file": str(tmp_path / "test.py"), "file_type": "code"},
                {"id": "my_class_doit", "label": ".doit()", "node_type": "METHOD", "source_file": str(tmp_path / "test.py"), "file_type": "code"},
            ],
            "edges": [
                {"source": "my_class", "target": "my_class_doit", "relation": "method", "confidence": "EXTRACTED"},
            ],
        }
        G = build_from_json(extraction)
        file_nodes = {}
        call = ExtractedCallSite(name="doit", arity=0, line=10, in_class="my_class", receiver="self")
        result = _resolve_single_call(call, tmp_path / "test.py", [], G, file_nodes)
        assert result is not None

    def test_resolve_single_call_no_receiver_in_class(self, tmp_path):
        from graphify.cross_file import _resolve_single_call
        from graphify.build import build_from_json
        from graphify.receiver import ExtractedCallSite
        extraction = {
            "nodes": [
                {"id": "my_class", "label": "MyClass", "node_type": "CLASS", "source_file": str(tmp_path / "test.py"), "file_type": "code"},
                {"id": "my_class_doit", "label": ".doit()", "node_type": "METHOD", "source_file": str(tmp_path / "test.py"), "file_type": "code"},
            ],
            "edges": [
                {"source": "my_class", "target": "my_class_doit", "relation": "method", "confidence": "EXTRACTED"},
            ],
        }
        G = build_from_json(extraction)
        file_nodes = {}
        call = ExtractedCallSite(name="doit", arity=0, line=10, in_class="my_class", receiver=None)
        result = _resolve_single_call(call, tmp_path / "test.py", [], G, file_nodes)
        assert result is not None


class TestResolveImportForCall:
    def test_resolve_import_for_call_not_found(self, tmp_path):
        from graphify.cross_file import _resolve_import_for_call
        caller = tmp_path / "main.py"
        caller.write_text("")
        result = _resolve_import_for_call("no_such_func", caller, [caller])
        assert result is None

    def test_resolve_import_for_call_python_external(self, tmp_path):
        from graphify.cross_file import _resolve_import_for_call
        caller = tmp_path / "main.py"
        caller.write_text("")
        result = _resolve_import_for_call("os", caller, [caller])
        assert result is None


class TestBenchmarkCountExpectedEdges:
    def test_count_expected_edges(self, tmp_path):
        from graphify.benchmark import _count_expected_edges
        f = tmp_path / "test.py"
        f.write_text("def foo():\n    bar()\n    baz()\n")
        edges = _count_expected_edges(f)
        assert edges >= 0

    def test_count_expected_edges_nonexistent(self, tmp_path):
        from graphify.benchmark import _count_expected_edges
        f = tmp_path / "nonexistent.py"
        edges = _count_expected_edges(f)
        assert edges == 0


class TestFindParentClass:
    def test_find_parent_class_none(self):
        from graphify.receiver import _find_parent_class
        result = _find_parent_class(None, {})
        assert result is None

    def test_find_parent_class_no_parent(self):
        from graphify.receiver import _find_parent_class
        graph_nodes = {"my_class": {"label": "MyClass"}}
        result = _find_parent_class("my_class", graph_nodes)
        assert result is None


class TestC3LinearizeNoDup:
    def test_c3_linearize_no_dup(self):
        from graphify.mro import _c3_linearize
        from graphify.build import build_from_json
        extraction = {
            "nodes": [
                {"id": "a", "label": "A", "node_type": "CLASS", "source_file": "t.py", "file_type": "code"},
                {"id": "b", "label": "B", "node_type": "CLASS", "source_file": "t.py", "file_type": "code"},
                {"id": "c", "label": "C", "node_type": "CLASS", "source_file": "t.py", "file_type": "code"},
                {"id": "d", "label": "D", "node_type": "CLASS", "source_file": "t.py", "file_type": "code"},
            ],
            "edges": [
                {"source": "b", "target": "a", "relation": "extends", "confidence": "EXTRACTED"},
                {"source": "c", "target": "a", "relation": "extends", "confidence": "EXTRACTED"},
                {"source": "d", "target": "b", "relation": "extends", "confidence": "EXTRACTED"},
                {"source": "d", "target": "c", "relation": "extends", "confidence": "EXTRACTED"},
            ],
        }
        G = build_from_json(extraction)
        result = _c3_linearize(G, "d", set(), [])
        assert "a" in result
        assert "b" in result
        assert "c" in result
        assert "d" in result
        assert result.count("a") == 1


class TestBenchmarkCallResolution:
    def test_benchmark_call_resolution_empty(self):
        from graphify.benchmark import benchmark_call_resolution
        from graphify.build import build_from_json
        G = build_from_json({"nodes": [], "edges": []})
        result = benchmark_call_resolution(G, num_files=10)
        assert result["total_calls"] == 0

    def test_benchmark_resolution_accuracy_missing(self):
        from graphify.benchmark import benchmark_resolution_accuracy
        from graphify.build import build_from_json
        G = build_from_json({"nodes": [], "edges": []})
        result = benchmark_resolution_accuracy(G, fixture_dir="/nonexistent/path")
        assert "error" in result

    def test_benchmark_call_resolution_scale(self):
        from graphify.benchmark import benchmark_call_resolution_scale
        from graphify.build import build_from_json
        G = build_from_json({"nodes": [], "edges": []})
        result = benchmark_call_resolution_scale(G)
        assert isinstance(result, list)

    def test_benchmark_call_resolution_basic(self):
        from graphify.benchmark import benchmark_call_resolution
        from graphify.build import build_from_json
        extraction = {
            "nodes": [
                {"id": "func_a", "label": "func_a()", "source_file": "a.py", "file_type": "code"},
            ],
            "edges": [],
        }
        G = build_from_json(extraction)
        result = benchmark_call_resolution(G, num_files=1)
        assert "total_calls" in result

    def test_benchmark_call_resolution_no_code_files(self):
        from graphify.benchmark import benchmark_call_resolution
        from graphify.build import build_from_json
        extraction = {
            "nodes": [
                {"id": "doc", "label": "Doc", "source_file": "doc.md", "file_type": "markdown"},
            ],
            "edges": [],
        }
        G = build_from_json(extraction)
        result = benchmark_call_resolution(G, num_files=1)
        assert result["total_calls"] == 0


class TestCallDAGNoParser:
    def test_parse_file_failure(self):
        from graphify.call_dag import _parse_file
        from pathlib import Path
        result = _parse_file(Path("/nonexistent/nope.py"), "python")
        assert result is None

    def test_parse_file_unsupported_lang(self):
        from graphify.call_dag import _parse_file
        from pathlib import Path
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("x = 1")
            tmp = f.name
        try:
            result = _parse_file(Path(tmp), "haskell")
            assert result is None
        finally:
            os.unlink(tmp)


class TestResolveCallChainCrossFile:
    def test_resolve_call_chain_with_receiver_super(self, tmp_path):
        from graphify.cross_file import resolve_call_chain_across_files
        from graphify.build import build_from_json
        from graphify.receiver import ExtractedCallSite
        extraction = {
            "nodes": [
                {"id": "child_service", "label": "ChildService", "node_type": "CLASS",
                 "source_file": str(tmp_path / "test.py"), "file_type": "code"},
                {"id": "parent_service", "label": "ParentService", "node_type": "CLASS",
                 "source_file": str(tmp_path / "test.py"), "file_type": "code"},
                {"id": "parent_service_dowork", "label": ".doWork()", "node_type": "METHOD",
                 "source_file": str(tmp_path / "test.py"), "file_type": "code"},
            ],
            "edges": [
                {"source": "child_service", "target": "parent_service", "relation": "extends"},
                {"source": "parent_service", "target": "parent_service_dowork", "relation": "method"},
            ],
        }
        G = build_from_json(extraction)
        call = ExtractedCallSite(name="doWork", receiver="super", arity=0, line=20, in_class="child_service")
        result = resolve_call_chain_across_files([call], tmp_path / "test.py", [], G)
        assert isinstance(result, list)


class TestMROFirstWinsDeep:
    def test_mro_first_wins_deep(self):
        from graphify.mro import _mro_first_wins
        from graphify.build import build_from_json
        extraction = {
            "nodes": [
                {"id": "a", "label": "A", "node_type": "CLASS", "source_file": "t.py", "file_type": "code"},
                {"id": "b", "label": "B", "node_type": "CLASS", "source_file": "t.py", "file_type": "code"},
                {"id": "c", "label": "C", "node_type": "CLASS", "source_file": "t.py", "file_type": "code"},
                {"id": "a_method", "label": ".method()", "node_type": "METHOD", "source_file": "t.py", "file_type": "code"},
            ],
            "edges": [
                {"source": "b", "target": "a", "relation": "extends"},
                {"source": "c", "target": "b", "relation": "extends"},
                {"source": "a", "target": "a_method", "relation": "method"},
            ],
        }
        G = build_from_json(extraction)
        result = _mro_first_wins(G, "c", "method")
        assert result == "a"


class TestResolveMethodByMRORubymixin:
    def test_resolve_mro_ruby_mixin(self):
        from graphify.mro import resolve_method_by_mro
        from graphify.build import build_from_json
        extraction = {
            "nodes": [
                {"id": "base", "label": "Base", "node_type": "CLASS", "source_file": "t.rb", "file_type": "code"},
                {"id": "base_m", "label": ".m()", "node_type": "METHOD", "source_file": "t.rb", "file_type": "code"},
            ],
            "edges": [
                {"source": "base", "target": "base_m", "relation": "method"},
            ],
        }
        G = build_from_json(extraction)
        result = resolve_method_by_mro("m", "base", G, "ruby")
        assert result == "base"
