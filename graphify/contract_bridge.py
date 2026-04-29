from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from graphify.lazy_pool import GraphPool
import networkx as nx


def detect_shared_interfaces(graphs: dict[str, nx.Graph]) -> list[dict]:
    index: dict[str, set[str]] = {}
    for repo_id, G in graphs.items():
        for nid, data in G.nodes(data=True):
            node_type = data.get("node_type", data.get("file_type", ""))
            if node_type not in ("class", "interface", "type_alias"):
                continue
            label = (data.get("label", nid) or "").lower()
            if not label:
                continue
            index.setdefault(label, set()).add(repo_id)
    results: list[dict] = []
    for label, repos in index.items():
        if len(repos) < 2:
            continue
        methods: list[str] = []
        seen_methods: set[str] = set()
        for repo_id, G in graphs.items():
            if repo_id not in repos:
                continue
            for nid, data in G.nodes(data=True):
                if (data.get("label", nid) or "").lower() != label:
                    continue
                for neighbor in G.neighbors(nid):
                    edge_data = G.edges[nid, neighbor]
                    if edge_data.get("relation") == "defines":
                        m_label = G.nodes[neighbor].get("label", neighbor)
                        sig = data.get("signature", "")
                        m_key = f"{m_label}{sig}"
                        if m_key not in seen_methods:
                            methods.append(m_label)
                            seen_methods.add(m_key)
        results.append({
            "interface_name": label,
            "repos": sorted(repos),
            "methods": sorted(methods),
        })
    return results


def detect_shared_types(graphs: dict[str, nx.Graph]) -> list[dict]:
    return detect_shared_interfaces(graphs)


def map_api_consumers(
    api_repo_id: str,
    consumer_repos: list[str],
    pool: GraphPool,
) -> list[dict]:
    results: list[dict] = []
    api_graph = pool.get_graph(api_repo_id)
    if api_graph is None:
        return results
    api_routes: dict[str, str] = {}
    for nid, data in api_graph.nodes(data=True):
        label = data.get("label", nid)
        node_type = data.get("node_type", "")
        if node_type == "route" or "/" in label:
            api_routes[label] = nid
    for repo_id in consumer_repos:
        consumer = pool.get_graph(repo_id)
        if consumer is None:
            continue
        for route_label, api_nid in api_routes.items():
            for nid, data in consumer.nodes(data=True):
                if "route" in (data.get("label", nid) or "").lower():
                    api_data = api_graph.nodes[api_nid]
                    results.append({
                        "consumer_repo": repo_id,
                        "route": route_label,
                        "provider_file": api_data.get("source_file", ""),
                        "consumer_file": data.get("source_file", ""),
                    })
    return results


def build_cross_repo_edges(
    repo_a: str,
    repo_b: str,
    pool: GraphPool,
) -> list[dict]:
    edges: list[dict] = []
    G_a = pool.get_graph(repo_a)
    G_b = pool.get_graph(repo_b)
    if G_a is None or G_b is None:
        return edges
    shared = detect_shared_interfaces({repo_a: G_a, repo_b: G_b})
    for item in shared:
        edges.append({
            "source_repo": item["repos"][0],
            "target_repo": item["repos"][1],
            "interface": item["interface_name"],
            "relation": "shared_interface",
            "methods": item["methods"],
        })
    return edges
