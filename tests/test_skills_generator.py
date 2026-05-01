"""Tests for graphify/skills/generator.py."""
import json
import pytest
from pathlib import Path
import networkx as nx
from graphify.skills.generator import (
    generate_repo_skill,
    generate_community_skill,
    generate_all_community_skills,
    render_skill_template,
    SkillContext,
    CommunityInfo,
    _build_skill_context,
    _collect_communities,
    _collect_god_nodes,
    _collect_languages,
    _sample_label,
    _collect_key_relationships,
    _collect_files_for_nodes,
)


def _make_graph_with_communities(tmp_path: Path) -> tuple[Path, nx.Graph]:
    G = nx.Graph()
    G.add_node("n1", label="AuthModule", source_file="src/auth.py", community=0, file_type="code", language="python")
    G.add_node("n2", label="LoginHandler", source_file="src/auth.py", community=0, file_type="code", language="python")
    G.add_node("n3", label="UserModel", source_file="src/models.py", community=0, file_type="code", language="python")
    G.add_node("n4", label="ConfigLoader", source_file="src/config.py", community=1, file_type="code", language="python")
    G.add_node("n5", label="EnvParser", source_file="src/config.py", community=1, file_type="code", language="python")
    G.add_node("n6", label="Logger", source_file="src/log.py", community=1, file_type="code", language="python")
    G.add_node("n7", label="Router", source_file="src/router.py", community=2, file_type="code", language="python")
    G.add_node("n8", label="Dispatcher", source_file="src/router.py", community=2, file_type="code", language="python")
    G.add_edge("n1", "n2", relation="calls", confidence="EXTRACTED")
    G.add_edge("n1", "n3", relation="imports", confidence="EXTRACTED")
    G.add_edge("n2", "n3", relation="calls", confidence="INFERRED")
    G.add_edge("n4", "n5", relation="calls", confidence="EXTRACTED")
    G.add_edge("n5", "n6", relation="imports", confidence="EXTRACTED")
    G.add_edge("n7", "n8", relation="calls", confidence="EXTRACTED")
    G.add_edge("n1", "n7", relation="calls", confidence="INFERRED")

    graph_path = tmp_path / "graph.json"
    from networkx.readwrite import json_graph as _jg
    data = _jg.node_link_data(G, edges="links")
    graph_path.write_text(json.dumps(data))
    return graph_path, G


class TestRenderSkillTemplate:
    def test_render_basic(self):
        ctx = SkillContext(
            repo_name="test-project",
            total_nodes=100,
            total_edges=50,
            total_communities=5,
            god_nodes=[
                {"label": "Core", "degree": 42},
                {"label": "Main", "degree": 30},
            ],
            communities=[
                CommunityInfo(
                    community_id=1,
                    label="Auth",
                    node_count=20,
                    file_count=5,
                    cohesion=0.85,
                    top_nodes=[{"label": "AuthModule", "degree": 10, "file": "auth.py", "type": "code"}],
                    source_files=["auth.py", "login.py"],
                    key_relationships=[{"relation": "calls", "count": "15", "example": "Auth->Login"}],
                ),
            ],
            languages=["python"],
        )
        result = render_skill_template(ctx)
        assert "Knowledge graph context for test-project" in result
        assert "100 nodes" in result
        assert "Core" in result
        assert "Auth" in result

    def test_render_empty_god_nodes(self):
        ctx = SkillContext(
            repo_name="empty",
            total_nodes=0,
            total_edges=0,
            total_communities=0,
            god_nodes=[],
            communities=[],
            languages=[],
        )
        result = render_skill_template(ctx)
        assert "No god nodes detected" in result

    def test_render_empty_repo_name(self):
        ctx = SkillContext(
            repo_name="",
            total_nodes=10,
            total_edges=5,
            total_communities=1,
            god_nodes=[{"label": "A", "degree": 3}],
            communities=[],
            languages=[],
        )
        result = render_skill_template(ctx)
        assert "Knowledge graph context for project" in result

    def test_render_cohesion_none(self):
        ctx = SkillContext(
            repo_name="test",
            total_nodes=10,
            total_edges=5,
            total_communities=1,
            god_nodes=[],
            communities=[
                CommunityInfo(
                    community_id=0,
                    label="TestComm",
                    node_count=5,
                    file_count=2,
                    cohesion=None,
                    top_nodes=[],
                    source_files=["a.py"],
                    key_relationships=[],
                ),
            ],
            languages=[],
        )
        result = render_skill_template(ctx)
        assert "TestComm" in result

    def test_render_with_languages(self):
        ctx = SkillContext(
            repo_name="multi-lang",
            total_nodes=50,
            total_edges=30,
            total_communities=2,
            god_nodes=[],
            communities=[],
            languages=["python", "typescript", "go"],
        )
        result = render_skill_template(ctx)
        assert "python" in result
        assert "typescript" in result
        assert "go" in result


class TestCollectCommunities:
    def test_communities_from_graph(self, tmp_path):
        graph_path, G = _make_graph_with_communities(tmp_path)
        comms = _collect_communities(G, min_files=1)
        assert len(comms) > 0

    def test_min_files_filter(self, tmp_path):
        graph_path, G = _make_graph_with_communities(tmp_path)
        comms = _collect_communities(G, min_files=3)
        assert len(comms) <= 3


class TestCollectFiles:
    def test_collect_files(self, tmp_path):
        graph_path, G = _make_graph_with_communities(tmp_path)
        files = _collect_files_for_nodes(G, ["n1", "n2", "n4"])
        assert "src/auth.py" in files
        assert "src/config.py" in files


