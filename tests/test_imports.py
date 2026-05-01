from __future__ import annotations

from pathlib import Path

from graphify.imports import (
    resolve_import,
    build_import_graph,
    resolve_all_imports,
    _resolve_named,
    _resolve_wildcard_leaf,
    _resolve_wildcard_transitive,
    _resolve_namespace,
)
from graphify.language_provider import register_provider, LanguageCallProvider


_ALL_FILES = {
    "util": ["lib/util.py", "ext/util.py"],
    "helper": ["lib/helper.py"],
    "core": ["lib/core/__init__.py"],
    "foo": ["src/foo.py"],
}

_FROM_FILE = Path("src/main.py")


def test_resolve_import_named_strategy():
    result = resolve_import("helper", _FROM_FILE, _ALL_FILES, "python")
    assert result == "lib/helper.py"


def test_resolve_import_named_multiple_candidates():
    result = resolve_import("util", Path("lib/mod.py"), _ALL_FILES, "python")
    assert result in ("lib/util.py", "ext/util.py")


def test_resolve_import_wildcard_leaf():
    result = resolve_import("foo", _FROM_FILE, {
        "bar": ["src/foo.py", "test/foo.py"]
    }, "python")
    assert result == "src/foo.py"


def test_resolve_import_wildcard_transitive():
    all_files = {"foo": ["src/pkg/foo/__init__.py"]}
    result = resolve_import("foo", _FROM_FILE, all_files, "python")
    assert result == "src/pkg/foo/__init__.py"


def test_resolve_import_namespace_strategy():
    all_files = {"mypkg": ["lib/mypkg/__init__.py"]}
    result = resolve_import("mypkg.core", Path("src/main.py"), all_files, "python")
    assert result is None


def test_resolve_import_returns_none_no_match():
    result = resolve_import("nonexistent", _FROM_FILE, _ALL_FILES, "python")
    assert result is None


def test_build_import_graph():
    files = [Path("a.py"), Path("b.py")]
    parsed_files = {
        "a.py": {
            "edges": [
                {"relation": "imports", "target": "b.py"},
                {"relation": "calls", "target": "x"},
            ]
        },
        "b.py": {"edges": []},
    }
    graph = build_import_graph(files, parsed_files)
    assert "b.py" in graph["a.py"]
    assert "x" not in graph["a.py"]


def test_build_import_graph_empty():
    files = [Path("a.py")]
    parsed_files = {}
    graph = build_import_graph(files, parsed_files)
    assert graph["a.py"] == []


def test_build_import_graph_imports_from():
    files = [Path("a.py")]
    parsed_files = {
        "a.py": {
            "edges": [
                {"relation": "imports_from", "target": "os.path"},
            ]
        }
    }
    graph = build_import_graph(files, parsed_files)
    assert "os.path" in graph["a.py"]


def test_resolve_all_imports():
    imports = [
        {"name": "helper"},
        {"name": "util"},
        {"name": "nonexistent"},
    ]
    resolved = resolve_all_imports(_FROM_FILE, imports, _ALL_FILES, "python")
    assert "helper" in resolved
    assert resolved["helper"] == "lib/helper.py"
    assert "nonexistent" not in resolved


def test_resolve_all_imports_different_keys():
    imports = [
        {"source": "helper"},
        {"target": "nonexistent"},
    ]
    resolved = resolve_all_imports(_FROM_FILE, imports, _ALL_FILES, "python")
    assert "helper" in resolved


def test_resolve_all_imports_empty():
    resolved = resolve_all_imports(_FROM_FILE, [], _ALL_FILES, "python")
    assert resolved == {}


def test_resolve_all_imports_blank_name():
    imports = [{"name": ""}, {"name": "helper"}]
    resolved = resolve_all_imports(_FROM_FILE, imports, _ALL_FILES, "python")
    assert "" not in resolved
    assert "helper" in resolved


# ---------------------------------------------------------------------------
# resolve_import with empty all_files
# ---------------------------------------------------------------------------
def test_resolve_import_empty_all_files():
    result = resolve_import("helper", _FROM_FILE, {}, "python")
    assert result is None


# ---------------------------------------------------------------------------
# resolve_import with multiple candidates — scoring picks closer one
# ---------------------------------------------------------------------------
def test_resolve_import_scoring_picks_closest():
    all_files = {"helper": ["src/lib/helper.py", "tests/helper.py"]}
    result = resolve_import("helper", Path("src/lib/main.py"), all_files, "python")
    assert result == "src/lib/helper.py"


# ---------------------------------------------------------------------------
# build_import_graph: files that have no parsed_files entry
# ---------------------------------------------------------------------------
def test_build_import_graph_file_not_in_parsed():
    files = [Path("a.py"), Path("b.py")]
    parsed_files = {"a.py": {"edges": []}}
    graph = build_import_graph(files, parsed_files)
    assert graph["a.py"] == []
    assert graph["b.py"] == []


# ---------------------------------------------------------------------------
# build_import_graph: duplicate imports
# ---------------------------------------------------------------------------
def test_build_import_graph_dedup_same_target():
    files = [Path("a.py")]
    parsed_files = {
        "a.py": {
            "edges": [
                {"relation": "imports", "target": "os"},
                {"relation": "imports_from", "target": "os"},
            ]
        }
    }
    graph = build_import_graph(files, parsed_files)
    assert graph["a.py"] == ["os"]


