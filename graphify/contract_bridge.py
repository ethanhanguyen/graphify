# Contract bridge - detect shared interfaces across repository boundaries
#
# Identifies common patterns (function signatures, class names, module paths)
# that appear across repos, suggesting shared contracts or potential duplication.
#
from __future__ import annotations
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
import networkx as nx
from networkx.readwrite import json_graph as _jg


def _load_graph(path: str | Path) -> nx.Graph | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        try:
            return _jg.node_link_graph(data, edges="links")
        except TypeError:
            return _jg.node_link_graph(data)
    except (json.JSONDecodeError, OSError):
        return None


def _node_signature(node_data: dict) -> str:
    label = node_data.get("label", "")
    kind = node_data.get("file_type", "")
    language = node_data.get("language", "")
    return f"{label}::{kind}::{language}"


def _normalize_signature(sig: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", sig)
    return cleaned.strip("_").lower()


def detect_shared_interfaces(graph_paths: list[str]) -> list[dict[str, Any]]:
    repo_signatures: dict[str, set[str]] = {}
    repo_labels: dict[str, dict[str, str]] = {}

    for gp in graph_paths:
        G = _load_graph(gp)
        if G is None:
            continue
        repo_name = Path(gp).parent.parent.name
        sigs: set[str] = set()
        labels: dict[str, str] = {}
        for nid, data in G.nodes(data=True):
            raw = _node_signature(data)
            norm = _normalize_signature(raw)
            if norm:
                sigs.add(norm)
                labels[norm] = data.get("label", nid)
        repo_signatures[repo_name] = sigs
        repo_labels[repo_name] = labels

    results: list[dict[str, Any]] = []
    repos = list(repo_signatures.keys())
    for i in range(len(repos)):
        for j in range(i + 1, len(repos)):
            r1, r2 = repos[i], repos[j]
            s1, s2 = repo_signatures[r1], repo_signatures[r2]
            shared = s1 & s2
            if shared:
                examples: list[dict[str, str]] = []
                for nsig in list(shared)[:10]:
                    label_r1 = repo_labels.get(r1, {}).get(nsig, nsig)
                    label_r2 = repo_labels.get(r2, {}).get(nsig, nsig)
                    if label_r1 != label_r2:
                        examples.append({r1: label_r1, r2: label_r2})
                    else:
                        examples.append({"shared": label_r1})
                results.append({
                    "repos": [r1, r2],
                    "shared_count": len(shared),
                    "confidence": min(1.0, len(shared) / 20),
                    "examples": examples[:5],
                })

    return sorted(results, key=lambda r: r["shared_count"], reverse=True)


def bridge_report(graph_paths: list[str]) -> str:
    interfaces = detect_shared_interfaces(graph_paths)
    if not interfaces:
        return "No shared interfaces detected across repos."

    lines = [f"Contract Bridge Report ({len(graph_paths)} repos):\n"]
    for item in interfaces:
        lines.append(f"## {item['repos'][0]} ↔ {item['repos'][1]}")
        lines.append(f"  Shared signatures: {item['shared_count']}")
        lines.append(f"  Confidence: {item['confidence']:.2f}")
        if item["examples"]:
            lines.append("  Examples:")
            for ex in item["examples"]:
                keys = list(ex.keys())
                if "shared" in ex:
                    lines.append(f"    - {ex['shared']}")
                elif len(keys) == 2:
                    lines.append(f"    - {ex[keys[0]]} ↔ {ex[keys[1]]}")
        lines.append("")
    return "\n".join(lines)
