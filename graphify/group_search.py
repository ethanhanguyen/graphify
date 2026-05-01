# Group-aware search - fan out queries across repos and merge via RRF
#
# Reciprocal Rank Fusion (RRF) merges ranked results from multiple repos
# into a single coherent ranking. Each repo contributes scored results;
# RRF ensures repos don't dominate each other via rank normalization.
#
from __future__ import annotations
from typing import Any


def _rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)


def _fan_out(
    query: str,
    graph_paths: list[str],
    options: dict | None = None,
) -> list[tuple[str, list[dict[str, Any]]]]:
    opts = options or {}
    repo_results: list[tuple[str, list[dict[str, Any]]]] = []

    for gp in graph_paths:
        results = _query_single_repo(gp, query, opts)
        repo_results.append((gp, results))

    return repo_results


def _query_single_repo(
    graph_path: str,
    query: str,
    options: dict,
) -> list[dict[str, Any]]:
    import json
    from pathlib import Path
    import networkx as nx
    from networkx.readwrite import json_graph as _jg

    p = Path(graph_path)
    if not p.exists():
        return []

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        try:
            G = _jg.node_link_graph(data, edges="links")
        except TypeError:
            G = _jg.node_link_graph(data)
    except (json.JSONDecodeError, OSError):
        return []

    limit = options.get("limit", 10)
    results: list[dict[str, Any]] = []

    try:
        from graphify.search import hybrid_search
        sr = hybrid_search(query, G, {"limit": limit})
        refs = sr.get("references", [])
        if refs:
            for ref in refs[:limit]:
                results.append({
                    "name": ref.get("name", "?"),
                    "type": ref.get("type", ""),
                    "file": ref.get("file", ""),
                    "repo": p.parent.parent.name,
                    "score": ref.get("score", 0.5),
                })
            return results
    except ImportError:
        pass

    terms = [t.lower() for t in query.split() if len(t) > 2]
    from graphify.serve import _score_nodes
    scored = _score_nodes(G, terms)
    for score, nid in scored[:limit]:
        data = G.nodes[nid]
        results.append({
            "name": data.get("label", nid),
            "type": data.get("file_type", ""),
            "file": data.get("source_file", ""),
            "repo": p.parent.parent.name,
            "score": score,
        })
    return results


def group_search(
    query: str,
    graph_paths: list[str],
    options: dict | None = None,
) -> dict[str, Any]:
    repo_results = _fan_out(query, graph_paths, options)
    opts = options or {}
    limit = opts.get("limit", 10)

    merged: dict[str, dict[str, Any]] = {}
    for repo_path, results in repo_results:
        for rank, item in enumerate(results, 1):
            key = f"{item['name']}::{item.get('file', '')}"
            rrf = _rrf_score(rank)
            if key in merged:
                merged[key]["score"] += rrf
                merged[key]["repos"].add(item.get("repo", ""))
            else:
                merged[key] = {
                    "name": item["name"],
                    "type": item["type"],
                    "file": item["file"],
                    "repos": {item.get("repo", "")},
                    "score": rrf,
                }

    sorted_results = sorted(merged.values(), key=lambda r: r["score"], reverse=True)
    for r in sorted_results:
        r["repos"] = sorted(r["repos"])

    return {
        "query": query,
        "repos_searched": len(graph_paths),
        "total_results": len(sorted_results),
        "results": sorted_results[:limit],
    }


def group_search_text(query: str, graph_paths: list[str], options: dict | None = None) -> str:
    result = group_search(query, graph_paths, options)
    lines = [
        f"Cross-repo search for '{query}':",
        f"  Repos searched: {result['repos_searched']}",
        f"  Total results: {result['total_results']}",
        "",
    ]
    for i, r in enumerate(result["results"], 1):
        repos_str = ", ".join(r["repos"])
        lines.append(f"{i}. {r['name']} [{r.get('type', '')}] {r.get('file', '')} (score={r['score']:.3f}, repos={repos_str})")
    return "\n".join(lines)
