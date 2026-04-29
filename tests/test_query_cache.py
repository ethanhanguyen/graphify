import time
import hashlib
from graphify.query_cache import (
    cache_key,
    get_cached_query,
    set_cached_query,
    clear_expired_cache,
    cache_stats,
    CACHE_TTL,
)


def _cache_key(q: str, mode: str = "bfs", depth: int = 3, budget: int = 2000) -> str:
    return hashlib.sha256(f"{q}|{mode}|{depth}|{budget}".encode()).hexdigest()


def test_cache_key_deterministic():
    key1 = cache_key("test", "bfs", 3, 2000)
    key2 = cache_key("test", "bfs", 3, 2000)
    assert key1 == key2
    assert len(key1) == 64


def test_cache_key_different_params():
    key1 = cache_key("test", "bfs", 3, 2000)
    key2 = cache_key("test", "dfs", 3, 2000)
    assert key1 != key2


def test_set_and_get_cached_query(tmp_path):
    cache_dir = tmp_path / "query_cache"
    key = _cache_key("What is Transformer?")
    set_cached_query(cache_dir, key, "result text")
    result = get_cached_query(cache_dir, key)
    assert result == "result text"


def test_expired_cache_not_returned(tmp_path):
    cache_dir = tmp_path / "query_cache"
    key = _cache_key("stale query")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{key}.txt"
    old_ts = time.time() - CACHE_TTL - 10
    cache_file.write_text(f"{old_ts}\nstale result")
    result = get_cached_query(cache_dir, key)
    assert result is None


def test_clear_expired_cache(tmp_path):
    cache_dir = tmp_path / "query_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _cache_key("stale")
    old_ts = time.time() - CACHE_TTL - 60
    (cache_dir / f"{key}.txt").write_text(f"{old_ts}\nold")
    valid_key = _cache_key("fresh", "dfs", 2, 1000)
    (cache_dir / f"{valid_key}.txt").write_text(f"{time.time()}\nfresh")
    removed = clear_expired_cache(cache_dir)
    assert removed == 1
    assert not (cache_dir / f"{key}.txt").exists()
    assert (cache_dir / f"{valid_key}.txt").exists()


def test_cache_miss_returns_none(tmp_path):
    cache_dir = tmp_path / "query_cache"
    key = _cache_key("nonexistent")
    result = get_cached_query(cache_dir, key)
    assert result is None


def test_cache_stats(tmp_path):
    cache_dir = tmp_path / "query_cache"
    key = _cache_key("stats test")
    set_cached_query(cache_dir, key, "data")
    get_cached_query(cache_dir, key)
    stats = cache_stats(cache_dir)
    assert stats["entries"] >= 1
    assert stats["hits"] >= 1


def test_cache_stats_empty(tmp_path):
    cache_dir = tmp_path / "empty"
    stats = cache_stats(cache_dir)
    assert stats["entries"] == 0
    assert stats["hits"] == 0
    assert stats["misses"] == 0
    assert stats["hit_rate"] == 0.0


def test_clear_expired_cache_nonexistent():
    from pathlib import Path
    removed = clear_expired_cache(Path("/nonexistent/path"))
    assert removed == 0
