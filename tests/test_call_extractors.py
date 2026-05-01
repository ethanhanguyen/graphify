from __future__ import annotations

from pathlib import Path

from graphify.call_extractors import ExtractedCallSite, extract_calls
from graphify.code_schema import ConfidenceTier


FIXTURES = Path(__file__).parent / "fixtures"


def _extraction_with_calls(*, language="python", calls_only=True):
    nodes = [
        {"id": "n_func_a", "label": "func_a()", "file_type": "code", "source_file": "test.py"},
        {"id": "n_func_b", "label": "func_b()", "file_type": "code", "source_file": "test.py"},
        {"id": "n_func_c", "label": "Helper.process()", "file_type": "code", "source_file": "test.py"},
    ]
    edges = [
        {"source": "n_func_a", "target": "n_func_b", "relation": "calls",
         "confidence": "EXTRACTED", "source_file": "test.py", "source_location": "L5", "weight": 1.0},
        {"source": "n_func_a", "target": "n_func_c", "relation": "calls",
         "confidence": "INFERRED", "source_file": "test.py", "source_location": "L10", "weight": 1.0},
    ]
    if not calls_only:
        edges.append(
            {"source": "n_func_a", "target": "n_func_b", "relation": "contains",
             "confidence": "EXTRACTED", "source_file": "test.py", "source_location": "", "weight": 1.0},
        )
    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------
def test_extracted_call_site_dataclass():
    cs = ExtractedCallSite(
        caller_nid="n_main",
        caller_file="main.py",
        callee_name="do_work",
        callee_receiver="worker",
        arity=2,
        is_constructor=False,
        source_location="L42",
        confidence=ConfidenceTier.EXTRACTED,
    )
    assert cs.caller_nid == "n_main"
    assert cs.caller_file == "main.py"
    assert cs.callee_name == "do_work"
    assert cs.callee_receiver == "worker"
    assert cs.arity == 2
    assert cs.is_constructor is False
    assert cs.source_location == "L42"
    assert cs.confidence == ConfidenceTier.EXTRACTED


# ---------------------------------------------------------------------------
# Basic happy-path per language
# ---------------------------------------------------------------------------
def test_extract_calls_python():
    ext = _extraction_with_calls(language="python")
    results = extract_calls(Path("test.py"), "python", ext)
    assert len(results) > 0
    for cs in results:
        assert cs.caller_nid
        assert cs.callee_name
        assert cs.caller_file


def test_extract_calls_typescript():
    ext = _extraction_with_calls(language="typescript")
    results = extract_calls(Path("test.ts"), "typescript", ext)
    assert len(results) > 0


def test_extract_calls_go():
    ext = _extraction_with_calls(language="go")
    results = extract_calls(Path("test.go"), "go", ext)
    assert len(results) > 0


def test_extract_calls_java():
    nodes = [
        {"id": "n_A", "label": "A.run()", "file_type": "code", "source_file": "test.java"},
        {"id": "n_B", "label": "B.process()", "file_type": "code", "source_file": "test.java"},
    ]
    edges = [
        {"source": "n_A", "target": "n_B", "relation": "calls",
         "confidence": "EXTRACTED", "source_file": "test.java", "source_location": "L3", "weight": 1.0},
    ]
    ext = {"nodes": nodes, "edges": edges}
    results = extract_calls(Path("test.java"), "java", ext)
    assert len(results) > 0


# ---------------------------------------------------------------------------
# Unknown language
# ---------------------------------------------------------------------------
def test_extract_calls_unknown_language():
    ext = _extraction_with_calls()
    results = extract_calls(Path("test.rb"), "ruby", ext)
    assert results == []


# ---------------------------------------------------------------------------
# Empty / malformed extractions
# ---------------------------------------------------------------------------
def test_extract_calls_empty_extraction():
    ext = {"nodes": [], "edges": []}
    results = extract_calls(Path("empty.py"), "python", ext)
    assert results == []


def test_extract_calls_none_nodes_edges():
    ext: dict = {}
    results = extract_calls(Path("test.py"), "python", ext)
    assert results == []


def test_extract_calls_malformed_source_missing():
    nodes = [{"id": "n_a", "label": "a()"}]
    edges = [
        {"relation": "calls", "source": "", "target": "n_a", "confidence": "EXTRACTED"},
        {"relation": "calls", "source": "n_a", "target": "", "confidence": "EXTRACTED"},
        {"source": "n_a", "relation": "calls", "confidence": "EXTRACTED"},
    ]
    ext = {"nodes": nodes, "edges": edges}
    results = extract_calls(Path("test.py"), "python", ext)
    assert results == []


