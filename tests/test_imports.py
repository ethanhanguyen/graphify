"""Tests for graphify.imports — import resolution across languages."""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.imports import (
    ImportSemantics,
    ImportTarget,
    resolve_import,
)


class TestImportSemanticsEnum:
    def test_enum_values(self):
        assert ImportSemantics.NAMED.value == "named"
        assert ImportSemantics.WILDCARD_LEAF.value == "wildcard_leaf"
        assert ImportSemantics.WILDCARD_TRANSITIVE.value == "wildcard_transitive"
        assert ImportSemantics.NAMESPACE.value == "namespace"


class TestImportTarget:
    def test_dataclass_defaults(self):
        target = ImportTarget(module_path="foo.py")
        assert target.module_path == "foo.py"
        assert target.symbol is None
        assert target.is_external is False
        assert target.confidence == "EXTRACTED"

    def test_dataclass_full(self):
        target = ImportTarget(
            module_path="bar.ts", symbol="Bar", is_external=True, confidence="INFERRED"
        )
        assert target.module_path == "bar.ts"
        assert target.symbol == "Bar"
        assert target.is_external is True
        assert target.confidence == "INFERRED"


class TestResolvePythonImport:
    def test_resolve_python_import_named(self, tmp_path):
        mod_file = tmp_path / "mymodule" / "utils.py"
        mod_file.parent.mkdir(parents=True, exist_ok=True)
        mod_file.write_text("def foo(): pass")
        caller = tmp_path / "mymodule" / "main.py"
        caller.write_text("")

        all_files = [mod_file, caller]
        result = resolve_import(
            "utils.foo", caller, all_files, ImportSemantics.NAMED, "python"
        )
        assert result is not None
        assert result.symbol == "foo"

    def test_resolve_python_import_relative(self, tmp_path):
        mod_file = tmp_path / "pkg" / "helpers.py"
        mod_file.parent.mkdir(parents=True, exist_ok=True)
        mod_file.write_text("def bar(): pass")
        caller = tmp_path / "pkg" / "main.py"
        caller.write_text("")

        all_files = [mod_file, caller]
        result = resolve_import(
            ".helpers", caller, all_files, ImportSemantics.NAMESPACE, "python"
        )
        assert result is not None
        assert result.is_external is False

    def test_resolve_python_import_external(self, tmp_path):
        caller = tmp_path / "main.py"
        caller.write_text("")

        result = resolve_import(
            "os.path", caller, [], ImportSemantics.NAMESPACE, "python"
        )
        assert result is not None
        assert result.is_external is True


class TestResolveTypeScriptImport:
    def test_resolve_typescript_import(self, tmp_path):
        mod_file = tmp_path / "src" / "utils.ts"
        mod_file.parent.mkdir(parents=True, exist_ok=True)
        mod_file.write_text("export function foo(): void {}")
        caller = tmp_path / "src" / "main.ts"
        caller.write_text("")

        all_files = [mod_file, caller]
        result = resolve_import(
            "./utils.ts.foo", caller, all_files, ImportSemantics.NAMED, "typescript"
        )
        assert result is not None

    def test_resolve_typescript_import_external(self, tmp_path):
        caller = tmp_path / "main.ts"
        caller.write_text("")

        all_files = [caller]
        result = resolve_import(
            "lodash", caller, all_files, ImportSemantics.NAMESPACE, "typescript"
        )
        assert result is not None
        assert result.is_external is True


class TestResolveJavaImport:
    def test_resolve_java_import(self, tmp_path):
        mod_file = tmp_path / "com" / "example" / "UserService.java"
        mod_file.parent.mkdir(parents=True, exist_ok=True)
        mod_file.write_text("public class UserService {}")
        caller = tmp_path / "com" / "example" / "App.java"
        caller.write_text("")

        all_files = [mod_file, caller]
        result = resolve_import(
            "com.example.UserService", caller, all_files,
            ImportSemantics.NAMED, "java"
        )
        assert result is not None

    def test_resolve_java_import_jdk(self, tmp_path):
        caller = tmp_path / "App.java"
        caller.write_text("")

        all_files = [caller]
        result = resolve_import(
            "java.util.List", caller, all_files, ImportSemantics.NAMED, "java"
        )
        assert result is not None
        assert result.is_external is True


class TestResolveUnknownLanguage:
    def test_resolve_import_unknown_language(self, tmp_path):
        caller = tmp_path / "main.rs"
        caller.write_text("")

        result = resolve_import(
            "foo", caller, [], ImportSemantics.NAMED, "rust"
        )
        assert result is None

    def test_resolve_import_with_all_custom_language(self, tmp_path):
        caller = tmp_path / "custom.txt"
        caller.write_text("")
        result = resolve_import(
            "foo", caller, [], ImportSemantics.NAMED, "haskell"
        )
        assert result is None


