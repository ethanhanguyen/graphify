# Multi-repo group management - register, group, sync, query across repos
#
# A registry stores repo paths and metadata (JSON file at ~/.graphify/multirepo.json).
# Groups bundle repos for cross-repo operations.
# Sync ensures each repo in a group has an up-to-date graph.
# Cross-repo queries fan out and merge results via Reciprocal Rank Fusion (RRF).
#
from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_REGISTRY_PATH = Path.home() / ".graphify" / "multirepo.json"


@dataclass
class RepoEntry:
    name: str
    path: str
    graph_path: str = ""
    last_synced: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class GroupEntry:
    name: str
    repo_names: list[str] = field(default_factory=list)
    description: str = ""


def _load_registry() -> dict:
    if _REGISTRY_PATH.exists():
        try:
            return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"repos": {}, "groups": {}}


def _save_registry(data: dict) -> None:
    _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _REGISTRY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, _REGISTRY_PATH)


def register_repo(name: str, path: str | Path) -> RepoEntry:
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Repo path does not exist: {p}")
    graph_p = p / "graphify-out" / "graph.json"
    data = _load_registry()
    entry = RepoEntry(
        name=name,
        path=str(p),
        graph_path=str(graph_p) if graph_p.exists() else "",
    )
    data["repos"][name] = {
        "path": entry.path,
        "graph_path": entry.graph_path,
        "last_synced": entry.last_synced,
        "metadata": entry.metadata,
    }
    _save_registry(data)
    return entry


def unregister_repo(name: str) -> bool:
    data = _load_registry()
    if name in data["repos"]:
        del data["repos"][name]
        for group in data.get("groups", {}).values():
            if name in group.get("repo_names", []):
                group["repo_names"].remove(name)
        _save_registry(data)
        return True
    return False


def list_repos() -> list[RepoEntry]:
    data = _load_registry()
    return [
        RepoEntry(
            name=name,
            path=info.get("path", ""),
            graph_path=info.get("graph_path", ""),
            last_synced=info.get("last_synced", ""),
            metadata=info.get("metadata", {}),
        )
        for name, info in data.get("repos", {}).items()
    ]


def get_repo(name: str) -> RepoEntry | None:
    data = _load_registry()
    info = data.get("repos", {}).get(name)
    if info is None:
        return None
    return RepoEntry(
        name=name,
        path=info.get("path", ""),
        graph_path=info.get("graph_path", ""),
        last_synced=info.get("last_synced", ""),
        metadata=info.get("metadata", {}),
    )


def create_group(name: str, repo_names: list[str], description: str = "") -> GroupEntry:
    data = _load_registry()
    for rname in repo_names:
        if rname not in data.get("repos", {}):
            raise ValueError(f"Repo '{rname}' is not registered. Run register first.")
    entry = GroupEntry(name=name, repo_names=repo_names, description=description)
    data["groups"][name] = {
        "repo_names": repo_names,
        "description": description,
    }
    _save_registry(data)
    return entry


def delete_group(name: str) -> bool:
    data = _load_registry()
    if name in data.get("groups", {}):
        del data["groups"][name]
        _save_registry(data)
        return True
    return False


def list_groups() -> list[GroupEntry]:
    data = _load_registry()
    return [
        GroupEntry(
            name=name,
            repo_names=info.get("repo_names", []),
            description=info.get("description", ""),
        )
        for name, info in data.get("groups", {}).items()
    ]


def get_group(name: str) -> GroupEntry | None:
    data = _load_registry()
    info = data.get("groups", {}).get(name)
    if info is None:
        return None
    return GroupEntry(
        name=name,
        repo_names=info.get("repo_names", []),
        description=info.get("description", ""),
    )


def sync_group(name: str) -> dict[str, str]:
    group = get_group(name)
    if group is None:
        raise ValueError(f"Group '{name}' not found.")
    results: dict[str, str] = {}
    for rname in group.repo_names:
        entry = get_repo(rname)
        if entry is None:
            results[rname] = "not registered"
            continue
        p = Path(entry.path)
        graph_p = p / "graphify-out"
        if not graph_p.exists():
            results[rname] = "no graph built yet"
            continue
        graph_file = graph_p / "graph.json"
        if graph_file.exists():
            results[rname] = str(graph_file)
        else:
            results[rname] = "graph.json missing"
    return results


def group_graph_paths(name: str) -> list[str]:
    group = get_group(name)
    if group is None:
        raise ValueError(f"Group '{name}' not found.")
    paths: list[str] = []
    for rname in group.repo_names:
        entry = get_repo(rname)
        if entry is None:
            continue
        p = Path(entry.path) / "graphify-out" / "graph.json"
        if p.exists():
            paths.append(str(p))
    return paths
