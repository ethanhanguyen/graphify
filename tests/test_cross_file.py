from __future__ import annotations

from graphify.cross_file import (
    build_file_dependency_graph,
    compute_scc_order,
    propagate_types,
)


def test_build_file_dependency_graph_simple():
    import_map = {
        "main.py": {"helper": "lib/helper.py", "util": "lib/util.py"},
        "lib/helper.py": {},
        "lib/util.py": {"dep": "lib/helper.py"},
    }
    dep_graph = build_file_dependency_graph(import_map)
    assert "lib/helper.py" in dep_graph["main.py"]
    assert "lib/util.py" in dep_graph["main.py"]
    assert "lib/helper.py" in dep_graph["lib/util.py"]
    assert dep_graph["lib/helper.py"] == set()


def test_build_file_dependency_graph_unresolved_skipped():
    import_map = {
        "main.py": {"missing": ""},
    }
    dep_graph = build_file_dependency_graph(import_map)
    assert dep_graph["main.py"] == set()


def test_build_file_dependency_graph_external_skipped():
    import_map = {
        "main.py": {"external": "external/pkg.py"},
    }
    dep_graph = build_file_dependency_graph(import_map)
    assert "external/pkg.py" not in dep_graph["main.py"]


def test_compute_scc_order_dag():
    dep_graph = {
        "a.py": {"b.py", "c.py"},
        "b.py": {"d.py"},
        "c.py": set(),
        "d.py": set(),
    }
    sccs = compute_scc_order(dep_graph)
    all_nodes = set().union(*sccs)
    assert all_nodes == {"a.py", "b.py", "c.py", "d.py"}
    assert len(sccs) >= 1


def test_compute_scc_order_single_node():
    dep_graph = {"x.py": set()}
    sccs = compute_scc_order(dep_graph)
    assert sccs == [{"x.py"}]


def test_compute_scc_order_cycle():
    dep_graph = {
        "a.py": {"b.py"},
        "b.py": {"a.py"},
    }
    sccs = compute_scc_order(dep_graph)
    nodes = set().union(*sccs)
    assert nodes == {"a.py", "b.py"}
    assert len(sccs) == 1


def test_compute_scc_order_complex_cycle():
    dep_graph = {
        "a.py": {"b.py"},
        "b.py": {"c.py"},
        "c.py": {"a.py"},
        "d.py": set(),
    }
    sccs = compute_scc_order(dep_graph)
    nodes = set().union(*sccs)
    assert nodes == {"a.py", "b.py", "c.py", "d.py"}
    assert len(sccs) == 2


def test_compute_scc_order_empty():
    dep_graph = {}
    sccs = compute_scc_order(dep_graph)
    assert sccs == []


def test_propagate_types_within_scc():
    scc_order = [{"a.py", "b.py"}]
    symbols = {
        "a.py": {"x": {"type": "int"}},
        "b.py": {"y": {"type": "str"}},
    }
    result = propagate_types(scc_order, symbols)
    assert "y" in result["a.py"]
    assert "x" in result["b.py"]


def test_propagate_types_no_cross_scc():
    scc_order = [{"a.py"}, {"b.py"}]
    symbols = {
        "a.py": {"x": {"type": "int"}},
        "b.py": {"y": {"type": "str"}},
    }
    result = propagate_types(scc_order, symbols)
    assert "y" not in result["a.py"]


def test_propagate_types_preserves_existing():
    scc_order = [{"a.py", "b.py"}]
    symbols = {
        "a.py": {"x": {"type": "int"}},
        "b.py": {"x": {"type": "str"}},
    }
    result = propagate_types(scc_order, symbols)
    assert result["a.py"]["x"]["type"] == "int"
