"""Tests for graphify/query_cache.py."""
import pytest
from pathlib import Path
from graphify.query_cache import QueryCache, get_cache, reseed_cache, _hash_match


class TestQueryCache:
    def test_basic_get_set(self):
        cache = QueryCache(max_size=10)
        cache.set("test_tool", {"q": "hello"}, "result_value")
        assert cache.get("test_tool", {"q": "hello"}) == "result_value"

    def test_cache_miss(self):
        cache = QueryCache(max_size=10)
        assert cache.get("missing_tool", {}) is None

    def test_cache_lru_eviction(self):
        cache = QueryCache(max_size=3)
        for i in range(5):
            cache.set("t", {"i": i}, f"val_{i}")
        assert cache.size == 3
        assert cache.get("t", {"i": 0}) is None
        assert cache.get("t", {"i": 4}) == "val_4"

    def test_cache_key_uniqueness(self):
        cache = QueryCache(max_size=10)
        cache.set("t1", {"a": 1}, "r1")
        cache.set("t2", {"a": 1}, "r2")
        assert cache.get("t1", {"a": 1}) == "r1"
        assert cache.get("t2", {"a": 1}) == "r2"

    def test_cache_with_file_hashes_valid(self):
        cache = QueryCache(max_size=10)
        cache.set("t", {"q": "x"}, "result", {"f1.py": "abc123"})
        assert cache.get("t", {"q": "x"}, {"f1.py": "abc123"}) == "result"

    def test_cache_with_file_hashes_changed(self):
        cache = QueryCache(max_size=10)
        cache.set("t", {"q": "x"}, "result", {"f1.py": "abc123"})
        assert cache.get("t", {"q": "x"}, {"f1.py": "different"}) is None

    def test_cache_with_file_hashes_new_file_no_effect(self):
        cache = QueryCache(max_size=10)
        cache.set("t", {"q": "x"}, "result", {"f1.py": "abc123"})
        assert cache.get("t", {"q": "x"}, {"f1.py": "abc123", "f2.py": "extra"}) == "result"

    def test_cache_with_file_hashes_missing_file(self):
        cache = QueryCache(max_size=10)
        cache.set("t", {"q": "x"}, "result", {"f1.py": "abc123"})
        assert cache.get("t", {"q": "x"}, {}) is None

    def test_invalidate_file(self):
        cache = QueryCache(max_size=10)
        cache.set("t", {"q": "a"}, "r1", {"f1.py": "h1"})
        cache.set("t", {"q": "b"}, "r2", {"f2.py": "h2"})
        cache.set("t", {"q": "c"}, "r3", {"f1.py": "h1", "f3.py": "h3"})
        n = cache.invalidate_file("f1.py")
        assert n == 2
        assert cache.get("t", {"q": "a"}, {"f1.py": "h1"}) is None
        assert cache.get("t", {"q": "c"}, {"f1.py": "h1", "f3.py": "h3"}) is None
        assert cache.get("t", {"q": "b"}, {"f2.py": "h2"}) == "r2"

    def test_invalidate_all(self):
        cache = QueryCache(max_size=10)
        cache.set("t", {"q": "a"}, "r1")
        cache.set("t", {"q": "b"}, "r2")
        n = cache.invalidate_all()
        assert n == 2
        assert cache.size == 0
        assert cache.get("t", {"q": "a"}) is None

    def test_size_property(self):
        cache = QueryCache(max_size=10)
        assert cache.size == 0
        cache.set("t", {"q": "a"}, "r1")
        assert cache.size == 1

    def test_hit_rate_property(self):
        cache = QueryCache(max_size=10)
        cache.set("t", {"q": "a"}, "r1", {"f1.py": "h1"})
        stats = cache.hit_rate
        assert stats["cached_entries"] == 1
        assert stats["tracked_files"] == 1

    def test_get_file_dependents(self):
        cache = QueryCache(max_size=10)
        cache.set("t", {"q": "a"}, "r1", {"f1.py": "h1", "f2.py": "h2"})
        deps = cache.get_file_dependents_for_cache("f1.py")
        assert deps is not None
        assert len(deps) == 1
        deps2 = cache.get_file_dependents_for_cache("nonexistent.py")
        assert deps2 is None

    def test_mru_reorders(self):
        cache = QueryCache(max_size=3)
        cache.set("t", {"i": 0}, "v0")
        cache.set("t", {"i": 1}, "v1")
        cache.set("t", {"i": 2}, "v2")
        cache.get("t", {"i": 0})
        cache.set("t", {"i": 3}, "v3")
        assert cache.get("t", {"i": 0}) == "v0"
        assert cache.get("t", {"i": 1}) is None

    def test_thread_safe_access(self):
        import threading
        cache = QueryCache(max_size=100)
        def worker(start, count):
            for i in range(start, start + count):
                cache.set("t", {"i": i}, f"v{i}")
                cache.get("t", {"i": i})
        threads = [threading.Thread(target=worker, args=(i * 20, 20)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert cache.size > 0


class TestHashMatch:
    def test_exact_match(self):
        assert _hash_match({"a": "x"}, {"a": "x"}) is True

    def test_no_match(self):
        assert _hash_match({"a": "x"}, {"a": "y"}) is False

    def test_missing_key(self):
        assert _hash_match({"a": "x"}, {}) is False

    def test_empty_stored(self):
        assert _hash_match({}, {"any": "val"}) is True

    def test_extra_keys_no_effect(self):
        assert _hash_match({"a": "x"}, {"a": "x", "b": "y"}) is True


class TestGlobalCache:
    def test_get_cache_singleton(self):
        c1 = get_cache()
        c2 = get_cache()
        assert c1 is c2

    def test_reseed_cache_empty(self, tmp_path):
        result = reseed_cache(str(tmp_path / "nonexistent.json"))
        assert result == {}

    def test_reseed_cache_with_graph(self, tmp_path):
        import json
        graph = tmp_path / "graph.json"
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        graph.write_text(json.dumps({
            "nodes": [
                {"id": "n1", "label": "Test", "source_file": str(f)},
            ],
            "edges": [],
        }))
        result = reseed_cache(str(graph))
        assert len(result) >= 1
        assert str(f) in result
