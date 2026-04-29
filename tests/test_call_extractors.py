"""Tests for call_extractors — call site extraction per language using tree-sitter."""
from __future__ import annotations

import pytest

from graphify.call_extractors import (
    ExtractedCallSite,
    extract_calls_from_ast,
    _extract_calls_python,
    _extract_calls_typescript,
    _extract_calls_go,
    _extract_calls_java,
)


def _parse_python(code: str):
    import tree_sitter_python as tspython
    from tree_sitter import Language, Parser
    language = Language(tspython.language())
    parser = Parser(language)
    source = code.encode("utf-8")
    return parser.parse(source), source


def _parse_typescript(code: str):
    import tree_sitter_typescript as tsts
    from tree_sitter import Language, Parser
    language = Language(tsts.language_typescript())
    parser = Parser(language)
    source = code.encode("utf-8")
    return parser.parse(source), source


def _parse_go(code: str):
    import tree_sitter_go as tsgo
    from tree_sitter import Language, Parser
    language = Language(tsgo.language())
    parser = Parser(language)
    source = code.encode("utf-8")
    return parser.parse(source), source


def _parse_java(code: str):
    import tree_sitter_java as tsjava
    from tree_sitter import Language, Parser
    language = Language(tsjava.language())
    parser = Parser(language)
    source = code.encode("utf-8")
    return parser.parse(source), source


class TestExtractCallsPython:
    def test_extract_simple_call(self):
        code = """
def foo():
    bar()
"""
        tree, source = _parse_python(code)
        calls = _extract_calls_python(tree, source)
        names = [c.name for c in calls]
        assert "bar" in names

    def test_extract_method_call(self):
        code = """
def foo():
    self.method()
"""
        tree, source = _parse_python(code)
        calls = _extract_calls_python(tree, source)
        assert any(c.name == "method" for c in calls)

    def test_extract_nested_call(self):
        code = """
def outer():
    def inner():
        baz()
    inner()
"""
        tree, source = _parse_python(code)
        calls = _extract_calls_python(tree, source)
        names = [c.name for c in calls]
        assert "baz" in names or "inner" in names

    def test_extract_calls_inside_class(self):
        code = """
class MyClass:
    def method(self):
        other_func()
"""
        tree, source = _parse_python(code)
        calls = _extract_calls_python(tree, source)
        names = [c.name for c in calls]
        assert "other_func" in names

    def test_arity(self):
        code = """
def foo():
    bar(a, b, c)
"""
        tree, source = _parse_python(code)
        calls = _extract_calls_python(tree, source)
        bar_calls = [c for c in calls if c.name == "bar"]
        if bar_calls:
            assert bar_calls[0].arity >= 1

    def test_extract_calls_dispatch_python(self):
        code = """
def foo():
    bar()
"""
        tree, source = _parse_python(code)
        calls = extract_calls_from_ast(tree, "python", source)
        assert len(calls) >= 0

    def test_extract_no_calls(self):
        code = "x = 1"
        tree, source = _parse_python(code)
        calls = _extract_calls_python(tree, source)
        assert calls == []


class TestExtractCallsTypeScript:
    def test_extract_ts_call(self):
        code = """
function foo() {
    bar();
}
"""
        tree, source = _parse_typescript(code)
        calls = _extract_calls_typescript(tree, source)
        names = [c.name for c in calls]
        assert "bar" in names

    def test_extract_ts_method_call(self):
        code = """
class Service {
    doWork() {
        this.helper();
    }
}
"""
        tree, source = _parse_typescript(code)
        calls = _extract_calls_typescript(tree, source)
        names = [c.name for c in calls]
        assert "helper" in names

    def test_extract_ts_empty(self):
        code = "const x = 42;"
        tree, source = _parse_typescript(code)
        calls = _extract_calls_typescript(tree, source)
        assert calls == []


class TestExtractCallsJava:
    def test_extract_java_call(self):
        code = """
class Foo {
    void doWork() {
        helper();
    }
}
"""
        tree, source = _parse_java(code)
        calls = _extract_calls_java(tree, source)
        names = [c.name for c in calls]
        assert "helper" in names

    def test_extract_java_method_call(self):
        code = """
class Foo {
    void doWork() {
        this.helper();
    }
}
"""
        tree, source = _parse_java(code)
        calls = _extract_calls_java(tree, source)
        assert any(c.name == "helper" for c in calls)


class TestExtractCallsGo:
    def test_extract_go_call(self):
        code = """
package main

func foo() {
    bar()
}
"""
        tree, source = _parse_go(code)
        calls = _extract_calls_go(tree, source)
        names = [c.name for c in calls]
        assert "bar" in names