class TestPythonImportWildcard:
    def test_resolve_python_import_wildcard_leaf(self, tmp_path):
        mod_file = tmp_path / "utils.py"
        mod_file.write_text("def foo(): pass")
        caller = tmp_path / "main.py"
        caller.write_text("from utils import *")
        all_files = [mod_file, caller]
        result = resolve_import(
            "utils", caller, all_files, ImportSemantics.WILDCARD_LEAF, "python"
        )
        assert result is not None

    def test_resolve_python_import_wildcard_transitive(self, tmp_path):
        mod_file = tmp_path / "utils.py"
        mod_file.write_text("def foo(): pass")
        caller = tmp_path / "main.py"
        caller.write_text("from utils import *")
        all_files = [mod_file, caller]
        result = resolve_import(
            "utils", caller, all_files, ImportSemantics.WILDCARD_TRANSITIVE, "python"
        )
        assert result is not None

    def test_resolve_python_import_relative_named(self, tmp_path):
        mod_file = tmp_path / "pkg" / "utils.py"
        mod_file.parent.mkdir(parents=True, exist_ok=True)
        mod_file.write_text("def bar(): pass")
        caller = tmp_path / "pkg" / "main.py"
        caller.write_text("")
        all_files = [mod_file, caller]
        result = resolve_import(
            ".utils.bar", caller, all_files, ImportSemantics.NAMED, "python"
        )
        assert result is not None

    def test_resolve_python_import_namespace_with_init(self, tmp_path):
        init_file = tmp_path / "mypackage" / "__init__.py"
        init_file.parent.mkdir(parents=True, exist_ok=True)
        init_file.write_text("")
        caller = tmp_path / "main.py"
        caller.write_text("")
        all_files = [init_file, caller]
        result = resolve_import(
            "mypackage", caller, all_files, ImportSemantics.NAMESPACE, "python"
        )
        assert result is not None

    def test_resolve_python_import_namespace_no_file(self, tmp_path):
        caller = tmp_path / "main.py"
        caller.write_text("")
        all_files = [caller]
        result = resolve_import(
            "nosuchmodule", caller, all_files, ImportSemantics.NAMESPACE, "python"
        )
        assert result is not None
        assert result.is_external is True

    def test_resolve_python_import_namespace_with_mod(self, tmp_path):
        mod_file = tmp_path / "mymodule" / "submod.py"
        mod_file.parent.mkdir(parents=True, exist_ok=True)
        mod_file.write_text("def sub(): pass")
        caller = tmp_path / "main.py"
        caller.write_text("")
        all_files = [mod_file, caller]
        result = resolve_import(
            "mymodule.submod", caller, all_files, ImportSemantics.NAMESPACE, "python"
        )
        assert result is not None

    def test_resolve_python_relative_double_dot(self, tmp_path):
        mod_file = tmp_path / "pkg" / "top" / "mod.py"
        mod_file.parent.mkdir(parents=True, exist_ok=True)
        mod_file.write_text("def top_func(): pass")
        caller = tmp_path / "pkg" / "deep" / "main.py"
        caller.parent.mkdir(parents=True, exist_ok=True)
        caller.write_text("")
        all_files = [mod_file, caller]
        result = resolve_import(
            "..top.mod", caller, all_files, ImportSemantics.NAMESPACE, "python"
        )
        assert result is not None

    def test_resolve_python_relative_named_init(self, tmp_path):
        init_file = tmp_path / "pkg" / "__init__.py"
        init_file.parent.mkdir(parents=True, exist_ok=True)
        init_file.write_text("def foo(): pass")
        caller = tmp_path / "pkg" / "sub.py"
        caller.write_text("")
        all_files = [init_file, caller]
        result = resolve_import(
            ".foo", caller, all_files, ImportSemantics.NAMED, "python"
        )
        assert result is not None


