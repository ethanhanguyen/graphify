"""Tests for graphify/lazy_pool.py."""
import json
import pytest
import networkx as nx
from networkx.readwrite import json_graph

from graphify.lazy_pool import GraphPool


def _make_graph_data() -> dict:
    G = nx.Graph()
    G.add_node("n1", label="func_a", source_file="a.py", community=0)
    G.add_node("n2", label="func_b", source_file="b.py", community=1)
    G.add_edge("n1", "n2", relation="calls")
    return json_graph.node_link_data(G, edges="links")


def _write_graph(path, data=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data or _make_graph_data()))


def _mock_registry_entry(monkeypatch, repo_id, path):
    from graphify.registry import RepoEntry
    entry = RepoEntry(repo_id=repo_id, name="test", path=path, last_commit="abc")
    def mock_get_repo(rid):
        if rid == repo_id:
            return entry
        return None
    monkeypatch.setattr("graphify.lazy_pool.get_repo", mock_get_repo)
    return entry


def test_pool_get_graph(tmp_path, monkeypatch):
    repo_dir = tmp_path / "myrepo"
    graph_file = repo_dir / "graphify-out" / "graph.json"
    _write_graph(graph_file)
    _mock_registry_entry(monkeypatch, "test-repo", str(repo_dir))

    pool = GraphPool()
    G = pool.get_graph("test-repo")
    assert G is not None
    assert G.number_of_nodes() == 2
    assert G.number_of_edges() == 1
    pool.close()


def test_pool_caches(tmp_path, monkeypatch):
    repo_dir = tmp_path / "cached"
    graph_file = repo_dir / "graphify-out" / "graph.json"
    _write_graph(graph_file)
    _mock_registry_entry(monkeypatch, "cached-1", str(repo_dir))

    pool = GraphPool()
    g1 = pool.get_graph("cached-1")
    g2 = pool.get_graph("cached-1")
    assert g1 is g2
    pool.close()


def test_pool_eviction(tmp_path, monkeypatch):
    repo_dir = tmp_path / "evictme"
    graph_file = repo_dir / "graphify-out" / "graph.json"
    _write_graph(graph_file)
    _mock_registry_entry(monkeypatch, "evict-1", str(repo_dir))

    pool = GraphPool()
    G = pool.get_graph("evict-1")
    assert G is not None
    pool.evict("evict-1")
    assert "evict-1" not in pool._pool
    pool.close()


def test_pool_evict_expired(monkeypatch, tmp_path):
    repo_dir = tmp_path / "stale"
    graph_file = repo_dir / "graphify-out" / "graph.json"
    _write_graph(graph_file)
    _mock_registry_entry(monkeypatch, "stale-1", str(repo_dir))

    pool = GraphPool(ttl_minutes=0)
    G = pool.get_graph("stale-1")
    assert G is not None

    import time as _time
    now = _time.monotonic()
    monkeypatch.setattr("graphify.lazy_pool.time.monotonic", lambda: now + 9999)
    count = pool.evict_expired()
    assert count == 1
    assert "stale-1" not in pool._pool
    pool.close()


def test_pool_max_open(tmp_path, monkeypatch):
    entries = {}
    for i in range(7):
        rid = f"repo-{i}"
        repo_dir = tmp_path / rid
        graph_file = repo_dir / "graphify-out" / "graph.json"
        _write_graph(graph_file)
        from graphify.registry import RepoEntry
        entries[rid] = RepoEntry(repo_id=rid, name=rid, path=str(repo_dir), last_commit="abc")

    def mock_get_repo(rid):
        return entries.get(rid)
    monkeypatch.setattr("graphify.lazy_pool.get_repo", mock_get_repo)

    pool = GraphPool(max_open=3)
    for i in range(7):
        G = pool.get_graph(f"repo-{i}")
        assert G is not None
    assert len(pool._pool) == 3
    pool.close()


def test_pool_nonexistent_repo():
    pool = GraphPool()
    assert pool.get_graph("no-such-repo") is None
    pool.close()


def test_pool_graph_file_missing(tmp_path, monkeypatch):
    repo_dir = tmp_path / "no-graph"
    from graphify.registry import RepoEntry
    entry = RepoEntry(repo_id="ng-1", name="no-graph", path=str(repo_dir), last_commit="abc")
    def mock_get_repo(rid):
        return entry if rid == "ng-1" else None
    monkeypatch.setattr("graphify.lazy_pool.get_repo", mock_get_repo)
    pool = GraphPool()
    assert pool.get_graph("ng-1") is None
    pool.close()


def test_pool_close_clears():
    pool = GraphPool()
    pool._pool["x"] = (None, 0)
    pool.close()
    assert len(pool._pool) == 0