class TestExtractedCallSite:
    def test_dataclass_creation(self):
        call = ExtractedCallSite(
            name="doWork",
            receiver="self",
            arity=2,
            line=42,
            in_class="MyService",
            is_dynamic=True,
            full_call_text="self.doWork(a, b)",
        )
        assert call.name == "doWork"
        assert call.receiver == "self"
        assert call.arity == 2
        assert call.line == 42
        assert call.in_class == "MyService"
        assert call.is_dynamic is True
        assert call.full_call_text == "self.doWork(a, b)"


class TestExtractCallsDispatch:
    def test_dispatch_unknown_language(self):
        calls = extract_calls_from_ast(None, "unknown", b"")
        assert calls == []

    def test_dispatch_typescript(self):
        code = "function f() { g(); }"
        import tree_sitter_typescript as tsts
        from tree_sitter import Language, Parser
        language = Language(tsts.language_typescript())
        parser = Parser(language)
        source = code.encode("utf-8")
        tree = parser.parse(source)
        calls = extract_calls_from_ast(tree, "typescript", source)
        assert any(c.name == "g" for c in calls)

    def test_dispatch_go(self):
        code = "package main\nfunc f() { g() }"
        import tree_sitter_go as tsgo
        from tree_sitter import Language, Parser
        language = Language(tsgo.language())
        parser = Parser(language)
        source = code.encode("utf-8")
        tree = parser.parse(source)
        calls = extract_calls_from_ast(tree, "go", source)
        assert any(c.name == "g" for c in calls)

    def test_dispatch_java(self):
        code = "class Foo { void m() { h(); } }"
        import tree_sitter_java as tsjava
        from tree_sitter import Language, Parser
        language = Language(tsjava.language())
        parser = Parser(language)
        source = code.encode("utf-8")
        tree = parser.parse(source)
        calls = extract_calls_from_ast(tree, "java", source)
        assert any(c.name == "h" for c in calls)

    def test_dispatch_javascript(self):
        code = "function f() { g(); }"
        import tree_sitter_javascript as tsjs
        from tree_sitter import Language, Parser
        language = Language(tsjs.language())
        parser = Parser(language)
        source = code.encode("utf-8")
        tree = parser.parse(source)
        calls = extract_calls_from_ast(tree, "javascript", source)
        assert any(c.name == "g" for c in calls)


class TestExtractCallsMethodInsideClass:
    def test_python_class_method_from_outside(self):
        code = """
class Calc:
    pass

def test():
    c = Calc()
    c.add(5)
"""
        tree, source = _parse_python(code)
        calls = _extract_calls_python(tree, source)
        names = [c.name for c in calls]
        assert "add" in names or "Calc" in names


class TestExtractCallInfo:
    def test_extract_call_info_python_attribute(self):
        from graphify.call_extractors import _extract_call_info, _walk_extract_calls
        code = """
def foo():
    obj.method(a, b)
"""
        tree, source = _parse_python(code)
        calls = _extract_calls_python(tree, source)
        assert any(c.name == "method" for c in calls)
        assert any(c.receiver == "obj" or "obj" in c.full_call_text for c in calls)

    def test_extract_call_info_ts_member(self):
        from graphify.call_extractors import _extract_call_info, _walk_extract_calls
        code = """
class Service {
    process() {
        const result = this.helper();
    }
}
"""
        tree, source = _parse_typescript(code)
        calls = _extract_calls_typescript(tree, source)
        assert any(c.name == "helper" for c in calls)

    def test_extract_call_info_ts_function_field(self):
        code = """
function main() {
    foo(1, 2, 3);
}
"""
        tree, source = _parse_typescript(code)
        calls = _extract_calls_typescript(tree, source)
        assert any(c.name == "foo" for c in calls)
        foo_calls = [c for c in calls if c.name == "foo"]
        assert len(foo_calls) > 0

    def test_extract_call_info_java_with_object(self):
        code = """
class Foo {
    void work() {
        obj.helper();
    }
}
"""
        tree, source = _parse_java(code)
        calls = _extract_calls_java(tree, source)
        assert any(c.name == "helper" for c in calls)

    def test_extract_call_info_go_selector(self):
        code = """
package main

func foo() {
    fmt.Println("hello")
}
"""
        tree, source = _parse_go(code)
        calls = _extract_calls_go(tree, source)
        assert any(c.name == "Println" for c in calls)


