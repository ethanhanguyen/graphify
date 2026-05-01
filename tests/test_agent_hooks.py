"""Tests for graphify/agent_hooks.py."""
import json
import pytest
from pathlib import Path
from graphify.agent_hooks import (
    PreToolUseHook,
    PostToolUseHook,
    _is_search_command,
    _build_pre_tool_context,
)


class TestPreToolUseHook:
    def test_apply_search_tools(self):
        hook = PreToolUseHook()
        for tool in ("grep", "find", "rg", "fd", "ack", "ag", "ls", "glob"):
            result = hook.apply(tool, {})
            if result:
                assert "graphify" in result

    def test_apply_non_search_tool(self):
        hook = PreToolUseHook()
        result = hook.apply("edit_file", {})
        assert result is None

    def test_apply_bash_search(self):
        hook = PreToolUseHook()
        result = hook.apply("bash", {"command": "grep -r pattern ."})
        if result:
            assert "graphify" in result

    def test_apply_bash_non_search(self):
        hook = PreToolUseHook()
        result = hook.apply("bash", {"command": "npm install"})
        assert result is None

    def test_no_graph_file(self, tmp_path):
        hook = PreToolUseHook(graph_path=str(tmp_path / "nonexistent.json"))
        result = hook.apply("grep", {})
        assert result is None


class TestPostToolUseHook:
    def test_track_files(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        hook = PostToolUseHook()
        hook.track_files([str(f)])
        assert str(f) in hook._tracked_hashes

    def test_detect_no_changes(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        hook = PostToolUseHook()
        hook.track_files([str(f)])
        changed = hook.detect_changes("write", {})
        assert changed == []

    def test_detect_changes(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        hook = PostToolUseHook()
        hook.track_files([str(f)])
        f.write_text("x = 2")
        changed = hook.detect_changes("write", {})
        assert len(changed) == 1
        assert str(f) in changed

    def test_non_file_change_tool_skipped(self, tmp_path):
        hook = PostToolUseHook()
        changed = hook.detect_changes("read", {})
        assert changed == []

    def test_invalidate_affected(self, tmp_path):
        from graphify.query_cache import get_cache
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        hook = PostToolUseHook()
        hook.track_files([str(f)])
        cache = get_cache()
        cache.set("t", {"q": "a"}, "r1", {str(f): "oldhash"})
        f.write_text("x = 2")
        changed = hook.detect_changes("write", {})
        info = hook.invalidate_affected(changed)
        assert info["changed_files"] == 1

    def test_handle_post_tool_write(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        hook = PostToolUseHook()
        hook.track_files([str(f)])
        f.write_text("x = 2")
        result = hook.handle_post_tool("write", {})
        assert result is not None
        assert "changed" in result.lower()

    def test_handle_post_tool_non_write(self):
        hook = PostToolUseHook()
        result = hook.handle_post_tool("read", {})
        assert result is None


class TestIsSearchCommand:
    def test_bash_grep(self):
        assert _is_search_command("bash", {"command": "grep -r pattern"}) is True

    def test_bash_rg(self):
        assert _is_search_command("bash", {"command": "rg pattern ."}) is True

    def test_bash_find(self):
        assert _is_search_command("bash", {"command": "find . -name '*.py'"}) is True

    def test_bash_not_search(self):
        assert _is_search_command("bash", {"command": "python main.py"}) is False

    def test_non_bash_tool(self):
        assert _is_search_command("grep", {}) is False

    def test_command_is_list(self):
        assert _is_search_command("bash", {"command": ["ls", "-la"]}) is False


class TestBuildPreToolContext:
    def test_build_from_data(self):
        data = {
            "nodes": [
                {"id": "n1", "label": "Auth", "source_file": "auth.py", "community": 0},
                {"id": "n2", "label": "Login", "source_file": "login.py", "community": 0},
                {"id": "n3", "label": "Config", "source_file": "config.py", "community": 1},
            ],
            "edges": [
                {"source": "n1", "target": "n2", "relation": "calls"},
                {"source": "n2", "target": "n3", "relation": "imports"},
                {"source": "n1", "target": "n3", "relation": "calls"},
            ],
        }
        result = _build_pre_tool_context(data)
        assert "Graph" in result
        assert "3 nodes" in result
        assert "communities" in result.lower()

    def test_build_from_links(self):
        data = {
            "nodes": [{"id": "n1", "label": "A"}],
            "links": [{"source": "n1", "target": "n2"}],
        }
        result = _build_pre_tool_context(data)
        assert "Graph" in result

    def test_build_empty(self):
        data = {"nodes": [], "edges": []}
        result = _build_pre_tool_context(data)
        assert "0 nodes" in result

    def test_build_with_god_nodes(self):
        data = {
            "nodes": [
                {"id": "n1", "label": "Hub1"},
                {"id": "n2", "label": "Hub2"},
                {"id": "n3", "label": "Leaf"},
            ],
            "edges": [
                {"source": "n1", "target": "n2"},
                {"source": "n1", "target": "n3"},
                {"source": "n2", "target": "n1"},
                {"source": "n2", "target": "n3"},
            ],
        }
        result = _build_pre_tool_context(data)
        assert "Top concepts" in result
