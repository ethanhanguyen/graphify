"""Tests for graphify/registry.py."""
import pytest
import json
from pathlib import Path

from graphify.registry import (
    RepoEntry,
    load_registry,
    save_registry,
    register_repo,
    unregister_repo,
    list_repos,
    get_repo,
    update_commit,
    is_stale,
)


@pytest.fixture
def clean_registry(monkeypatch, tmp_path):
    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr("graphify.registry.REGISTRY_PATH", reg_path)
    yield reg_path
    if reg_path.exists():
        reg_path.unlink(missing_ok=True)


def test_register_and_list_repos(clean_registry):
    entry = register_repo("/fake/project")
    assert entry.name == "project"
    assert entry.path == str(Path("/fake/project").resolve())
    assert entry.repo_id.startswith("project-")

    repos = list_repos()
    assert len(repos) == 1
    assert repos[0].repo_id == entry.repo_id


def test_register_with_meta(clean_registry):
    entry = register_repo("/fake/myrepo", meta={"name": "custom-name", "url": "https://github.com/x/y"})
    assert entry.name == "custom-name"
    assert entry.url == "https://github.com/x/y"


def test_unregister_repo(clean_registry):
    entry = register_repo("/fake/toremove")
    assert unregister_repo(entry.repo_id) is True
    assert unregister_repo(entry.repo_id) is False
    assert len(list_repos()) == 0


def test_unregister_nonexistent(clean_registry):
    assert unregister_repo("nonexistent") is False


def test_get_repo(clean_registry):
    entry = register_repo("/fake/target")
    found = get_repo(entry.repo_id)
    assert found is not None
    assert found.name == "target"

    assert get_repo("nonexistent") is None


def test_update_commit(clean_registry):
    entry = register_repo("/fake/updateme")
    update_commit(entry.repo_id, "abc123def456")
    updated = get_repo(entry.repo_id)
    assert updated is not None
    assert updated.last_commit == "abc123def456"


def test_is_stale_no_registry(clean_registry, monkeypatch):
    def mock_detect(path):
        return ""
    monkeypatch.setattr("graphify.registry._detect_head", mock_detect)
    assert is_stale("nonexistent") is False


def test_load_empty_registry(clean_registry):
    assert load_registry() == {}


def test_save_and_load_roundtrip(clean_registry):
    entry = register_repo("/fake/roundtrip")
    loaded = load_registry()
    assert entry.repo_id in loaded
    assert loaded[entry.repo_id].name == "roundtrip"


def test_register_existing_updates(clean_registry):
    e1 = register_repo("/fake/reuse")
    e2 = register_repo("/fake/reuse")
    assert e1.repo_id == e2.repo_id
    assert len(list_repos()) == 1
    assert e2.indexed_at


def test_is_stale_no_head(clean_registry, monkeypatch):
    entry = register_repo("/fake/stalecheck")
    update_commit(entry.repo_id, "abc123")
    def mock_detect(path):
        return ""
    monkeypatch.setattr("graphify.registry._detect_head", mock_detect)
    assert is_stale(entry.repo_id) is False


def test_is_stale_matches(clean_registry, monkeypatch):
    entry = register_repo("/fake/stalematched")
    update_commit(entry.repo_id, "abc123")
    def mock_detect(path):
        return "abc123"
    monkeypatch.setattr("graphify.registry._detect_head", mock_detect)
    assert is_stale(entry.repo_id) is False


def test_is_stale_different(clean_registry, monkeypatch):
    entry = register_repo("/fake/stalediff")
    update_commit(entry.repo_id, "abc123")
    def mock_detect(path):
        return "def456"
    monkeypatch.setattr("graphify.registry._detect_head", mock_detect)
    assert is_stale(entry.repo_id) is True


def test_update_commit_nonexistent(clean_registry):
    update_commit("no-such-id", "abc123")


def test_detect_head_non_git(monkeypatch):
    from graphify.registry import _detect_head
    import subprocess
    def mock_run(*args, **kwargs):
        raise FileNotFoundError
    monkeypatch.setattr(subprocess, "run", mock_run)
    assert _detect_head("/nonexistent") == ""

