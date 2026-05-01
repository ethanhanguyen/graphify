from __future__ import annotations

from graphify.call_extractors import ExtractedCallSite
from graphify.receiver import (
    SelfInferrer,
    ConstructorInferrer,
    ChainInferrer,
    ImportInferrer,
    infer_receiver,
)
from graphify.code_schema import ConfidenceTier


def _cs(**kwargs):
    defaults = {
        "caller_nid": "n_main",
        "caller_file": "test.py",
        "callee_name": "target",
        "callee_receiver": None,
        "arity": 0,
        "is_constructor": False,
        "source_location": "L5",
        "confidence": ConfidenceTier.EXTRACTED,
    }
    defaults.update(kwargs)
    return ExtractedCallSite(**defaults)


class TestSelfInferrer:
    def test_self_keyword_with_enclosing_class(self):
        inferrer = SelfInferrer()
        cs = _cs(callee_name="self", callee_receiver=None)
        result = inferrer.infer(cs, {"enclosing_class": "MyType"})
        assert result == "MyType"

    def test_this_keyword_with_enclosing_class(self):
        inferrer = SelfInferrer()
        cs = _cs(callee_name="this")
        result = inferrer.infer(cs, {"enclosing_class": "MyClass"})
        assert result == "MyClass"

    def test_explicit_receiver_preserved(self):
        inferrer = SelfInferrer()
        cs = _cs(callee_name="foo", callee_receiver="bar")
        result = inferrer.infer(cs, {})
        assert result == "bar"

    def test_method_of_parent_class(self):
        inferrer = SelfInferrer()
        cs = _cs(callee_name="do_work")
        context = {
            "enclosing_class": "Child",
            "class_hierarchy": {"Child": ["Parent", "do_work"]},
        }
        result = inferrer.infer(cs, context)
        assert result == "Child"

    def test_no_enclosing_class_returns_none(self):
        inferrer = SelfInferrer()
        cs = _cs(callee_name="self")
        result = inferrer.infer(cs, {})
        assert result is None

    def test_me_keyword(self):
        inferrer = SelfInferrer()
        cs = _cs(callee_name="me")
        result = inferrer.infer(cs, {"enclosing_class": "Struct"})
        assert result == "Struct"


class TestConstructorInferrer:
    def test_constructor_returns_callee_name(self):
        inferrer = ConstructorInferrer()
        cs = _cs(callee_name="MyClass", is_constructor=True)
        result = inferrer.infer(cs, {})
        assert result == "MyClass"

    def test_non_constructor_returns_none(self):
        inferrer = ConstructorInferrer()
        cs = _cs(callee_name="my_func", is_constructor=False)
        result = inferrer.infer(cs, {})
        assert result is None


class TestChainInferrer:
    def test_method_in_own_class_method_map(self):
        inferrer = ChainInferrer()
        cs = _cs(callee_name="do_stuff")
        context = {
            "enclosing_class": "Worker",
            "method_map": {"Worker": {"do_stuff", "init"}},
        }
        result = inferrer.infer(cs, context)
        assert result == "Worker"

    def test_no_enclosing_class_returns_none(self):
        inferrer = ChainInferrer()
        cs = _cs(callee_name="foo")
        result = inferrer.infer(cs, {"method_map": {}})
        assert result is None

    def test_empty_callee_returns_none(self):
        inferrer = ChainInferrer()
        cs = _cs(callee_name="")
        result = inferrer.infer(cs, {"enclosing_class": "X", "method_map": {"X": set()}})
        assert result is None

    def test_callee_not_in_method_map(self):
        inferrer = ChainInferrer()
        cs = _cs(callee_name="unknown")
        result = inferrer.infer(cs, {"enclosing_class": "A", "method_map": {"A": {"known"}}})
        assert result is None


class TestImportInferrer:
    def test_callee_in_imports_dict(self):
        inferrer = ImportInferrer()
        cs = _cs(callee_name="sqrt")
        result = inferrer.infer(cs, {"imports": {"sqrt": "math"}})
        assert result == "math"

    def test_callee_in_import_map(self):
        inferrer = ImportInferrer()
        cs = _cs(callee_name="helper")
        result = inferrer.infer(cs, {
            "imports": {},
            "import_map": {"utils": {"helper", "Worker"}},
        })
        assert result == "utils"

    def test_empty_callee_returns_none(self):
        inferrer = ImportInferrer()
        cs = _cs(callee_name="")
        result = inferrer.infer(cs, {"imports": {}, "import_map": {}})
        assert result is None

    def test_no_match_returns_none(self):
        inferrer = ImportInferrer()
        cs = _cs(callee_name="unknown")
        result = inferrer.infer(cs, {"imports": {}, "import_map": {}})
        assert result is None


class TestInferReceiver:
    def test_self_first_priority(self):
        cs = _cs(callee_name="self")
        result = infer_receiver(cs, "n_main", {"n_main": "MyClass"})
        assert result == "MyClass"

    def test_constructor_second_priority(self):
        cs = _cs(callee_name="Foo", is_constructor=True)
        result = infer_receiver(cs, "n_main", {})
        assert result == "Foo"

    def test_no_match_returns_none(self):
        cs = _cs(callee_name="orphan_func")
        result = infer_receiver(cs, "n_unknown", {})
        assert result is None

    def test_enclosing_scope_used_for_class(self):
        cs = _cs(callee_name="this", caller_nid="n_method")
        result = infer_receiver(cs, "n_class", {"n_class": "Container"})
        assert result == "Container"

    def test_fallback_to_caller_nid_in_class_map(self):
        cs = _cs(callee_name="self", caller_nid="n_method")
        result = infer_receiver(cs, "n_other", {"n_method": "Worker"})
        assert result == "Worker"