class TestSampleLabel:
    def test_prefers_non_test(self):
        labels = ["test_auth", "AuthModule", "test_login"]
        assert _sample_label(labels) == "AuthModule"

    def test_fallback_first(self):
        labels = ["test_a", "test_b"]
        assert _sample_label(labels) == "test_a"

    def test_truncates_long(self):
        labels = ["this_is_a_very_long_label_name_that_exceeds_max_chars"]
        result = _sample_label(labels, max_len=20)
        assert len(result) <= 20
        assert result.endswith("...")

    def test_empty_labels(self):
        assert _sample_label([]) == "Community"


class TestCollectRelationships:
    def test_key_relationships(self, tmp_path):
        graph_path, G = _make_graph_with_communities(tmp_path)
        rels = _collect_key_relationships(G, ["n1", "n2", "n3"], top_n=3)
        assert len(rels) > 0
        assert any(r["relation"] == "calls" for r in rels)


class TestCollectLanguages:
    def test_collect_languages(self, tmp_path):
        graph_path, G = _make_graph_with_communities(tmp_path)
        langs = _collect_languages(G)
        assert "python" in langs


class TestCollectGodNodes:
    def test_collect_from_graph(self, tmp_path):
        graph_path, G = _make_graph_with_communities(tmp_path)
        gn = _collect_god_nodes(G, top_n=5)
        assert len(gn) > 0


class TestBuildSkillContext:
    def test_build_from_graph(self, tmp_path):
        graph_path, G = _make_graph_with_communities(tmp_path)
        ctx = _build_skill_context(G, "test-repo")
        assert ctx.repo_name == "test-repo"
        assert ctx.total_nodes == 8
        assert ctx.total_edges == 7
        assert len(ctx.languages) > 0


class TestGenerateRepoSkill:
    def test_generates(self, tmp_path):
        graph_path, G = _make_graph_with_communities(tmp_path)
        result = generate_repo_skill(str(graph_path), repo_name="test")
        assert "Knowledge graph context for test" in result
        assert "8 nodes" in result

    def test_no_graph(self, tmp_path):
        result = generate_repo_skill(str(tmp_path / "missing.json"))
        assert "No graph found" in result

    def test_default_repo_name(self, tmp_path):
        graph_path, G = _make_graph_with_communities(tmp_path)
        result = generate_repo_skill(str(graph_path))
        assert "nodes" in result


class TestGenerateCommunitySkill:
    def test_generates_for_community(self, tmp_path):
        graph_path, G = _make_graph_with_communities(tmp_path)
        result = generate_community_skill(str(graph_path), 0, repo_name="test")
        assert "Community 0" in result

    def test_generates_full_with_many_files(self, tmp_path):
        G = nx.Graph()
        for i in range(10):
            src = f"src/module{i}.py"
            G.add_node(f"n{i}", label=f"Class{i}", source_file=src,
                       community=0, file_type="code", language="python")
        for i in range(5):
            G.add_edge(f"n{i}", f"n{i+1}", relation="calls", confidence="EXTRACTED")
        graph_path = tmp_path / "graph.json"
        from networkx.readwrite import json_graph as _jg
        graph_path.write_text(json.dumps(_jg.node_link_data(G, edges="links")))
        result = generate_community_skill(str(graph_path), 0, repo_name="bigrepo")
        assert "Community 0" in result
        assert "Key Concepts" in result
        assert "Files" in result
        assert "Relationships" in result

    def test_community_not_found(self, tmp_path):
        graph_path, G = _make_graph_with_communities(tmp_path)
        result = generate_community_skill(str(graph_path), 99)
        assert "not found" in result

    def test_no_graph(self, tmp_path):
        result = generate_community_skill(str(tmp_path / "missing.json"), 0)
        assert "No graph found" in result

    def test_default_repo_name(self, tmp_path):
        graph_path, G = _make_graph_with_communities(tmp_path)
        result = generate_community_skill(str(graph_path), 0)
        assert "Community 0" in result


class TestGenerateAllCommunitySkills:
    def test_creates_skill_files(self, tmp_path):
        graph_path, G = _make_graph_with_communities(tmp_path)
        out = tmp_path / "skills"
        paths = generate_all_community_skills(str(graph_path), str(out), min_files=1)
        assert len(paths) > 0
        for p in paths:
            assert p.exists()
            assert p.name.startswith("skill-community-")

    def test_min_files_filter(self, tmp_path):
        graph_path, G = _make_graph_with_communities(tmp_path)
        out = tmp_path / "skills_filtered"
        paths = generate_all_community_skills(str(graph_path), str(out), min_files=100)
        assert len(paths) == 0

    def test_no_graph(self, tmp_path):
        paths = generate_all_community_skills(str(tmp_path / "missing.json"))
        assert paths == []

    def test_with_enough_files(self, tmp_path):
        G = nx.Graph()
        for i in range(12):
            src = f"src/file{i}.py"
            G.add_node(f"n{i}", label=f"Node{i}", source_file=src,
                       community=0, file_type="code", language="python")
        graph_path = tmp_path / "graph.json"
        from networkx.readwrite import json_graph as _jg
        graph_path.write_text(json.dumps(_jg.node_link_data(G, edges="links")))
        out = tmp_path / "skills_out"
        paths = generate_all_community_skills(str(graph_path), str(out), min_files=3)
        assert len(paths) == 1
