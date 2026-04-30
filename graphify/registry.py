from __future__ import annotations
import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REGISTRY_PATH = Path.home() / ".graphify" / "registry.json"


@dataclass
class RepoEntry:
    repo_id: str
    name: str
    path: str
    last_commit: str = ""
    group: str | None = None
    url: str | None = None
    indexed_at: str = ""


def _make_repo_id(repo_path: str) -> str:
    stem = Path(repo_path).resolve().name
    h = hashlib.sha256(repo_path.encode()).hexdigest()[:8]
    return f"{stem}-{h}"


def _detect_head(repo_path: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return ""


def load_registry() -> dict[str, RepoEntry]:
    if not REGISTRY_PATH.exists():
        return {}
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError):
        return {}
    result: dict[str, RepoEntry] = {}
    for repo_id, entry_dict in data.items():
        entry_dict["repo_id"] = repo_id
        result[repo_id] = RepoEntry(**entry_dict)
    return result


def save_registry(registry: dict[str, RepoEntry]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY_PATH.with_suffix(".json.tmp")
    data = {}
    for repo_id, entry in registry.items():
        item = {
            "name": entry.name,
            "path": entry.path,
            "last_commit": entry.last_commit,
            "group": entry.group,
            "url": entry.url,
            "indexed_at": entry.indexed_at,
        }
        data[repo_id] = item
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(REGISTRY_PATH)


def register_repo(repo_path: str, meta: dict | None = None) -> RepoEntry:
    resolved = str(Path(repo_path).resolve())
    repo_id = _make_repo_id(resolved)
    name = meta.get("name", Path(resolved).name) if meta else Path(resolved).name
    registry = load_registry()
    if repo_id in registry:
        entry = registry[repo_id]
        entry.last_commit = _detect_head(resolved)
        entry.indexed_at = datetime.now(timezone.utc).isoformat()
        if meta:
            entry.url = meta.get("url", entry.url)
            entry.group = meta.get("group", entry.group)
        save_registry(registry)
        return entry
    entry = RepoEntry(
        repo_id=repo_id,
        name=name,
        path=resolved,
        last_commit=_detect_head(resolved),
        group=meta.get("group") if meta else None,
        url=meta.get("url") if meta else None,
        indexed_at=datetime.now(timezone.utc).isoformat(),
    )
    registry[repo_id] = entry
    save_registry(registry)
    return entry


def unregister_repo(repo_id: str) -> bool:
    registry = load_registry()
    if repo_id not in registry:
        return False
    del registry[repo_id]
    save_registry(registry)
    return True


def list_repos() -> list[RepoEntry]:
    return list(load_registry().values())


def get_repo(repo_id: str) -> RepoEntry | None:
    return load_registry().get(repo_id)


def update_commit(repo_id: str, commit: str) -> None:
    registry = load_registry()
    if repo_id in registry:
        registry[repo_id].last_commit = commit
        registry[repo_id].indexed_at = datetime.now(timezone.utc).isoformat()
        save_registry(registry)


def is_stale(repo_id: str) -> bool:
    registry = load_registry()
    entry = registry.get(repo_id)
    if not entry or not entry.last_commit:
        return False
    head = _detect_head(entry.path)
    if not head:
        return False
    return head != entry.last_commit
