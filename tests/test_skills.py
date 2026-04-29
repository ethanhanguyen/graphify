import pytest
from pathlib import Path
import networkx as nx


@pytest.fixture
def test_graph():
    G = nx.Graph()
    G.add_node("n1", label="main()", file_type="code", source_file="main.py", community=0, community_label="Entry Point", entry_point=True, node_type="ENTRY_POINT")
    G.add_node("n2", label="process()", file_type="code", source_file="lib.py", community=0, community_label="Entry Point", entry_point=False, node_type="FUNCTION")
    G.add_node("n3", label="validate()", file_type="code", source_file="lib.py", community=1, community_label="Validation", entry_point=False, node_type="FUNCTION")
    G.add_node("n4", label="save()", file_type="code", source_file="store.py", community=1, community_label="Validation", entry_point=False, node_type="FUNCTION")
    G.add_node("n5", label="test_main.py", file_type="code", source_file="test_main.py", community=0, community_label="Entry Point")
    G.add_node("n6", label="Transformer", file_type="code", source_file="model.py", community=2, community_label="Models", node_type="CLASS")
    G.add_node("n7", label="__init__()", file_type="code", source_file="model.py", community=2, community_label="Models", node_type="METHOD")
    G.add_edge("n1", "n2", relation="calls", confidence="EXTRACTED")
    G.add_edge("n2", "n3", relation="calls", confidence="EXTRACTED")
    G.add_edge("n3", "n4", relation="calls", confidence="AMBIGUOUS")
    G.add_edge("n5", "n1", relation="tests", confidence="EXTRACTED")
    G.add_edge("n6", "n7", relation="contains", confidence="EXTRACTED")
    G.add_edge("n1", "n6", relation="instantiates", confidence="INFERRED")
    G.add_edge("n2", "n4", relation="calls", confidence="INFERRED")
    return G


class TestExploringSkill:
    def test_generate_exploring_skill_has_sections(self, test_graph):
        from graphify.skills.exploring import generate_exploring_skill
        result = generate_exploring_skill(test_graph)
        assert len(result) > 50
        assert "## Graph Overview" in result
        assert "## Tool Usage" in result
        assert "## God Nodes" in result
        assert "## Community Overview" in result
        assert "## Entry Points" in result
        assert "TODO" not in result
        assert "PLACEHOLDER" not in result

    def test_generate_exploring_skill_has_graph_stats(self, test_graph):
        from graphify.skills.exploring import generate_exploring_skill
        result = generate_exploring_skill(test_graph)
        assert "Nodes:" in result
        assert "Edges:" in result
        assert "Communities:" in result

    def test_generate_exploring_skill_references_entry_points(self, test_graph):
        from graphify.skills.exploring import generate_exploring_skill
        result = generate_exploring_skill(test_graph)
        assert "main()" in result


class TestDebuggingSkill:
    def test_generate_debugging_skill_has_sections(self, test_graph):
        from graphify.skills.debugging import generate_debugging_skill
        result = generate_debugging_skill(test_graph)
        assert len(result) > 50
        assert "## Call Chain Tracing" in result
        assert "## Bug Triage with Impact Analysis" in result
        assert "## Test" in result
        assert "## Common Error Patterns" in result
        assert "TODO" not in result
        assert "PLACEHOLDER" not in result

    def test_generate_debugging_skill_reports_ambiguous(self, test_graph):
        from graphify.skills.debugging import generate_debugging_skill
        result = generate_debugging_skill(test_graph)
        assert "validate()" in result

    def test_generate_debugging_skill_maps_test_to_source(self, test_graph):
        from graphify.skills.debugging import generate_debugging_skill
        result = generate_debugging_skill(test_graph)
        assert "test_main.py" in result


class TestImpactSkill:
    def test_generate_impact_skill_has_sections(self, test_graph):
        from graphify.skills.impact import generate_impact_skill
        result = generate_impact_skill(test_graph)
        assert len(result) > 50
        assert "## Blast Radius Analysis" in result
        assert "## Reading Change Detection Output" in result
        assert "## Risk Assessment Guidance" in result
        assert "TODO" not in result
        assert "PLACEHOLDER" not in result

    def test_generate_impact_skill_lists_high_degree_nodes(self, test_graph):
        from graphify.skills.impact import generate_impact_skill
        result = generate_impact_skill(test_graph)
        assert "main()" in result


class TestRefactoringSkill:
    def test_generate_refactoring_skill_has_sections(self, test_graph):
        from graphify.skills.refactoring import generate_refactoring_skill
        result = generate_refactoring_skill(test_graph)
        assert len(result) > 50
        assert "## Dependency Mapping" in result
        assert "## Circular Dependencies" in result
        assert "## Low-Cohesion Communities" in result
        assert "## Isolated" in result
        assert "TODO" not in result
        assert "PLACEHOLDER" not in result