# ---------------------------------------------------------------------------
# _resolve_wildcard_leaf with no match
# ---------------------------------------------------------------------------
def test_resolve_import_wildcard_leaf_no_match():
    result = resolve_import("unknown_thing", _FROM_FILE, _ALL_FILES, "python")
    assert result is None


# ---------------------------------------------------------------------------
# _resolve_wildcard_transitive with scoring
# ---------------------------------------------------------------------------
def test_resolve_import_wildcard_transitive_scoring():
    all_files = {"lib": ["src/pkg/lib.py", "other/lib.py"]}
    result = resolve_import("lib", Path("src/pkg/main.py"), all_files, "python")
    assert result == "src/pkg/lib.py"


# ---------------------------------------------------------------------------
# resolve_all_imports: empty imports dict
# ---------------------------------------------------------------------------
def test_resolve_all_imports_empty_imports_list():
    resolved = resolve_all_imports(_FROM_FILE, [], _ALL_FILES, "python")
    assert resolved == {}


# ---------------------------------------------------------------------------
# resolve_import: named strategy succeeds, skipping later strategies
# ---------------------------------------------------------------------------
def test_resolve_import_named_wins_over_wildcard():
    all_files = {"helper": ["lib/helper.py"]}
    result = resolve_import("helper", _FROM_FILE, all_files, "python")
    assert result == "lib/helper.py"


# ===========================================================================
# _resolve_named: scoring when multiple candidates exist
# ===========================================================================

def test_resolve_named_scoring_multiple():
    all_files = {"svc": ["src/pkg/svc.py", "tests/svc.py"]}
    result = _resolve_named("svc", Path("src/pkg/main.py"), all_files)
    assert result == "src/pkg/svc.py"


def test_resolve_named_no_candidates():
    result = _resolve_named("ghost", Path("main.py"), {})
    assert result is None


# ===========================================================================
# _resolve_wildcard_leaf: path-based matching
# ===========================================================================

def test_resolve_wildcard_leaf_suffix_match():
    all_files = {"bar": ["lib/foo/bar.py"]}
    result = _resolve_wildcard_leaf("bar", Path("lib/foo/main.py"), all_files)
    assert result == "lib/foo/bar.py"


def test_resolve_wildcard_leaf_slash_replacement():
    all_files = {"baz": ["pkg/foo/bar"]}
    result = _resolve_wildcard_leaf("foo.bar", Path("lib/main.py"), all_files)
    assert result == "pkg/foo/bar"


def test_resolve_wildcard_leaf_scoring_multiple():
    all_files = {"q": ["src/foo/q.py", "other/q.py"]}
    result = _resolve_wildcard_leaf("q", Path("src/foo/main.py"), all_files)
    assert result == "src/foo/q.py"


def test_resolve_wildcard_leaf_no_match():
    result = _resolve_wildcard_leaf("nope", Path("main.py"), _ALL_FILES)
    assert result is None


# ===========================================================================
# _resolve_wildcard_transitive: stem matching
# ===========================================================================

def test_resolve_wildcard_transitive_single():
    all_files = {"lib": ["src/pkg/lib.py"]}
    result = _resolve_wildcard_transitive("lib", Path("main.py"), all_files)
    assert result == "src/pkg/lib.py"


def test_resolve_wildcard_transitive_scoring():
    all_files = {"mod": ["src/core/mod.py", "tests/mod.py"]}
    result = _resolve_wildcard_transitive("mod", Path("src/core/main.py"), all_files)
    assert result == "src/core/mod.py"


def test_resolve_wildcard_transitive_no_match():
    result = _resolve_wildcard_transitive("ghost", Path("main.py"), _ALL_FILES)
    assert result is None


# ===========================================================================
# _resolve_namespace
# ===========================================================================

def test_resolve_namespace_dotted_path():
    all_files = {"pkg": ["lib/com/pkg/__init__.py"]}
    result = _resolve_namespace("com.pkg", Path("lib/main.py"), all_files)
    assert result == "lib/com/pkg/__init__.py"


def test_resolve_namespace_partial_dir_match():
    all_files = {"svc": ["src/svc.py"]}
    result = _resolve_namespace("svc", Path("lib/main.py"), all_files)
    assert result == "src/svc.py"


def test_resolve_namespace_no_match():
    result = _resolve_namespace("nothing", Path("main.py"), _ALL_FILES)
    assert result is None


# ===========================================================================
# resolve_import: namespace strategy via provider
# ===========================================================================

class _NamespaceProvider(LanguageCallProvider):
    def import_resolver(self, file_path, import_name, all_files):
        return None

    def call_extractor(self, parsed_ast, source_bytes, config):
        return []

    def receiver_inferrer(self, call_node, enclosing_class, source_bytes):
        return None

    def mro_strategy(self):
        return "c3"

    def import_semantics(self):
        return "namespace"


def test_resolve_import_with_namespace_provider():
    register_provider("java_test_ns", _NamespaceProvider())
    all_files = {"svc": ["com/example/svc/__init__.py"]}
    result = resolve_import("com.example.svc", Path("main.java"), all_files, "java_test_ns")
    assert result == "com/example/svc/__init__.py"


def test_resolve_import_namespace_fallback_fails():
    result = resolve_import("total.ghost", _FROM_FILE, _ALL_FILES, "python")
    assert result is None
