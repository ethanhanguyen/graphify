import pytest
from graphify.search.grouping import (
    GroupedSearchResult,
    format_grouped_results,
    group_results_by_process,
)


def _make_process():
    from graphify.processes import Process, EntryPoint, ProcessStep

    entry = EntryPoint(
        node_id="login_handler",
        label="Login",
        kind="route_handler",
        route="/api/login",
        method="POST",
        score=10.0,
        file="src/routes/auth.py",
    )
    steps = [
        ProcessStep(node_id="n1", step_index=0, call_chain=[], file="src/routes/auth.py", line="L42"),
        ProcessStep(node_id="n2", step_index=1, call_chain=[], file="src/services/auth.py", line="L15"),
        ProcessStep(node_id="n3", step_index=2, call_chain=[], file="src/db/users.py", line="L80"),
    ]
    return Process(
        id="proc_login",
        name="Login Flow",
        entry_point=entry,
        steps=steps,
        confidence=0.95,
        total_calls=3,
        unique_files=3,
    )


def _make_graph():
    import networkx as nx

    G = nx.Graph()
    G.add_node("n1", label="loginHandler", node_type="FUNCTION",
               source_file="src/routes/auth.py", signature="loginHandler(req: Request): Response")
    G.add_node("n2", label="authenticateUser", node_type="FUNCTION",
               source_file="src/services/auth.py", signature="authenticateUser(email: str, password: str): User")
    G.add_node("n3", label="findUserByEmail", node_type="FUNCTION",
               source_file="src/db/users.py", signature="findUserByEmail(email: str): User | None")
    G.add_node("n4", label="unrelatedUtils", node_type="FUNCTION",
               source_file="src/utils/helpers.py")
    return G


def test_group_results_by_process():
    G = _make_graph()
    proc = _make_process()
    processes = [proc]

    ranked = [
        ("n1", 0.9),
        ("n2", 0.8),
        ("n4", 0.5),
    ]

    grouped = group_results_by_process(ranked, G, processes)
    assert len(grouped) == 1
    assert grouped[0].process_name == "Login Flow"
    assert grouped[0].symbol_count == 2
    assert len(grouped[0].definitions) == 2


def test_group_results_no_match():
    G = _make_graph()
    proc = _make_process()
    processes = [proc]

    ranked = [("n4", 0.5)]

    grouped = group_results_by_process(ranked, G, processes)
    assert len(grouped) == 0


def test_group_results_multiple_processes():
    G = _make_graph()

    from graphify.processes import Process, EntryPoint, ProcessStep

    proc1 = _make_process()
    entry2 = EntryPoint(
        node_id="register_handler",
        label="Register",
        kind="route_handler",
        route="/api/register",
        method="POST",
        score=10.0,
        file="src/routes/auth.py",
    )
    steps2 = [
        ProcessStep(node_id="n4", step_index=0, call_chain=[], file="src/utils/helpers.py", line="L10"),
    ]
    proc2 = Process(
        id="proc_register",
        name="Register Flow",
        entry_point=entry2,
        steps=steps2,
        confidence=0.9,
        total_calls=1,
        unique_files=1,
    )

    processes = [proc1, proc2]
    ranked = [("n1", 0.9), ("n4", 0.6)]

    grouped = group_results_by_process(ranked, G, processes)
    assert len(grouped) == 2
    names = {g.process_name for g in grouped}
    assert "Login Flow" in names
    assert "Register Flow" in names


def test_format_grouped_results():
    G = _make_graph()
    proc = _make_process()
    processes = [proc]

    ranked = [("n1", 0.9), ("n2", 0.8)]
    grouped = group_results_by_process(ranked, G, processes)
    output = format_grouped_results(grouped)

    assert "Login Flow" in output
    assert "route_handler" in output
    assert "definitions:" in output
    assert "loginHandler" in output


def test_format_empty_results():
    output = format_grouped_results([])
    assert "No matching processes" in output
