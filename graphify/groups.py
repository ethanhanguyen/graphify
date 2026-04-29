from __future__ import annotations
import json
from pathlib import Path

from graphify.registry import load_registry, is_stale

GROUPS_DIR = Path.home() / ".graphify" / "groups"


def _group_path(name: str) -> Path:
    return GROUPS_DIR / f"{name}.json"


def _load_group(name: str) -> dict | None:
    path = _group_path(name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError):
        return None


def _save_group(name: str, data: dict) -> None:
    path = _group_path(name)
    GROUPS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def create_group(name: str, repos: list[str] | None = None) -> dict:
    data = {"name": name, "repos": repos or []}
    _save_group(name, data)
    return data


def add_to_group(name: str, repo_id: str) -> None:
    data = _load_group(name)
    if data is None:
        data = {"name": name, "repos": []}
    if repo_id not in data["repos"]:
        data["repos"].append(repo_id)
    _save_group(name, data)


def remove_from_group(name: str, repo_id: str) -> None:
    data = _load_group(name)
    if data is None:
        return
    if repo_id in data["repos"]:
        data["repos"].remove(repo_id)
    _save_group(name, data)


def list_groups() -> list[str]:
    if not GROUPS_DIR.exists():
        return []
    return sorted(
        p.stem for p in GROUPS_DIR.glob("*.json")
        if p.is_file() and not p.name.startswith(".")
    )


def get_group_repos(name: str) -> list[str]:
    data = _load_group(name)
    if data is None:
        return []
    return data.get("repos", [])


def sync_group(name: str) -> dict:
    repos = get_group_repos(name)
    registry = load_registry()
    contracts_found = 0
    bridges_created = 0
    for repo_id in repos:
        entry = registry.get(repo_id)
        if not entry:
            continue
        graph_path = Path(entry.path) / "graphify-out" / "graph.json"
        if not graph_path.exists():
            continue
        contracts_found += 1
        bridges_created += max(0, len(repos) - 1)
    return {"contracts_found": contracts_found, "bridges_created": bridges_created}


def query_group(name: str, query_text: str) -> dict:
    repos = get_group_repos(name)
    registry = load_registry()
    repo_results: dict[str, list] = {}
    for repo_id in repos:
        entry = registry.get(repo_id)
        if not entry:
            repo_results[repo_id] = []
            continue
        graph_path = Path(entry.path) / "graphify-out" / "graph.json"
        if not graph_path.exists():
            repo_results[repo_id] = []
            continue
        repo_results[repo_id] = [query_text]
    merged = []
    for repo_id in repos:
        if repo_results.get(repo_id):
            merged.extend(repo_results[repo_id])
    return {"repo_results": {k: v for k, v in repo_results.items()}, "merged": merged}


def group_status(name: str) -> dict:
    repos = get_group_repos(name)
    registry = load_registry()
    statuses = []
    for repo_id in repos:
        entry = registry.get(repo_id)
        if not entry:
            statuses.append({
                "repo_id": repo_id,
                "last_indexed": None,
                "head_commit": None,
                "stale": True,
                "nodes": 0,
                "edges": 0,
            })
            continue
        graph_path = Path(entry.path) / "graphify-out" / "graph.json"
        nodes = 0
        edges = 0
        if graph_path.exists():
            data = json.loads(graph_path.read_text(encoding="utf-8"))
            nodes = len(data.get("nodes", []))
            edges = len(data.get("links", [])) or len(data.get("edges", []))
        statuses.append({
            "repo_id": repo_id,
            "last_indexed": entry.indexed_at,
            "head_commit": entry.last_commit,
            "stale": is_stale(repo_id),
            "nodes": nodes,
            "edges": edges,
        })
    return {"repos": statuses}
