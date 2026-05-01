"""Tests for entry_points.py."""
import networkx as nx
from graphify.entry_points import (
    EntryPoint,
    EntryPointDetector,
    FrameworkEntryPointDetector,
    detect_entry_points,
    score_entry_points,
    register_detector,
)


def test_entrypoint_dataclass_creation():
    ep = EntryPoint(name="handler", kind="HTTP", file="server.py", line=42, language="python", framework="flask")
    assert ep.name == "handler"
    assert ep.kind == "HTTP"
    assert ep.file == "server.py"
    assert ep.line == 42
    assert ep.language == "python"
    assert ep.framework == "flask"


def test_entrypoint_defaults():
    ep = EntryPoint(name="main", kind="CLI", file="main.py", line=10, language="python")
    assert ep.framework == ""


def test_detect_express_route():
    detector = FrameworkEntryPointDetector()
    assert detector._is_express_route("app.get('/')", "") is True
    assert detector._is_express_route("router.post('/', handler)", "") is True
    assert detector._is_express_route("app.use(cors())", "") is True
    assert detector._is_express_route("some_function()", "") is False


def test_detect_express_via_detect_from_node():
    detector = FrameworkEntryPointDetector()
    results = detector._detect_from_node(
        label="app.get('/users', getUsers)",
        src_file="routes/users.ts",
        node_type="function_declaration",
        language="typescript",
        line=15,
    )
    assert len(results) == 1
    assert results[0].kind == "HTTP"
    assert results[0].framework == "express"


def test_detect_cli_main_python():
    detector = FrameworkEntryPointDetector()
    results = detector._detect_from_node(
        label="def main(argv=None)",
        src_file="cli.py",
        node_type="function_declaration",
        language="python",
        line=5,
    )
    assert len(results) == 1
    assert results[0].kind == "CLI"


def test_detect_cli_main_guard():
    detector = FrameworkEntryPointDetector()
    assert detector._is_cli_main("if __name__ == '__main__'", "", "") is True
    assert detector._is_cli_main("if __name__ == \"__main__\"", "", "") is True


def test_detect_test_patterns():
    detector = FrameworkEntryPointDetector()
    assert detector._is_test("def test_login_page():", "") is True
    assert detector._is_test("def test_basic", "") is True
    assert detector._is_test("it('renders correctly', () => {", "") is True
    assert detector._is_test("describe('Login', () => {", "") is True
    assert detector._is_test("test('handles error', async () => {", "") is True
    assert detector._is_test("some_other_func()", "") is False


def test_detect_go_main():
    detector = FrameworkEntryPointDetector()
    results = detector._detect_from_node(
        label="func main()",
        src_file="cmd/server/main.go",
        node_type="function_declaration",
        language="go",
        line=10,
    )
    assert len(results) >= 1
    names = {r.name for r in results}
    assert "main" in names
    assert any(r.kind == "CLI" for r in results)


def test_detect_go_init():
    detector = FrameworkEntryPointDetector()
    results = detector._detect_from_node(
        label="func init()",
        src_file="pkg/plugin/init.go",
        node_type="function_declaration",
        language="go",
        line=3,
    )
    assert len(results) == 1
    assert results[0].kind == "EVENT"
    assert results[0].name == "init"


def test_detect_entry_points_with_mock_graph():
    G = nx.DiGraph()
    extractions = [
        {
            "id": "n1", "label": "app.get('/users')", "source_file": "routes.ts",
            "source_location": "L15", "tree_sitter_type": "call_expression",
            "node_type": "function", "language": "typescript",
        },
        {
            "id": "n2", "label": "def main()", "source_file": "cli.py",
            "source_location": "L3", "tree_sitter_type": "function_definition",
            "node_type": "function", "language": "python",
        },
        {
            "id": "n3", "label": "def test_foo()", "source_file": "test_foo.py",
            "source_location": "L7", "tree_sitter_type": "function_definition",
            "node_type": "function", "language": "python",
        },
        {
            "id": "n4", "label": "validate_input", "source_file": "utils.py",
            "source_location": "L20", "tree_sitter_type": "function_definition",
            "node_type": "function", "language": "python",
        },
    ]
    eps = detect_entry_points(G, extractions)
    kinds = {ep.kind for ep in eps}
    assert "HTTP" in kinds
    assert "CLI" in kinds
    assert "TEST" in kinds