# ---------------------------------------------------------------------------
# Constructor detection
# ---------------------------------------------------------------------------
def test_extract_calls_constructor_detection():
    nodes = [
        {"id": "n_main", "label": "main()", "file_type": "code", "source_file": "test.py"},
        {"id": "n_Builder", "label": "Builder", "file_type": "code", "source_file": "test.py"},
    ]
    edges = [
        {"source": "n_main", "target": "n_Builder", "relation": "calls",
         "confidence": "EXTRACTED", "source_file": "test.py", "source_location": "L1", "weight": 1.0},
    ]
    ext = {"nodes": nodes, "edges": edges}
    results = extract_calls(Path("test.py"), "python", ext)
    constructors = [cs for cs in results if cs.is_constructor]
    assert len(constructors) >= 1


# ---------------------------------------------------------------------------
# Method / receiver splitting
# ---------------------------------------------------------------------------
def test_extract_calls_method_splitting():
    nodes = [
        {"id": "n_main", "label": "run()", "file_type": "code", "source_file": "test.py"},
        {"id": "n_method", "label": "Worker.do()", "file_type": "code", "source_file": "test.py"},
    ]
    edges = [
        {"source": "n_main", "target": "n_method", "relation": "calls",
         "confidence": "EXTRACTED", "source_file": "test.py", "source_location": "L2", "weight": 1.0},
    ]
    ext = {"nodes": nodes, "edges": edges}
    results = extract_calls(Path("test.py"), "python", ext)
    for cs in results:
        assert cs.callee_receiver is not None or cs.callee_name


# ---------------------------------------------------------------------------
# Java constructor from <init>
# ---------------------------------------------------------------------------
def test_extract_calls_java_constructor_from_init():
    nodes = [
        {"id": "n_main", "label": "main()", "file_type": "code", "source_file": "Test.java"},
        {"id": "n_init", "label": "Foo.<init>", "file_type": "code", "source_file": "Test.java"},
    ]
    edges = [
        {"source": "n_main", "target": "n_init", "relation": "calls",
         "confidence": "EXTRACTED", "source_file": "Test.java", "source_location": "L5", "weight": 1.0},
    ]
    ext = {"nodes": nodes, "edges": edges}
    results = extract_calls(Path("Test.java"), "java", ext)
    constructors = [cs for cs in results if cs.is_constructor]
    assert len(constructors) >= 1


# ---------------------------------------------------------------------------
# Property checks
# ---------------------------------------------------------------------------
def test_extract_calls_has_caller_nid():
    ext = _extraction_with_calls()
    results = extract_calls(Path("test.py"), "python", ext)
    for cs in results:
        assert cs.caller_nid
        assert isinstance(cs.caller_nid, str)


def test_extract_calls_has_callee_name():
    ext = _extraction_with_calls()
    results = extract_calls(Path("test.py"), "python", ext)
    for cs in results:
        assert cs.callee_name
        assert isinstance(cs.callee_name, str)


def test_extract_calls_has_source_file():
    ext = _extraction_with_calls()
    results = extract_calls(Path("test.py"), "python", ext)
    for cs in results:
        assert cs.caller_file


def test_extract_calls_javascript_alias():
    ext = _extraction_with_calls(language="js")
    results = extract_calls(Path("test.js"), "javascript", ext)
    assert len(results) > 0


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------
def test_extract_calls_deduplication():
    nodes = [
        {"id": "n_a", "label": "a()", "file_type": "code", "source_file": "test.py"},
        {"id": "n_b", "label": "b()", "file_type": "code", "source_file": "test.py"},
    ]
    edges = [
        {"source": "n_a", "target": "n_b", "relation": "calls", "confidence": "EXTRACTED",
         "source_file": "test.py", "source_location": "L1", "weight": 1.0},
        {"source": "n_a", "target": "n_b", "relation": "calls", "confidence": "EXTRACTED",
         "source_file": "test.py", "source_location": "L2", "weight": 1.0},
    ]
    ext = {"nodes": nodes, "edges": edges}
    results = extract_calls(Path("test.py"), "python", ext)
    assert len(results) == 1


# ===========================================================================
# Raw calls processing per language
# ===========================================================================

def _raw_calls_extraction(*, callee="helper.do_thing", caller_nid="n_main",
                          is_member_call=True, source_location="L8"):
    return {
        "nodes": [],
        "edges": [],
        "raw_calls": [
            {
                "caller_nid": caller_nid,
                "callee": callee,
                "is_member_call": is_member_call,
                "source_location": source_location,
            }
        ],
    }