class TestTypeScriptImportAdvanced:
    def test_resolve_typescript_relative_import(self, tmp_path):
        mod_file = tmp_path / "src" / "utils.ts"
        mod_file.parent.mkdir(parents=True, exist_ok=True)
        mod_file.write_text("export function foo(): void {}")
        caller = tmp_path / "src" / "main.ts"
        caller.write_text("")
        all_files = [mod_file, caller]
        result = resolve_import(
            "./utils", caller, all_files, ImportSemantics.NAMESPACE, "typescript"
        )
        assert result is not None

    def test_resolve_typescript_wildcard_leaf(self, tmp_path):
        mod_file = tmp_path / "src" / "utils.ts"
        mod_file.parent.mkdir(parents=True, exist_ok=True)
        mod_file.write_text("export function foo(): void {}")
        caller = tmp_path / "src" / "main.ts"
        caller.write_text("")
        all_files = [mod_file, caller]
        result = resolve_import(
            "./utils", caller, all_files, ImportSemantics.WILDCARD_LEAF, "typescript"
        )
        assert result is not None

    def test_resolve_typescript_namespace_external(self, tmp_path):
        caller = tmp_path / "src" / "main.ts"
        caller.parent.mkdir(parents=True, exist_ok=True)
        caller.write_text("")
        all_files = [caller]
        result = resolve_import(
            "@company/pkg", caller, all_files, ImportSemantics.NAMESPACE, "typescript"
        )
        assert result is not None
        assert result.is_external is True

    def test_resolve_typescript_named_external(self, tmp_path):
        caller = tmp_path / "src" / "main.ts"
        caller.parent.mkdir(parents=True, exist_ok=True)
        caller.write_text("")
        all_files = [caller]
        result = resolve_import(
            "lodash.debounce", caller, all_files, ImportSemantics.NAMED, "typescript"
        )
        assert result is not None
        assert result.is_external is True

    def test_resolve_typescript_relative_non_existent(self, tmp_path):
        caller = tmp_path / "src" / "main.ts"
        caller.parent.mkdir(parents=True, exist_ok=True)
        caller.write_text("")
        all_files = [caller]
        result = resolve_import(
            "./missing", caller, all_files, ImportSemantics.NAMESPACE, "typescript"
        )
        assert result is not None
        assert result.is_external is True


class TestGoImport:
    def test_resolve_go_import_external(self, tmp_path):
        caller = tmp_path / "main.go"
        caller.write_text("")
        all_files = [caller]
        result = resolve_import(
            "fmt", caller, all_files, ImportSemantics.NAMED, "go"
        )
        assert result is not None
        assert result.is_external is True

    def test_resolve_go_import_qualified(self, tmp_path):
        caller = tmp_path / "main.go"
        caller.write_text("")
        all_files = [caller]
        result = resolve_import(
            "github.com/user/repo/pkg", caller, all_files,
            ImportSemantics.NAMED, "go"
        )
        assert result is not None
        assert result.is_external is True

    def test_resolve_go_import_relative(self, tmp_path):
        caller = tmp_path / "main.go"
        caller.write_text("")
        all_files = [caller]
        result = resolve_import(
            "./localpkg", caller, all_files, ImportSemantics.NAMED, "go"
        )
        assert result is not None
        assert result.is_external is False