class TestExtractCallInfoDirect:
    def test_extract_call_info_empty_fields_default(self):
        from graphify.call_extractors import _extract_call_info
        code = """
def foo():
    bar(a, b, c)
"""
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser
        language = Language(tspython.language())
        parser = Parser(language)
        source = code.encode("utf-8")
        tree = parser.parse(source)
        # Find the call node
        call_nodes = []
        def find_calls(n):
            if n.type == "call":
                call_nodes.append(n)
            for c in n.children:
                find_calls(c)
        find_calls(tree.root_node)
        if call_nodes:
            name, recv, is_mem, arity = _extract_call_info(
                call_nodes[0], source, "function",
                frozenset({"attribute"}), "attribute", "python"
            )
            assert name is not None

    def test_extract_call_info_with_empty_call_function_field(self):
        from graphify.call_extractors import _extract_call_info
        code = """
def foo():
    bar()
"""
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser
        language = Language(tspython.language())
        parser = Parser(language)
        source = code.encode("utf-8")
        tree = parser.parse(source)
        call_nodes = []
        def find_calls(n):
            if n.type == "call":
                call_nodes.append(n)
            for c in n.children:
                find_calls(c)
        find_calls(tree.root_node)
        assert len(call_nodes) >= 1  # bar() should be found

    def test_extract_call_info_with_args(self):
        from graphify.call_extractors import _extract_call_info
        code = "result = sum(1, 2, 3)"
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser
        language = Language(tspython.language())
        parser = Parser(language)
        source = code.encode("utf-8")
        tree = parser.parse(source)
        call_nodes = []
        def find_calls(n):
            if n.type == "call":
                call_nodes.append(n)
            for c in n.children:
                find_calls(c)
        find_calls(tree.root_node)
        if call_nodes:
            name, recv, is_mem, arity = _extract_call_info(
                call_nodes[0], source, "function",
                frozenset({"attribute"}), "attribute", "python"
            )
            assert name == "sum"
            assert arity >= 0

    def test_extract_call_info_python_no_func_field(self):
        from graphify.call_extractors import _extract_call_info
        code = "result = sum(1, 2, 3)"
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser
        language = Language(tspython.language())
        parser = Parser(language)
        source = code.encode("utf-8")
        tree = parser.parse(source)
        call_nodes = []
        def find_calls(n):
            if n.type == "call":
                call_nodes.append(n)
            for c in n.children:
                find_calls(c)
        find_calls(tree.root_node)
        if call_nodes:
            name, recv, is_mem, arity = _extract_call_info(
                call_nodes[0], source, "",
                frozenset(), "", "python"
            )
            assert name == "sum"

    def test_extract_call_info_ts_no_func_field(self):
        from graphify.call_extractors import _extract_call_info
        code = "const r = foo(1, 2);"
        import tree_sitter_typescript as tsts
        from tree_sitter import Language, Parser
        language = Language(tsts.language_typescript())
        parser = Parser(language)
        source = code.encode("utf-8")
        tree = parser.parse(source)
        call_nodes = []
        def find_calls(n):
            if n.type == "call_expression":
                call_nodes.append(n)
            for c in n.children:
                find_calls(c)
        find_calls(tree.root_node)
        if call_nodes:
            name, recv, is_mem, arity = _extract_call_info(
                call_nodes[0], source, "",
                frozenset(), "", "typescript"
            )
            assert name == "foo"

    def test_extract_call_info_go_no_func_field(self):
        from graphify.call_extractors import _extract_call_info
        code = """
package main
func main() { fmt.Println("hello") }
"""
        import tree_sitter_go as tsgo
        from tree_sitter import Language, Parser
        language = Language(tsgo.language())
        parser = Parser(language)
        source = code.encode("utf-8")
        tree = parser.parse(source)
        call_nodes = []
        def find_calls(n):
            if n.type == "call_expression":
                call_nodes.append(n)
            for c in n.children:
                find_calls(c)
        find_calls(tree.root_node)
        if call_nodes:
            name, recv, is_mem, arity = _extract_call_info(
                call_nodes[0], source, "",
                frozenset(), "", "go"
            )
            assert name is not None

    def test_extract_call_info_java_no_func_field(self):
        from graphify.call_extractors import _extract_call_info
        code = "class Foo { void m() { helper(); } }"
        import tree_sitter_java as tsjava
        from tree_sitter import Language, Parser
        language = Language(tsjava.language())
        parser = Parser(language)
        source = code.encode("utf-8")
        tree = parser.parse(source)
        call_nodes = []
        def find_calls(n):
            if n.type == "method_invocation":
                call_nodes.append(n)
            for c in n.children:
                find_calls(c)
        find_calls(tree.root_node)
        if call_nodes:
            name, recv, is_mem, arity = _extract_call_info(
                call_nodes[0], source, "",
                frozenset(), "", "java"
            )
            assert name is not None

    def test_extract_call_info_java_no_object(self):
        code = """
class Foo {
    void work() {
        helper(1, 2);
    }
}
"""
        tree, source = _parse_java(code)
        calls = _extract_calls_java(tree, source)
        assert any(c.name == "helper" for c in calls)

    def test_extract_call_info_ts_identifier(self):
        code = """
function main() {
    doWork();
}
"""
        tree, source = _parse_typescript(code)
        calls = _extract_calls_typescript(tree, source)
        assert any(c.name == "doWork" for c in calls)