def test_extract_calls_python_raw_calls():
    ext = _raw_calls_extraction()
    results = extract_calls(Path("test.py"), "python", ext)
    assert len(results) == 1
    cs = results[0]
    assert cs.callee_name == "do_thing"
    assert cs.callee_receiver == "helper"
    assert cs.confidence == ConfidenceTier.INFERRED


def test_extract_calls_python_raw_calls_no_member():
    ext = _raw_calls_extraction(callee="run", is_member_call=False)
    results = extract_calls(Path("test.py"), "python", ext)
    assert len(results) == 1
    assert results[0].callee_name == "run"
    assert results[0].callee_receiver is None


def test_extract_calls_python_raw_calls_empty_fields():
    ext = {"nodes": [], "edges": [], "raw_calls": [
        {"caller_nid": "", "callee": "run"},
        {"caller_nid": "n_x", "callee": ""},
    ]}
    results = extract_calls(Path("test.py"), "python", ext)
    assert results == []


def test_extract_calls_ts_raw_calls():
    ext = _raw_calls_extraction(callee="Service.handle")
    results = extract_calls(Path("test.ts"), "typescript", ext)
    assert len(results) == 1
    assert results[0].callee_name == "handle"
    assert results[0].callee_receiver == "Service"


def test_extract_calls_go_raw_calls():
    ext = _raw_calls_extraction(callee="pkg.Func")
    results = extract_calls(Path("test.go"), "go", ext)
    assert len(results) == 1
    assert results[0].callee_name == "Func"


def test_extract_calls_java_raw_calls():
    ext = _raw_calls_extraction(callee="com.Foo.bar")
    results = extract_calls(Path("Test.java"), "java", ext)
    assert len(results) == 1
    assert results[0].callee_name == "bar"


def test_extract_calls_raw_calls_single_part_member():
    ext = _raw_calls_extraction(callee="run", is_member_call=True, caller_nid="n_x")
    results = extract_calls(Path("test.py"), "python", ext)
    assert len(results) == 1
    assert results[0].callee_name == "run"
    assert results[0].callee_receiver is None


# ===========================================================================
# Non-EXTRACTED confidence (INFERRED via edge)
# ===========================================================================

def _extraction_inferred_edge():
    nodes = [
        {"id": "n_a", "label": "a()", "file_type": "code", "source_file": "test.py"},
        {"id": "n_b", "label": "b()", "file_type": "code", "source_file": "test.py"},
    ]
    edges = [
        {"source": "n_a", "target": "n_b", "relation": "calls",
         "confidence": "BOGUS", "source_file": "test.py", "source_location": "L1", "weight": 1.0},
    ]
    return {"nodes": nodes, "edges": edges}


def test_extract_calls_python_inferred_confidence():
    ext = _extraction_inferred_edge()
    results = extract_calls(Path("test.py"), "python", ext)
    assert len(results) == 1
    assert results[0].confidence == ConfidenceTier.INFERRED


def test_extract_calls_ts_inferred_confidence():
    ext = _extraction_inferred_edge()
    results = extract_calls(Path("test.ts"), "typescript", ext)
    assert len(results) == 1
    assert results[0].confidence == ConfidenceTier.INFERRED


def test_extract_calls_go_inferred_confidence():
    ext = _extraction_inferred_edge()
    results = extract_calls(Path("test.go"), "go", ext)
    assert len(results) == 1
    assert results[0].confidence == ConfidenceTier.INFERRED


def test_extract_calls_java_inferred_confidence():
    nodes = [
        {"id": "n_a", "label": "A.run()", "file_type": "code", "source_file": "Test.java"},
        {"id": "n_b", "label": "B.do()", "file_type": "code", "source_file": "Test.java"},
    ]
    edges = [
        {"source": "n_a", "target": "n_b", "relation": "calls",
         "confidence": "BOGUS", "source_file": "Test.java", "source_location": "L1", "weight": 1.0},
    ]
    ext = {"nodes": nodes, "edges": edges}
    results = extract_calls(Path("Test.java"), "java", ext)
    assert len(results) == 1
    assert results[0].confidence == ConfidenceTier.INFERRED


# ===========================================================================
# TypeScript: `new ` constructor prefix
# ===========================================================================

def test_extract_calls_ts_new_constructor():
    nodes = [
        {"id": "n_main", "label": "main()"},
        {"id": "n_foo", "label": "new Foo()"},
    ]
    edges = [
        {"source": "n_main", "target": "n_foo", "relation": "calls",
         "confidence": "EXTRACTED", "source_location": "L1", "weight": 1.0},
    ]
    ext = {"nodes": nodes, "edges": edges}
    results = extract_calls(Path("test.ts"), "typescript", ext)
    constructors = [c for c in results if c.is_constructor]
    assert len(constructors) >= 1
    for c in constructors:
        assert "new" not in c.callee_name.lower() or c.callee_name == "Foo"