class TestJavaImportAdvanced:
    def test_resolve_java_import_jakarta(self, tmp_path):
        caller = tmp_path / "App.java"
        caller.write_text("")
        all_files = [caller]
        result = resolve_import(
            "jakarta.ws.rs.GET", caller, all_files, ImportSemantics.NAMED, "java"
        )
        assert result is not None
        assert result.is_external is True

    def test_resolve_java_import_local_file(self, tmp_path):
        mod_file = tmp_path / "com" / "example" / "User.java"
        mod_file.parent.mkdir(parents=True, exist_ok=True)
        mod_file.write_text("public class User {}")
        caller = tmp_path / "com" / "example" / "App.java"
        caller.write_text("")
        all_files = [mod_file, caller]
        result = resolve_import(
            "com.example.User", caller, all_files, ImportSemantics.NAMED, "java"
        )
        assert result is not None
        assert result.is_external is False

    def test_resolve_python_import_single_dot_namespace(self, tmp_path):
        init_file = tmp_path / "pkg" / "__init__.py"
        init_file.parent.mkdir(parents=True, exist_ok=True)
        init_file.write_text("")
        caller = tmp_path / "pkg" / "sub.py"
        caller.write_text("")
        all_files = [init_file, caller]
        result = resolve_import(
            ".", caller, all_files, ImportSemantics.NAMESPACE, "python"
        )
        assert result is not None

    def test_resolve_python_import_named_without_module(self, tmp_path):
        mod_file = tmp_path / "single.py"
        mod_file.write_text("def solo(): pass")
        caller = tmp_path / "main.py"
        caller.write_text("from single import solo")
        all_files = [mod_file, caller]
        result = resolve_import(
            "single.solo", caller, all_files, ImportSemantics.NAMED, "python"
        )
        assert result is not None

    def test_resolve_python_wildcard_transitive_relative(self, tmp_path):
        mod_file = tmp_path / "pkg" / "utils.py"
        mod_file.parent.mkdir(parents=True, exist_ok=True)
        mod_file.write_text("def bar(): pass")
        caller = tmp_path / "pkg" / "main.py"
        caller.write_text("")
        all_files = [mod_file, caller]
        result = resolve_import(
            ".utils", caller, all_files, ImportSemantics.WILDCARD_TRANSITIVE, "python"
        )
        assert result is not None

    def test_resolve_typescript_wildcard_transitive(self, tmp_path):
        caller = tmp_path / "src" / "main.ts"
        caller.parent.mkdir(parents=True, exist_ok=True)
        caller.write_text("")
        all_files = [caller]
        result = resolve_import(
            "lodash.throttle", caller, all_files,
            ImportSemantics.WILDCARD_TRANSITIVE, "typescript"
        )
        assert result is not None
        assert result.is_external is True

    def test_resolve_typescript_named_with_path(self, tmp_path):
        caller = tmp_path / "src" / "main.ts"
        caller.parent.mkdir(parents=True, exist_ok=True)
        caller.write_text("")
        all_files = [caller]
        result = resolve_import(
            "myutils", caller, all_files, ImportSemantics.NAMED, "typescript"
        )
        assert result is not None
        assert result.is_external is True

    def test_resolve_typescript_relative_does_not_exist(self, tmp_path):
        caller = tmp_path / "src" / "main.ts"
        caller.parent.mkdir(parents=True, exist_ok=True)
        caller.write_text("")
        all_files = [caller]
        result = resolve_import(
            "./nosuch", caller, all_files, ImportSemantics.NAMESPACE, "typescript"
        )
        assert result is not None

    def test_resolve_python_named_no_module_found(self, tmp_path):
        caller = tmp_path / "main.py"
        caller.write_text("")
        all_files = [caller]
        result = resolve_import(
            "os.path.join", caller, all_files, ImportSemantics.NAMED, "python"
        )
        assert result is not None

    def test_resolve_javascript_import(self, tmp_path):
        caller = tmp_path / "src" / "main.js"
        caller.parent.mkdir(parents=True, exist_ok=True)
        caller.write_text("")
        all_files = [caller]
        result = resolve_import(
            "express", caller, all_files, ImportSemantics.NAMESPACE, "javascript"
        )
        assert result is not None
        assert result.is_external is True

    def test_file_matches_function(self):
        from graphify.imports import _file_matches
        from pathlib import Path
        result = _file_matches("test", Path("/tmp/test"), (".py",))
        assert isinstance(result, bool)

    def test_resolve_python_wildcard_transitive_rel(self, tmp_path):
        mod_file = tmp_path / "sub" / "mod.py"
        mod_file.parent.mkdir(parents=True, exist_ok=True)
        mod_file.write_text("def x(): pass")
        caller = tmp_path / "pkg" / "main.py"
        caller.parent.mkdir(parents=True, exist_ok=True)
        caller.write_text("")
        all_files = [mod_file, caller]
        result = resolve_import(
            "..sub.mod", caller, all_files, ImportSemantics.WILDCARD_TRANSITIVE, "python"
        )
        assert result is not None

    def test_resolve_python_namespace_double_dot(self, tmp_path):
        mod_file = tmp_path / "top" / "module.py"
        mod_file.parent.mkdir(parents=True, exist_ok=True)
        mod_file.write_text("def f(): pass")
        caller = tmp_path / "deep" / "main.py"
        caller.parent.mkdir(parents=True, exist_ok=True)
        caller.write_text("")
        all_files = [mod_file, caller]
        result = resolve_import(
            "..top.module", caller, all_files, ImportSemantics.NAMESPACE, "python"
        )
        assert result is not None

    def test_resolve_typescript_named_with_relative_non_existent(self, tmp_path):
        caller = tmp_path / "src" / "main.ts"
        caller.parent.mkdir(parents=True, exist_ok=True)
        caller.write_text("")
        all_files = [caller]
        result = resolve_import(
            "./nosuch", caller, all_files, ImportSemantics.NAMED, "typescript"
        )
        assert result is not None

    def test_resolve_java_import_with_local_match(self, tmp_path):
        m = tmp_path / "com" / "example" / "Thing.class"
        m.parent.mkdir(parents=True, exist_ok=True)
        m.write_text("")
        caller = tmp_path / "com" / "example" / "App.java"
        caller.write_text("")
        all_files = [caller, m]
        result = resolve_import(
            "com.example.Thing", caller, all_files, ImportSemantics.NAMED, "java"
        )
        assert result is not None
