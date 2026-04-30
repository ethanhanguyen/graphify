"""Per-language call extraction from tree-sitter AST."""
from __future__ import annotations

import importlib
from dataclasses import dataclass


@dataclass
class ExtractedCallSite:
    name: str
    receiver: str | None = None
    arity: int = 0
    line: int = 0
    in_class: str | None = None
    is_dynamic: bool = False
    full_call_text: str = ""


def extract_calls_from_ast(parsed_file, language: str, source: bytes) -> list[ExtractedCallSite]:
    if language == "python":
        return _extract_calls_python(parsed_file, source)
    elif language in ("typescript", "javascript"):
        return _extract_calls_typescript(parsed_file, source)
    elif language == "go":
        return _extract_calls_go(parsed_file, source)
    elif language == "java":
        return _extract_calls_java(parsed_file, source)
    return []


def _read_text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _walk_extract_calls(root_node, source: bytes, config: dict, language: str) -> list[ExtractedCallSite]:
    call_types = config.get("call_types", frozenset())
    function_boundary_types = config.get("function_boundary_types", frozenset())
    call_function_field = config.get("call_function_field", "function")
    call_accessor_node_types = config.get("call_accessor_node_types", frozenset())
    call_accessor_field = config.get("call_accessor_field", "attribute")

    results: list[ExtractedCallSite] = []

    def walk(node, class_name: str | None) -> None:
        t = node.type

        if t in call_types:
            callee_name, receiver, is_member, arity = _extract_call_info(
                node, source, call_function_field, call_accessor_node_types,
                call_accessor_field, language
            )
            if callee_name:
                line = node.start_point[0] + 1
                call_text = _read_text(node, source)[:200]
                results.append(ExtractedCallSite(
                    name=callee_name,
                    receiver=receiver,
                    arity=arity,
                    line=line,
                    in_class=class_name,
                    is_dynamic=is_member,
                    full_call_text=call_text,
                ))

        if t in ("class_definition", "class_declaration", "class_specifier"):
            name_node = node.child_by_field_name("name")
            new_class_name = None
            if name_node:
                new_class_name = _read_text(name_node, source)
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    walk(child, new_class_name or class_name)
            return

        for child in node.children:
            walk(child, class_name)

    walk(root_node, None)
    return results


def _extract_call_info(node, source: bytes, call_function_field: str,
                       call_accessor_node_types: frozenset,
                       call_accessor_field: str, language: str):
    callee_name = None
    receiver = None
    is_member = False
    arity = 0

    args_node = node.child_by_field_name("arguments")
    if args_node:
        arity = sum(1 for c in args_node.children if c.is_named and c.type not in ("(", ")"))

    func_node = node.child_by_field_name(call_function_field) if call_function_field else None
    if func_node:
        if func_node.type == "identifier":
            callee_name = _read_text(func_node, source)
        elif func_node.type in call_accessor_node_types:
            is_member = True
            operand = func_node.child_by_field_name("object")
            if operand:
                receiver = _read_text(operand, source)
            if call_accessor_field:
                attr = func_node.child_by_field_name(call_accessor_field)
                if attr:
                    callee_name = _read_text(attr, source)
        else:
            callee_name = _read_text(func_node, source)
    elif language == "python":
        func_node = node.child_by_field_name("function")
        if func_node:
            if func_node.type == "identifier":
                callee_name = _read_text(func_node, source)
            elif func_node.type == "attribute":
                is_member = True
                obj = func_node.child_by_field_name("object")
                if obj:
                    receiver = _read_text(obj, source)
                attr = func_node.child_by_field_name("attribute")
                if attr:
                    callee_name = _read_text(attr, source)
    elif language in ("typescript", "javascript"):
        func_node = node.child_by_field_name("function")
        if func_node:
            if func_node.type == "identifier":
                callee_name = _read_text(func_node, source)
            elif func_node.type == "member_expression":
                is_member = True
                obj = func_node.child_by_field_name("object")
                if obj:
                    receiver = _read_text(obj, source)
                prop = func_node.child_by_field_name("property")
                if prop:
                    callee_name = _read_text(prop, source)
    elif language == "java":
        name_node = node.child_by_field_name("name")
        if name_node:
            callee_name = _read_text(name_node, source)
        obj = node.child_by_field_name("object")
        if obj:
            receiver = _read_text(obj, source)
            is_member = True
    elif language == "go":
        func_node = node.child_by_field_name("function")
        if func_node:
            if func_node.type == "identifier":
                callee_name = _read_text(func_node, source)
            elif func_node.type == "selector_expression":
                operand = func_node.child_by_field_name("operand")
                if operand:
                    receiver = _read_text(operand, source)
                field = func_node.child_by_field_name("field")
                if field:
                    callee_name = _read_text(field, source)
                is_member = True

    return callee_name, receiver, is_member, arity


def _extract_calls_python(parsed_file, source: bytes) -> list[ExtractedCallSite]:
    config = {
        "call_types": frozenset({"call"}),
        "function_boundary_types": frozenset({"function_definition"}),
        "call_function_field": "function",
        "call_accessor_node_types": frozenset({"attribute"}),
        "call_accessor_field": "attribute",
    }
    return _walk_extract_calls(parsed_file.root_node, source, config, "python")


def _extract_calls_typescript(parsed_file, source: bytes) -> list[ExtractedCallSite]:
    config = {
        "call_types": frozenset({"call_expression"}),
        "function_boundary_types": frozenset({"function_declaration", "arrow_function", "method_definition"}),
        "call_function_field": "function",
        "call_accessor_node_types": frozenset({"member_expression"}),
        "call_accessor_field": "property",
    }
    return _walk_extract_calls(parsed_file.root_node, source, config, "typescript")


def _extract_calls_go(parsed_file, source: bytes) -> list[ExtractedCallSite]:
    config = {
        "call_types": frozenset({"call_expression"}),
        "function_boundary_types": frozenset({"function_declaration", "method_declaration"}),
        "call_function_field": "function",
        "call_accessor_node_types": frozenset({"selector_expression"}),
        "call_accessor_field": "field",
    }
    return _walk_extract_calls(parsed_file.root_node, source, config, "go")


def _extract_calls_java(parsed_file, source: bytes) -> list[ExtractedCallSite]:
    config = {
        "call_types": frozenset({"method_invocation"}),
        "function_boundary_types": frozenset({"method_declaration", "constructor_declaration"}),
        "call_function_field": "name",
        "call_accessor_node_types": frozenset(),
        "call_accessor_field": "",
    }
    return _walk_extract_calls(parsed_file.root_node, source, config, "java")
