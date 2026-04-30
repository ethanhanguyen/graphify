"""Tests for graphify.receiver — self/this/super receiver inference."""
from __future__ import annotations

import pytest

from graphify.receiver import (
    ExtractedCallSite,
    infer_receiver,
    is_constructor_call,
)


class TestInferReceiver:
    def test_infer_self_receiver(self):
        call = ExtractedCallSite(
            name="doWork", receiver="self", arity=0, line=10,
            in_class="my_service"
        )
        graph_nodes = {"my_service": {"label": "MyService", "node_type": "CLASS"}}
        result = infer_receiver(call, "my_service", graph_nodes)
        assert result == "my_service"

    def test_infer_this_receiver(self):
        call = ExtractedCallSite(
            name="doWork", receiver="this", arity=0, line=10,
            in_class="data_service"
        )
        graph_nodes = {"data_service": {"label": "DataService", "node_type": "CLASS"}}
        result = infer_receiver(call, "data_service", graph_nodes)
        assert result == "data_service"

    def test_infer_super_receiver(self):
        call = ExtractedCallSite(
            name="doWork", receiver="super", arity=0, line=10,
            in_class="child_service"
        )
        graph_nodes = {
            "child_service": {"label": "ChildService", "node_type": "CLASS", "extends": "parent_service"},
            "parent_service": {"label": "ParentService", "node_type": "CLASS"},
        }
        result = infer_receiver(call, "child_service", graph_nodes)
        assert result == "parent_service"

    def test_infer_super_receiver_no_parent(self):
        call = ExtractedCallSite(
            name="doWork", receiver="super", arity=0, line=10,
            in_class="child_service"
        )
        graph_nodes = {
            "child_service": {"label": "ChildService", "node_type": "CLASS"},
        }
        result = infer_receiver(call, "child_service", graph_nodes)
        assert result is None

    def test_infer_cls_receiver(self):
        call = ExtractedCallSite(
            name="factory", receiver="cls", arity=0, line=10,
            in_class="my_class"
        )
        graph_nodes = {"my_class": {"label": "MyClass", "node_type": "CLASS"}}
        result = infer_receiver(call, "my_class", graph_nodes)
        assert result == "my_class"

    def test_infer_without_class_context(self):
        call = ExtractedCallSite(
            name="freeFunc", receiver=None, arity=0, line=10, in_class=None
        )
        graph_nodes = {}
        result = infer_receiver(call, None, graph_nodes)
        assert result is None

    def test_infer_with_explicit_receiver(self):
        call = ExtractedCallSite(
            name="doWork", receiver="myObj", arity=0, line=10,
            in_class="some_service"
        )
        graph_nodes = {"myObj": {"label": "MyObj", "node_type": "CLASS"}}
        result = infer_receiver(call, "some_service", graph_nodes)
        assert result == "myObj"


class TestIsConstructorCall:
    def test_is_constructor_call_match(self):
        graph_nodes = {
            "my_service": {"label": "MyService", "node_type": "CLASS"},
        }
        result = is_constructor_call("MyService", graph_nodes)
        assert result == "my_service"

    def test_is_constructor_call_no_match(self):
        graph_nodes = {
            "my_service": {"label": "MyService", "node_type": "CLASS"},
        }
        result = is_constructor_call("UnknownClass", graph_nodes)
        assert result is None

    def test_is_constructor_call_empty_graph(self):
        result = is_constructor_call("Foo", {})
        assert result is None

    def test_is_constructor_call_not_a_class(self):
        graph_nodes = {
            "my_func": {"label": "myFunc", "node_type": "FUNCTION"},
        }
        result = is_constructor_call("myFunc", graph_nodes)
        assert result is None

    def test_is_constructor_call_case_insensitive(self):
        graph_nodes = {
            "user_service": {"label": "UserService", "node_type": "CLASS"},
        }
        result = is_constructor_call("userservice", graph_nodes)
        assert result == "user_service"