# ===========================================================================
# Go: `go ` / `defer ` prefix stripping
# ===========================================================================

def test_extract_calls_go_goroutine_prefix():
    nodes = [
        {"id": "n_a", "label": "main()"},
        {"id": "n_b", "label": "go worker()"},
    ]
    edges = [
        {"source": "n_a", "target": "n_b", "relation": "calls",
         "confidence": "EXTRACTED", "source_location": "L1", "weight": 1.0},
    ]
    ext = {"nodes": nodes, "edges": edges}
    results = extract_calls(Path("test.go"), "go", ext)
    assert len(results) == 1
    assert results[0].callee_name == "worker"


def test_extract_calls_go_defer_prefix():
    nodes = [
        {"id": "n_a", "label": "run()"},
        {"id": "n_b", "label": "defer cleanup()"},
    ]
    edges = [
        {"source": "n_a", "target": "n_b", "relation": "calls",
         "confidence": "EXTRACTED", "source_location": "L2", "weight": 1.0},
    ]
    ext = {"nodes": nodes, "edges": edges}
    results = extract_calls(Path("test.go"), "go", ext)
    assert len(results) >= 1
    names = [c.callee_name for c in results]
    assert "cleanup" in names


def test_extract_calls_go_receiver_dot_after_prefix():
    nodes = [
        {"id": "n_a", "label": "main()"},
        {"id": "n_b", "label": "go client.Send()"},
    ]
    edges = [
        {"source": "n_a", "target": "n_b", "relation": "calls",
         "confidence": "EXTRACTED", "source_location": "L1", "weight": 1.0},
    ]
    ext = {"nodes": nodes, "edges": edges}
    results = extract_calls(Path("test.go"), "go", ext)
    assert len(results) == 1
    assert results[0].callee_name == "Send"
    assert results[0].callee_receiver == "client"


# ===========================================================================
# Java: `new ` and `#` splitting
# ===========================================================================

def test_extract_calls_java_new_prefix_constructor():
    nodes = [
        {"id": "n_a", "label": "main()"},
        {"id": "n_b", "label": "new ArrayList()"},
    ]
    edges = [
        {"source": "n_a", "target": "n_b", "relation": "calls",
         "confidence": "EXTRACTED", "source_location": "L1", "weight": 1.0},
    ]
    ext = {"nodes": nodes, "edges": edges}
    results = extract_calls(Path("Test.java"), "java", ext)
    constructors = [c for c in results if c.is_constructor]
    assert len(constructors) >= 1
    assert any("new" not in c.callee_name for c in constructors)


def test_extract_calls_java_hash_splitting():
    nodes = [
        {"id": "n_a", "label": "run()"},
        {"id": "n_b", "label": "com.pkg.Cls#method()"},
    ]
    edges = [
        {"source": "n_a", "target": "n_b", "relation": "calls",
         "confidence": "EXTRACTED", "source_location": "L3", "weight": 1.0},
    ]
    ext = {"nodes": nodes, "edges": edges}
    results = extract_calls(Path("Test.java"), "java", ext)
    assert len(results) == 1
    assert results[0].callee_name == "method"
    assert results[0].callee_receiver == "com.pkg.Cls"


def test_extract_calls_java_hash_and_dot():
    nodes = [
        {"id": "n_a", "label": "run()"},
        {"id": "n_b", "label": "pkg.Cls#method()"},
    ]
    edges = [
        {"source": "n_a", "target": "n_b", "relation": "calls",
         "confidence": "EXTRACTED", "source_location": "L4", "weight": 1.0},
    ]
    ext = {"nodes": nodes, "edges": edges}
    results = extract_calls(Path("Test.java"), "java", ext)
    assert len(results) == 1
    assert results[0].callee_name == "method"


# ===========================================================================
# Cross-language: known language with empty extraction
# ===========================================================================

def test_extract_calls_ts_empty():
    ext = {"nodes": [], "edges": []}
    results = extract_calls(Path("test.ts"), "typescript", ext)
    assert results == []


def test_extract_calls_go_empty():
    ext = {"nodes": [], "edges": []}
    results = extract_calls(Path("test.go"), "go", ext)
    assert results == []


def test_extract_calls_java_empty():
    ext = {"nodes": [], "edges": []}
    results = extract_calls(Path("Test.java"), "java", ext)
    assert results == []