class TestRepoSkills:
    def test_generate_community_skills_creates_files(self, test_graph, tmp_path):
        from graphify.skills.repo_skills import generate_community_skills
        communities = {0: ["n1", "n2", "n5"], 1: ["n3", "n4"], 2: ["n6", "n7"]}
        labels = {0: "Entry Point", 1: "Validation", 2: "Models"}
        count = generate_community_skills(test_graph, communities, labels, tmp_path)
        assert count == 3
        files = list(tmp_path.iterdir())
        assert len(files) == 3
        content = (tmp_path / "Entry Point.md").read_text()
        assert "# Entry Point" in content
        assert "main()" in content

    def test_generate_community_skills_has_key_files(self, test_graph, tmp_path):
        from graphify.skills.repo_skills import generate_community_skills
        communities = {0: ["n1", "n2"]}
        labels = {0: "Entry Point"}
        generate_community_skills(test_graph, communities, labels, tmp_path)
        content = (tmp_path / "Entry Point.md").read_text()
        assert "## Key Files" in content
        assert "main.py" in content or "lib.py" in content


class TestHooks:
    def test_generate_hooks_creates_files(self, tmp_path):
        from graphify.skills.hooks import generate_hooks
        pre, post = generate_hooks(tmp_path)
        pre_path = tmp_path / "pre-tool-use-graphify.sh"
        post_path = tmp_path / "post-tool-use-graphify.sh"
        assert pre_path.exists()
        assert post_path.exists()
        assert pre == str(pre_path)
        assert post == str(post_path)

    def test_hooks_are_executable(self, tmp_path):
        from graphify.skills.hooks import generate_hooks
        pre, post = generate_hooks(tmp_path)
        pre_path = Path(pre)
        post_path = Path(post)
        assert pre_path.stat().st_mode & 0o111
        assert post_path.stat().st_mode & 0o111

    def test_hooks_contain_expected_content(self, tmp_path):
        from graphify.skills.hooks import generate_hooks
        pre, post = generate_hooks(tmp_path)
        pre_content = Path(pre).read_text()
        post_content = Path(post).read_text()
        assert "graphify-out/graph.json" in pre_content
        assert "GRAPH_REPORT.md" in pre_content
        assert "graphify update" in post_content


class TestInject:
    def test_inject_into_claude_md_writes_section(self, test_graph, tmp_path):
        from graphify.skills.inject import inject_into_claude_md
        ag_md = tmp_path / "AGENTS.md"
        ag_md.write_text("# My Project\n\nSome content.\n")
        result = inject_into_claude_md(tmp_path, test_graph)
        assert result is True
        content = ag_md.read_text()
        assert "## Graphify Knowledge Graph" in content
        assert "main()" in content

    def test_inject_into_claude_md_skips_existing(self, test_graph, tmp_path):
        from graphify.skills.inject import inject_into_claude_md
        ag_md = tmp_path / "AGENTS.md"
        ag_md.write_text("## Graphify Knowledge Graph\nalready here")
        result = inject_into_claude_md(tmp_path, test_graph)
        assert result is False

    def test_detect_harness_configs_finds_existing(self, tmp_path):
        from graphify.skills.inject import detect_harness_configs
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "settings.json").write_text("{}")
        result = detect_harness_configs(tmp_path)
        assert len(result) >= 1
        assert any("settings.json" in str(p) for p in result)


class TestOrchestrator:
    def test_generate_base_skills_returns_paths(self, test_graph, tmp_path, monkeypatch):
        import json as _json
        from networkx.readwrite import json_graph
        graph_file = tmp_path / "graph.json"
        data = json_graph.node_link_data(test_graph)
        graph_file.write_text(_json.dumps(data))

        from graphify.skills import generate_base_skills
        out_dir = tmp_path / "skills"
        paths = generate_base_skills(out_dir, graph_file)
        assert len(paths) == 4
        assert (out_dir / "exploring.md").exists()
        assert (out_dir / "debugging.md").exists()
        assert (out_dir / "impact-analysis.md").exists()
        assert (out_dir / "refactoring.md").exists()

    def test_generate_base_skills_missing_graph_raises(self, tmp_path):
        from graphify.skills import generate_base_skills
        with pytest.raises(FileNotFoundError):
            generate_base_skills(tmp_path / "skills", tmp_path / "nonexistent.json")

    def test_generate_all_includes_everything(self, test_graph, tmp_path):
        import json as _json
        from networkx.readwrite import json_graph
        graph_file = tmp_path / "graph.json"
        G = test_graph.copy()
        for nid in G.nodes:
            G.nodes[nid].setdefault("community_label", "Test Community")
            G.nodes[nid].setdefault("community", 0)
        data = json_graph.node_link_data(G)
        graph_file.write_text(_json.dumps(data))

        from graphify.skills import generate_all
        out_dir = tmp_path / "skills"
        result = generate_all(out_dir, graph_file)
        assert len(result["skills"]) == 4
        assert result["community_skills"] >= 1
        assert result["hooks"]["pre_tool"]
        assert result["hooks"]["post_tool"]
