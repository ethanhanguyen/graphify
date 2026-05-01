"""Tests for graphify/multirepo.py."""
import json
import pytest
from pathlib import Path
from graphify.multirepo import (
    _REGISTRY_PATH,
    _load_registry,
    _save_registry,
    register_repo,
    unregister_repo,
    list_repos,
    get_repo,
    create_group,
    delete_group,
    list_groups,
    get_group,
    sync_group,
    group_graph_paths,
    RepoEntry,
    GroupEntry,
)


@pytest.fixture(autouse=True)
def _isolate_registry(tmp_path, monkeypatch):
    registry = tmp_path / "multirepo.json"
    monkeypatch.setattr("graphify.multirepo._REGISTRY_PATH", registry)
    yield
    if registry.exists():
        registry.unlink(missing_ok=True)


def _make_repo(tmp_path: Path, name: str) -> Path:
    r = tmp_path / name
    r.mkdir(parents=True)
    (r / "README.md").write_text(f"# {name}")
    return r


class TestRegisterRepo:
    def test_register(self, tmp_path):
        r = _make_repo(tmp_path, "repo1")
        entry = register_repo("test-repo", str(r))
        assert entry.name == "test-repo"
        assert entry.path == str(r)

    def test_register_missing_path(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            register_repo("bad", str(tmp_path / "nope"))

    def test_register_twice_overwrites(self, tmp_path):
        r = _make_repo(tmp_path, "repo1")
        register_repo("test", str(r))
        (r / "new.py").write_text("x=1")
        entry = register_repo("test", str(r))
        assert entry.path == str(r)


class TestUnregisterRepo:
    def test_unregister(self, tmp_path):
        r = _make_repo(tmp_path, "repo1")
        register_repo("r1", str(r))
        assert unregister_repo("r1") is True
        assert get_repo("r1") is None

    def test_unregister_nonexistent(self):
        assert unregister_repo("nope") is False

    def test_unregister_removes_from_group(self, tmp_path):
        r1 = _make_repo(tmp_path, "repo1")
        r2 = _make_repo(tmp_path, "repo2")
        register_repo("r1", str(r1))
        register_repo("r2", str(r2))
        create_group("g1", ["r1", "r2"])
        unregister_repo("r1")
        g = get_group("g1")
        assert g is not None
        assert "r1" not in g.repo_names


class TestListRepos:
    def test_empty(self):
        assert list_repos() == []

    def test_with_entries(self, tmp_path):
        r = _make_repo(tmp_path, "repo1")
        register_repo("r1", str(r))
        repos = list_repos()
        assert len(repos) == 1
        assert repos[0].name == "r1"


class TestGetRepo:
    def test_get_existing(self, tmp_path):
        r = _make_repo(tmp_path, "repo1")
        register_repo("r1", str(r))
        entry = get_repo("r1")
        assert entry is not None
        assert entry.name == "r1"

    def test_get_missing(self):
        assert get_repo("nonexistent") is None


class TestCreateGroup:
    def test_create(self, tmp_path):
        r1 = _make_repo(tmp_path, "r1")
        r2 = _make_repo(tmp_path, "r2")
        register_repo("a", str(r1))
        register_repo("b", str(r2))
        g = create_group("group1", ["a", "b"], "test group")
        assert g.name == "group1"
        assert g.repo_names == ["a", "b"]
        assert g.description == "test group"

    def test_create_unregistered_repo_raises(self, tmp_path):
        r = _make_repo(tmp_path, "r1")
        register_repo("a", str(r))
        with pytest.raises(ValueError, match="not registered"):
            create_group("g1", ["a", "nonexistent"])


class TestDeleteGroup:
    def test_delete_existing(self, tmp_path):
        r = _make_repo(tmp_path, "r1")
        register_repo("a", str(r))
        create_group("g1", ["a"])
        assert delete_group("g1") is True

    def test_delete_nonexistent(self):
        assert delete_group("nope") is False


class TestListGroups:
    def test_empty(self):
        assert list_groups() == []

    def test_with_entries(self, tmp_path):
        r = _make_repo(tmp_path, "r1")
        register_repo("a", str(r))
        create_group("g1", ["a"])
        assert len(list_groups()) == 1


class TestGetGroup:
    def test_get_existing(self, tmp_path):
        r = _make_repo(tmp_path, "r1")
        register_repo("a", str(r))
        create_group("g1", ["a"])
        assert get_group("g1") is not None

    def test_get_missing(self):
        assert get_group("nope") is None


class TestSyncGroup:
    def test_sync_no_repo(self):
        with pytest.raises(ValueError, match="not found"):
            sync_group("nonexistent")

    def test_sync_no_graph(self, tmp_path):
        r = _make_repo(tmp_path, "r1")
        register_repo("a", str(r))
        create_group("g1", ["a"])
        results = sync_group("g1")
        assert results["a"] == "no graph built yet"


class TestGroupGraphPaths:
    def test_returns_paths(self, tmp_path):
        r = _make_repo(tmp_path, "r1")
        (r / "graphify-out").mkdir()
        graph = r / "graphify-out" / "graph.json"
        graph.write_text("{}")
        register_repo("a", str(r))
        create_group("g1", ["a"])
        paths = group_graph_paths("g1")
        assert len(paths) == 1
        assert paths[0] == str(graph)

    def test_nonexistent_group(self):
        with pytest.raises(ValueError, match="not found"):
            group_graph_paths("nonexistent")
