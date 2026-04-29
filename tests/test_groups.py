"""Tests for graphify/groups.py."""
import json
import pytest
from pathlib import Path

from graphify.groups import (
    create_group,
    add_to_group,
    remove_from_group,
    list_groups,
    get_group_repos,
    sync_group,
    query_group,
    group_status,
)


@pytest.fixture
def clean_groups(monkeypatch, tmp_path):
    groups_dir = tmp_path / "groups"
    monkeypatch.setattr("graphify.groups.GROUPS_DIR", groups_dir)
    yield groups_dir


def test_create_and_list_groups(clean_groups):
    assert list_groups() == []
    create_group("monorepo", ["repo-a", "repo-b"])
    assert "monorepo" in list_groups()
    assert get_group_repos("monorepo") == ["repo-a", "repo-b"]


def test_create_group_empty(clean_groups):
    create_group("empty-group")
    assert get_group_repos("empty-group") == []


def test_add_and_remove_repos(clean_groups):
    create_group("test-group")
    add_to_group("test-group", "new-repo")
    assert "new-repo" in get_group_repos("test-group")

    add_to_group("test-group", "new-repo")
    assert get_group_repos("test-group").count("new-repo") == 1

    remove_from_group("test-group", "new-repo")
    assert "new-repo" not in get_group_repos("test-group")


def test_remove_nonexistent(clean_groups):
    remove_from_group("no-such-group", "repo-x")


def test_list_groups_empty(clean_groups):
    assert list_groups() == []


def test_sync_group(clean_groups, monkeypatch, tmp_path):
    repo_dir = tmp_path / "syncrepo"
    graph_file = repo_dir / "graphify-out" / "graph.json"
    graph_file.parent.mkdir(parents=True, exist_ok=True)
    G_data = {
        "nodes": [{"id": "n1", "label": "f1"}],
        "links": [{"source": "n1", "target": "n1", "relation": "calls"}],
    }
    graph_file.write_text(json.dumps(G_data))

    from graphify.registry import RepoEntry
    entry = RepoEntry(repo_id="sync-1", name="sync", path=str(repo_dir), last_commit="abc")
    def mock_load():
        return {"sync-1": entry}
    monkeypatch.setattr("graphify.groups.load_registry", mock_load)

    create_group("sync-group", ["sync-1"])
    result = sync_group("sync-group")
    assert result["contracts_found"] == 1
    assert result["bridges_created"] == 0


def test_query_group(clean_groups, monkeypatch, tmp_path):
    repo_dir = tmp_path / "qrepo"
    graph_file = repo_dir / "graphify-out" / "graph.json"
    graph_file.parent.mkdir(parents=True, exist_ok=True)
    graph_file.write_text(json.dumps({"nodes": [{"id": "n1"}], "links": []}))

    from graphify.registry import RepoEntry
    entry = RepoEntry(repo_id="q-1", name="qrepo", path=str(repo_dir), last_commit="abc")
    def mock_load():
        return {"q-1": entry}
    monkeypatch.setattr("graphify.groups.load_registry", mock_load)

    create_group("q-group", ["q-1"])
    result = query_group("q-group", "test query")
    assert "repo_results" in result
    assert "q-1" in result["repo_results"]
    assert len(result["merged"]) > 0


def test_group_status(clean_groups, monkeypatch, tmp_path):
    repo_dir = tmp_path / "statusrepo"
    graph_file = repo_dir / "graphify-out" / "graph.json"
    graph_file.parent.mkdir(parents=True, exist_ok=True)
    graph_file.write_text(json.dumps({"nodes": [{"id": "n1"}, {"id": "n2"}], "links": []}))

    from graphify.registry import RepoEntry
    entry = RepoEntry(repo_id="s-1", name="statusrepo", path=str(repo_dir), last_commit="abc", indexed_at="2025-01-01T00:00:00")
    def mock_load():
        return {"s-1": entry}
    monkeypatch.setattr("graphify.groups.load_registry", mock_load)

    def mock_stale(repo_id):
        return False
    monkeypatch.setattr("graphify.groups.is_stale", mock_stale)

    create_group("s-group", ["s-1"])
    result = group_status("s-group")
    assert len(result["repos"]) == 1
    assert result["repos"][0]["nodes"] == 2
    assert result["repos"][0]["edges"] == 0


def test_group_status_no_entry(clean_groups, monkeypatch):
    monkeypatch.setattr("graphify.groups.load_registry", lambda: {})
    def mock_stale(rid):
        return True
    monkeypatch.setattr("graphify.groups.is_stale", mock_stale)
    create_group("orphan-group", ["missing-repo"])
    result = group_status("orphan-group")
    assert len(result["repos"]) == 1
    assert result["repos"][0]["nodes"] == 0


def test_sync_group_no_entry(clean_groups, monkeypatch):
    monkeypatch.setattr("graphify.groups.load_registry", lambda: {})
    create_group("no-entry-group", ["ghost"])
    result = sync_group("no-entry-group")
    assert result["contracts_found"] == 0


def test_query_group_no_entry(clean_groups, monkeypatch):
    monkeypatch.setattr("graphify.groups.load_registry", lambda: {})
    create_group("no-qentry-group", ["phantom"])
    result = query_group("no-qentry-group", "query")
    assert "phantom" in result["repo_results"]
    assert result["repo_results"]["phantom"] == []


def test_query_group_no_graph(clean_groups, monkeypatch, tmp_path):
    repo_dir = tmp_path / "no-graph-repo"
    from graphify.registry import RepoEntry
    entry = RepoEntry(repo_id="ngr-1", name="ngr", path=str(repo_dir), last_commit="abc")
    def mock_load():
        return {"ngr-1": entry}
    monkeypatch.setattr("graphify.groups.load_registry", mock_load)
    create_group("ngr-group", ["ngr-1"])
    result = query_group("ngr-group", "query")
    assert result["repo_results"]["ngr-1"] == []


def test_add_to_group_creates_if_missing(clean_groups):
    add_to_group("new-group", "repo-1")
    assert list_groups() == ["new-group"]
    assert get_group_repos("new-group") == ["repo-1"]


def test_remove_from_group_not_in_group(clean_groups):
    create_group("g", ["a", "b"])
    remove_from_group("g", "c")
    assert get_group_repos("g") == ["a", "b"]


def test_remove_from_group_no_data(clean_groups):
    remove_from_group("no-such", "x")


def test_get_group_repos_no_data(clean_groups):
    assert get_group_repos("nonexistent") == []