def test_detect_entry_points_returns_empty_for_no_entry_points():
    G = nx.DiGraph()
    extractions = [
        {
            "id": "n1", "label": "helper_func", "source_file": "utils.py",
            "source_location": "L1", "tree_sitter_type": "function_definition",
            "node_type": "function", "language": "python",
        },
    ]
    eps = detect_entry_points(G, extractions)
    assert eps == []


def test_score_entry_points_returns_scored_list():
    G = nx.DiGraph()
    G.add_node("n_main", label="main", source_file="server.py", source_location="L1")
    G.add_node("n_helper", label="helper", source_file="server.py", source_location="L10")
    G.add_node("n_db", label="db_connect", source_file="db.py", source_location="L1")
    G.add_edge("n_main", "n_helper", relation="calls")
    G.add_edge("n_main", "n_db", relation="calls")

    ep = EntryPoint(name="main", kind="CLI", file="server.py", line=1, language="python")
    scored = score_entry_points([ep], G)
    assert len(scored) == 1
    assert isinstance(scored[0], tuple)
    assert isinstance(scored[0][0], EntryPoint)
    assert isinstance(scored[0][1], float)
    assert 0.0 <= scored[0][1] <= 1.0


def test_register_detector_and_detection():
    G = nx.DiGraph()
    G.add_node("n1", label="custom_handler", source_file="custom.py")

    class CustomDetector(FrameworkEntryPointDetector):
        def detect(self, graph, extractions):
            return [
                EntryPoint(
                    name="custom_handler", kind="CUSTOM", file="custom.py",
                    line=1, language="python", framework="custom_fw",
                )
            ]

    register_detector("custom_fw", CustomDetector())
    extractions = [
        {
            "id": "n1", "label": "custom_handler", "source_file": "custom.py",
            "source_location": "L1", "tree_sitter_type": "function_definition",
            "language": "python",
        },
    ]
    eps = detect_entry_points(G, extractions)
    assert len(eps) >= 1
    kinds = {ep.kind for ep in eps}
    assert "CUSTOM" in kinds


def test_base_detector_returns_empty():
    detector = EntryPointDetector()
    G = nx.DiGraph()
    assert detector.detect(G, []) == []


def test_detect_flask_route():
    detector = FrameworkEntryPointDetector()
    results = detector._detect_from_node(
        label="@app.route('/items')",
        src_file="app.py",
        node_type="decorated_definition",
        language="python",
        line=12,
    )
    assert len(results) == 1
    assert results[0].framework == "flask"


def test_detect_fastapi_route():
    detector = FrameworkEntryPointDetector()
    results = detector._detect_from_node(
        label="@router.get('/items/{item_id}')",
        src_file="api.py",
        node_type="decorated_definition",
        language="python",
        line=8,
    )
    assert len(results) >= 1
    frameworks = {r.framework for r in results}
    assert "fastapi" in frameworks


def test_detect_test_def_variants():
    detector = FrameworkEntryPointDetector()
    assert detector._is_test("def test_auth_logout():", "") is True
    assert detector._is_test("def test_edge_case", "") is True
    assert detector._is_test("func TestGoHandler(t *testing.T)", "") is True
    assert detector._is_test("@Test", "") is True
    assert detector._is_test("def helper_func", "") is False


def test_non_dict_extraction_skipped():
    detector = FrameworkEntryPointDetector()
    G = nx.DiGraph()
    results = detector.detect(G, ["not_a_dict", None, 42])
    assert results == []


def test_empty_extractions():
    from graphify.entry_points import _DETECTOR_REGISTRY
    _DETECTOR_REGISTRY.clear()
    G = nx.DiGraph()
    eps = detect_entry_points(G, [])
    assert eps == []
