# MCP stdio server - exposes graph query tools to Claude and other agents
from __future__ import annotations
import json
import sys
from pathlib import Path
import networkx as nx
from networkx.readwrite import json_graph
from graphify.security import sanitize_label
from graphify.query_cache import get_cache, reseed_cache

_CONFIDENCE_PRIORITY = {"EXTRACTED": 0, "INFERRED": 1, "AMBIGUOUS": 2}


def _load_graph_file(graph_path: str | Path) -> nx.Graph:
    p = Path(graph_path).resolve()
    if not p.exists() and p.suffix == ".json":
        gz = p.with_suffix(".json.gz")
        if gz.exists():
            p = gz
    if not p.exists():
        raise FileNotFoundError(f"Graph file not found: {p}")
    is_gz = p.suffix == ".gz" or p.name.endswith(".json.gz")
    try:
        if is_gz:
            import gzip
            raw_bytes = gzip.decompress(p.read_bytes())
            data = json.loads(raw_bytes.decode("utf-8"))
        else:
            raw_bytes = p.read_bytes()
            try:
                import orjson
                data = orjson.loads(raw_bytes)
            except ImportError:
                data = json.loads(raw_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"graph.json is corrupted ({exc}). Re-run /graphify to rebuild.") from exc
    try:
        return json_graph.node_link_graph(data, edges="links")
    except TypeError:
        return json_graph.node_link_graph(data)


def _load_graph(graph_path: str) -> nx.Graph:
    try:
        return _load_graph_file(graph_path)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"error: graph.json is corrupted ({exc}). Re-run /graphify to rebuild.", file=sys.stderr)
        sys.exit(1)


def _communities_from_graph(G: nx.Graph) -> dict[int, list[str]]:
    """Reconstruct community dict from community property stored on nodes."""
    communities: dict[int, list[str]] = {}
    for node_id, data in G.nodes(data=True):
        cid = data.get("community")
        if cid is not None:
            communities.setdefault(int(cid), []).append(node_id)
    return communities


def _strip_diacritics(text: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _score_nodes(G: nx.Graph, terms: list[str]) -> list[tuple[float, str]]:
    scored = []
    norm_terms = [_strip_diacritics(t).lower() for t in terms]
    for nid, data in G.nodes(data=True):
        norm_label = data.get("norm_label") or _strip_diacritics(data.get("label") or "").lower()
        source = (data.get("source_file") or "").lower()
        score = sum(1 for t in norm_terms if t in norm_label) + sum(0.5 for t in norm_terms if t in source)
        if score > 0:
            scored.append((score, nid))
    return sorted(scored, reverse=True)


def _bfs(G: nx.Graph, start_nodes: list[str], depth: int) -> tuple[set[str], list[tuple]]:
    visited: set[str] = set(start_nodes)
    frontier = set(start_nodes)
    edges_seen: list[tuple] = []
    for _ in range(depth):
        next_frontier: set[str] = set()
        for n in frontier:
            for neighbor in G.neighbors(n):
                if neighbor not in visited:
                    next_frontier.add(neighbor)
                    edges_seen.append((n, neighbor))
        visited.update(next_frontier)
        frontier = next_frontier
    return visited, edges_seen


def _dfs(G: nx.Graph, start_nodes: list[str], depth: int) -> tuple[set[str], list[tuple]]:
    visited: set[str] = set()
    edges_seen: list[tuple] = []
    stack = [(n, 0) for n in reversed(start_nodes)]
    while stack:
        node, d = stack.pop()
        if node in visited or d > depth:
            continue
        visited.add(node)
        for neighbor in G.neighbors(node):
            if neighbor not in visited:
                stack.append((neighbor, d + 1))
                edges_seen.append((node, neighbor))
    return visited, edges_seen


def _select_best_start_node(G: nx.Graph, candidates: list[str]) -> str:
    """Select the lowest-degree candidate node for optimal traversal performance."""
    if not candidates:
        return ""
    return min(candidates, key=lambda n: G.degree(n))


def _prefer_extracted_edges(G: nx.Graph, frontier: list[str]) -> list[str]:
    """Sort frontier by confidence tier: EXTRACTED edges explored first."""
    def _conf_prio(node):
        min_prio = 2
        for nb in G.neighbors(node):
            e = G.edges.get((node, nb)) or G.edges.get((nb, node))
            if e:
                conf = e.get("confidence", "EXTRACTED")
                min_prio = min(min_prio, _CONFIDENCE_PRIORITY.get(conf, 1))
        return min_prio
    return sorted(frontier, key=_conf_prio)


def _bidirectional_shortest_path(
    G: nx.Graph,
    src: str,
    tgt: str,
    max_hops: int = 8,
    edge_types: list[str] | None = None,
) -> tuple[list[str], int]:
    """Bidirectional BFS for O(b^(d/2)) shortest path finding.

    Returns (path_nodes, hops) or ([], -1) if no path found.
    When edge_types is provided, only traverses edges of those relation types.
    """
    if src == tgt:
        return [src], 0

    def _neighbors(node):
        if edge_types:
            for nb in G.neighbors(node):
                e = G.edges.get((node, nb)) or G.edges.get((nb, node))
                if e and e.get("relation", "") in edge_types:
                    yield nb
        else:
            yield from G.neighbors(node)

    fwd_visited: dict[str, str | None] = {src: None}
    bwd_visited: dict[str, str | None] = {tgt: None}
    fwd_frontier = {src}
    bwd_frontier = {tgt}

    for hops in range(max_hops + 1):
        if len(fwd_frontier) <= len(bwd_frontier):
            next_set: set[str] = set()
            for node in fwd_frontier:
                for nb in _neighbors(node):
                    if nb not in fwd_visited:
                        fwd_visited[nb] = node
                        next_set.add(nb)
                        if nb in bwd_visited:
                            return _reconstruct_bidir_path(
                                fwd_visited, bwd_visited, nb
                            ), hops + 1
            fwd_frontier = next_set
        else:
            next_set = set()
            for node in bwd_frontier:
                for nb in _neighbors(node):
                    if nb not in bwd_visited:
                        bwd_visited[nb] = node
                        next_set.add(nb)
                        if nb in fwd_visited:
                            return _reconstruct_bidir_path(
                                fwd_visited, bwd_visited, nb
                            ), hops + 1
            bwd_frontier = next_set
    return [], -1


def _reconstruct_bidir_path(
    fwd: dict[str, str | None], bwd: dict[str, str | None], midpoint: str
) -> list[str]:
    path: list[str] = []
    node = midpoint
    while node is not None:
        path.append(node)
        node = fwd[node]
    path.reverse()
    node = bwd[midpoint]
    while node is not None:
        path.append(node)
        node = bwd[node]
    return path


def _weighted_dijkstra(
    G: nx.Graph,
    src: str,
    tgt: str,
    weight_field: str = "confidence_score",
) -> tuple[list[str], float]:
    """Dijkstra with configurable weight field. Lower weight = preferred path."""
    import heapq

    if src not in G or tgt not in G:
        return [], -1.0

    dist: dict[str, float] = {src: 0}
    prev: dict[str, str] = {}
    pq = [(0.0, src)]

    while pq:
        d, node = heapq.heappop(pq)
        if node == tgt:
            path = []
            while node in prev:
                path.append(node)
                node = prev[node]
            path.append(src)
            path.reverse()
            return path, d
        if d > dist.get(node, float("inf")):
            continue
        for nb in G.neighbors(node):
            edata = G.get_edge_data(node, nb)
            if edata:
                w = 1.0 - edata.get(weight_field, 0.5)
                w = max(w, 0.01)
            else:
                w = 0.5
            nd = d + w
            if nd < dist.get(nb, float("inf")):
                dist[nb] = nd
                prev[nb] = node
                heapq.heappush(pq, (nd, nb))
    return [], -1.0


def _community_aware_heuristic(G: nx.Graph, node: str, tgt: str) -> float:
    """Heuristic: prefer nodes in the same community as the target."""
    tgt_comm = G.nodes[tgt].get("community")
    node_comm = G.nodes[node].get("community")
    if tgt_comm is not None and node_comm == tgt_comm:
        return 0.0
    return 1.0


def _astar(
    G: nx.Graph,
    src: str,
    tgt: str,
    max_hops: int = 8,
) -> tuple[list[str], int]:
    """A* search with community-aware heuristic (fewer community hops = better)."""
    import heapq

    if src == tgt:
        return [src], 0
    if src not in G or tgt not in G:
        return [], -1

    g_score: dict[str, float] = {src: 0}
    f_score: dict[str, float] = {src: _community_aware_heuristic(G, src, tgt)}
    prev: dict[str, str] = {}
    open_set = [(f_score[src], src)]
    visited = set()

    while open_set:
        _, current = heapq.heappop(open_set)
        if current in visited:
            continue
        visited.add(current)
        if current == tgt:
            path = []
            node = current
            while node in prev:
                path.append(node)
                node = prev[node]
            path.append(src)
            path.reverse()
            return path, len(path) - 1
        for nb in G.neighbors(current):
            if nb in visited:
                continue
            tentative_g = g_score[current] + 1
            if tentative_g < g_score.get(nb, float("inf")):
                prev[nb] = current
                g_score[nb] = tentative_g
                f_score[nb] = tentative_g + _community_aware_heuristic(G, nb, tgt)
                heapq.heappush(open_set, (f_score[nb], nb))
    return [], -1


def _subgraph_to_text(G: nx.Graph, nodes: set[str], edges: list[tuple], token_budget: int = 2000) -> str:
    """Render subgraph as text, cutting at token_budget (approx 3 chars/token)."""
    char_budget = token_budget * 3
    lines = []
    for nid in sorted(nodes, key=lambda n: G.degree(n), reverse=True):
        d = G.nodes[nid]
        line = f"NODE {sanitize_label(d.get('label', nid))} [src={d.get('source_file', '')} loc={d.get('source_location', '')} community={d.get('community', '')}]"
        lines.append(line)
    for u, v in edges:
        if u in nodes and v in nodes:
            raw = G[u][v]
            d = next(iter(raw.values()), {}) if isinstance(G, (nx.MultiGraph, nx.MultiDiGraph)) else raw
            line = f"EDGE {sanitize_label(G.nodes[u].get('label', u))} --{d.get('relation', '')} [{d.get('confidence', '')}]--> {sanitize_label(G.nodes[v].get('label', v))}"
            lines.append(line)
    output = "\n".join(lines)
    if len(output) > char_budget:
        output = output[:char_budget] + f"\n... (truncated to ~{token_budget} token budget)"
    return output


def _find_node(G: nx.Graph, label: str) -> list[str]:
    """Return node IDs whose label or ID matches the search term (diacritic-insensitive)."""
    term = _strip_diacritics(label).lower()
    return [nid for nid, d in G.nodes(data=True)
            if term in (d.get("norm_label") or _strip_diacritics(d.get("label") or "").lower())
            or term == nid.lower()]


def _filter_blank_stdin() -> None:
    """Filter blank lines from stdin before MCP reads it.

    Some MCP clients (Claude Desktop, etc.) send blank lines between JSON
    messages. The MCP stdio transport tries to parse every line as a
    JSONRPCMessage, so a bare newline triggers a Pydantic ValidationError.
    This installs an OS-level pipe that relays stdin while dropping blanks.
    """
    import os
    import threading

    r_fd, w_fd = os.pipe()
    saved_fd = os.dup(sys.stdin.fileno())

    def _relay() -> None:
        try:
            with open(saved_fd, "rb") as src, open(w_fd, "wb") as dst:
                for line in src:
                    if line.strip():
                        dst.write(line)
                        dst.flush()
        except Exception:
            pass

    threading.Thread(target=_relay, daemon=True).start()
    os.dup2(r_fd, sys.stdin.fileno())
    os.close(r_fd)
    sys.stdin = open(0, "r", closefd=False)


def serve(graph_path: str = "graphify-out/graph.json") -> None:
    """Start the MCP server. Requires pip install mcp."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp import types
    except ImportError as e:
        raise ImportError("mcp not installed. Run: pip install mcp") from e

    G = _load_graph(graph_path)
    communities = _communities_from_graph(G)

    server = Server("graphify")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="query_graph",
                description="Search the knowledge graph using hybrid, BFS, or DFS. Default: hybrid (BM25+semantic).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "Natural language question or keyword search"},
                        "mode": {"type": "string", "enum": ["hybrid", "bfs", "dfs"], "default": "hybrid",
                                 "description": "hybrid=BM25+semantic fusion, bfs=broad context, dfs=trace a specific path"},
                        "depth": {"type": "integer", "default": 3, "description": "Traversal depth (1-6) for bfs/dfs modes"},
                        "limit": {"type": "integer", "default": 10, "description": "Max results for hybrid mode"},
                        "token_budget": {"type": "integer", "default": 2000, "description": "Max output tokens"},
                    },
                    "required": ["question"],
                },
            ),
            types.Tool(
                name="get_node",
                description="Get full details for a specific node by label or ID.",
                inputSchema={
                    "type": "object",
                    "properties": {"label": {"type": "string", "description": "Node label or ID to look up"}},
                    "required": ["label"],
                },
            ),
            types.Tool(
                name="get_neighbors",
                description="Get all direct neighbors of a node with edge details.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "relation_filter": {"type": "string", "description": "Optional: filter by relation type"},
                    },
                    "required": ["label"],
                },
            ),
            types.Tool(
                name="get_community",
                description="Get all nodes in a community by community ID.",
                inputSchema={
                    "type": "object",
                    "properties": {"community_id": {"type": "integer", "description": "Community ID (0-indexed by size)"}},
                    "required": ["community_id"],
                },
            ),
            types.Tool(
                name="god_nodes",
                description="Return the most connected nodes - the core abstractions of the knowledge graph.",
                inputSchema={"type": "object", "properties": {"top_n": {"type": "integer", "default": 10}}},
            ),
            types.Tool(
                name="graph_stats",
                description="Return summary statistics: node count, edge count, communities, confidence breakdown.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name=                "shortest_path",
                description="Find the shortest path between two concepts in the knowledge graph.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "Source concept label or keyword"},
                        "target": {"type": "string", "description": "Target concept label or keyword"},
                        "max_hops": {"type": "integer", "default": 8, "description": "Maximum hops to consider"},
                        "algorithm": {"type": "string", "enum": ["bidirectional", "dijkstra", "astar"], "default": "bidirectional",
                                      "description": "Pathfinding algorithm"},
                        "edge_types": {"type": "array", "items": {"type": "string"},
                                       "description": "Optional: restrict to these edge relation types"},
                    },
                    "required": ["source", "target"],
                },
            ),
            types.Tool(
                name="context",
                description="Get 360° context for a symbol: incoming/outgoing calls, imports, exports, and process membership.",
                inputSchema={
                    "type": "object",
                    "properties": {"name": {"type": "string", "description": "Symbol name to look up"}},
                    "required": ["name"],
                },
            ),
            types.Tool(
                name="impact",
                description="Analyze blast radius: what depends on this symbol? Returns upstream/downstream impact with risk scoring.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "Target symbol"},
                        "direction": {"type": "string", "enum": ["upstream", "downstream", "both"], "default": "both"},
                        "min_confidence": {"type": "number", "default": 0.5},
                        "max_depth": {"type": "integer", "default": 5},
                    },
                    "required": ["target"],
                },
            ),
            types.Tool(
                name="trace",
                description="Trace full execution flow from an entry point through all call chains.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entry_point": {"type": "string", "description": "Entry point name to trace"},
                        "max_depth": {"type": "integer", "default": 20},
                    },
                    "required": ["entry_point"],
                },
            ),
            types.Tool(
                name="detect_changes",
                description="Detect code changes and identify affected symbols, processes, and risk level.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "scope": {"type": "string", "enum": ["all", "uncommitted"], "default": "all"},
                    },
                },
            ),
            types.Tool(
                name="cache_stats",
                description="Return query cache statistics: hit rate, size, tracked files.",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    def _tool_query_graph(arguments: dict) -> str:
        question = arguments["question"]
        mode = arguments.get("mode", "hybrid")
        depth = min(int(arguments.get("depth", 3)), 6)
        budget = int(arguments.get("token_budget", 2000))
        limit = int(arguments.get("limit", 10))

        cache = get_cache()
        file_hashes = reseed_cache(graph_path)
        cached_result = cache.get("query_graph", {
            "question": question, "mode": mode, "depth": depth, "limit": limit
        }, file_hashes)
        if cached_result is not None:
            return cached_result

        if mode == "hybrid":
            try:
                from graphify.search import hybrid_search
                results = hybrid_search(question, G, {"limit": limit})
                processes = results.get("processes", [])
                references = results.get("references", [])
                orphaned = results.get("orphaned", [])
                lines = [f"Hybrid search results for '{question}':\n"]
                if processes:
                    lines.append("## Process-Grouped Results")
                    for p in processes[:5]:
                        lines.append(f"  [{p.get('process_type', '')}] {p.get('summary', '')} (priority={p.get('priority_score', 0):.2f})")
                        for sym in p.get("symbols", [])[:5]:
                            lines.append(f"    - {sym.get('name', '?')} [{sym.get('type', '')}] {sym.get('file', '')}")
                if references:
                    lines.append(f"\n## References ({len(references)} results)")
                    for ref in references[:limit]:
                        lines.append(f"  - {ref.get('name', '?')} [{ref.get('type', '')}] {ref.get('file', '')}")
                if orphaned:
                    lines.append(f"\n## Other Results ({len(orphaned)} orphaned)")
                    for o in orphaned[:5]:
                        lines.append(f"  - {o.get('name', '?')} [{o.get('type', '')}]")
                lines.append(f"\nTotal: {results.get('total_results', 0)} results")
                result_str = "\n".join(lines)
                cache.set("query_graph", {
                    "question": question, "mode": mode, "depth": depth, "limit": limit
                }, result_str, file_hashes)
                return result_str
            except ImportError:
                mode = "bfs"

        terms = [t.lower() for t in question.split() if len(t) > 2]
        scored = _score_nodes(G, terms)
        start_nodes = [nid for _, nid in scored[:3]]
        if not start_nodes:
            return "No matching nodes found."
        nodes, edges = _dfs(G, start_nodes, depth) if mode == "dfs" else _bfs(G, start_nodes, depth)
        header = f"Traversal: {mode.upper()} depth={depth} | Start: {[G.nodes[n].get('label', n) for n in start_nodes]} | {len(nodes)} nodes found\n\n"
        result_str = header + _subgraph_to_text(G, nodes, edges, budget)
        cache.set("query_graph", {
            "question": question, "mode": mode, "depth": depth, "limit": limit
        }, result_str, file_hashes)
        return result_str

    def _tool_get_node(arguments: dict) -> str:
        label = arguments["label"].lower()
        matches = [(nid, d) for nid, d in G.nodes(data=True)
                   if label in (d.get("label") or "").lower() or label == nid.lower()]
        if not matches:
            return f"No node matching '{label}' found."
        nid, d = matches[0]
        return "\n".join([
            f"Node: {d.get('label', nid)}",
            f"  ID: {nid}",
            f"  Source: {d.get('source_file', '')} {d.get('source_location', '')}",
            f"  Type: {d.get('file_type', '')}",
            f"  Community: {d.get('community', '')}",
            f"  Degree: {G.degree(nid)}",
        ])

    def _tool_get_neighbors(arguments: dict) -> str:
        label = arguments["label"].lower()
        rel_filter = arguments.get("relation_filter", "").lower()
        matches = _find_node(G, label)
        if not matches:
            return f"No node matching '{label}' found."
        nid = matches[0]
        lines = [f"Neighbors of {G.nodes[nid].get('label', nid)}:"]
        for neighbor in G.neighbors(nid):
            d = G.edges[nid, neighbor]
            rel = d.get("relation", "")
            if rel_filter and rel_filter not in rel.lower():
                continue
            lines.append(f"  --> {G.nodes[neighbor].get('label', neighbor)} [{rel}] [{d.get('confidence', '')}]")
        return "\n".join(lines)

    def _tool_get_community(arguments: dict) -> str:
        cid = int(arguments["community_id"])
        nodes = communities.get(cid, [])
        if not nodes:
            return f"Community {cid} not found."
        lines = [f"Community {cid} ({len(nodes)} nodes):"]
        for n in nodes:
            d = G.nodes[n]
            lines.append(f"  {d.get('label', n)} [{d.get('source_file', '')}]")
        return "\n".join(lines)

    def _tool_god_nodes(arguments: dict) -> str:
        from .analyze import god_nodes as _god_nodes
        nodes = _god_nodes(G, top_n=int(arguments.get("top_n", 10)))
        lines = ["God nodes (most connected):"]
        lines += [f"  {i}. {n['label']} - {n['degree']} edges" for i, n in enumerate(nodes, 1)]
        return "\n".join(lines)

    def _tool_graph_stats(_: dict) -> str:
        confs = [d.get("confidence", "EXTRACTED") for _, _, d in G.edges(data=True)]
        total = len(confs) or 1
        return (
            f"Nodes: {G.number_of_nodes()}\n"
            f"Edges: {G.number_of_edges()}\n"
            f"Communities: {len(communities)}\n"
            f"EXTRACTED: {round(confs.count('EXTRACTED')/total*100)}%\n"
            f"INFERRED: {round(confs.count('INFERRED')/total*100)}%\n"
            f"AMBIGUOUS: {round(confs.count('AMBIGUOUS')/total*100)}%\n"
        )

    def _tool_shortest_path(arguments: dict) -> str:
        src_scored = _score_nodes(G, [t.lower() for t in arguments["source"].split()])
        tgt_scored = _score_nodes(G, [t.lower() for t in arguments["target"].split()])
        if not src_scored:
            return f"No node matching source '{arguments['source']}' found."
        if not tgt_scored:
            return f"No node matching target '{arguments['target']}' found."

        src_nid = _select_best_start_node(G, [nid for _, nid in src_scored[:5]])
        tgt_nid = _select_best_start_node(G, [nid for _, nid in tgt_scored[:5]])

        max_hops = int(arguments.get("max_hops", 8))
        algorithm = arguments.get("algorithm", "bidirectional")
        edge_types = arguments.get("edge_types")

        if algorithm == "dijkstra":
            path, cost = _weighted_dijkstra(G, src_nid, tgt_nid)
            hops = len(path) - 1 if path else -1
            if hops < 0:
                return f"No path found between '{G.nodes[src_nid].get('label', src_nid)}' and '{G.nodes[tgt_nid].get('label', tgt_nid)}'."
            if hops > max_hops:
                return f"Path exceeds max_hops={max_hops} ({hops} hops, cost={cost:.2f})."
        elif algorithm == "astar":
            path, hops = _astar(G, src_nid, tgt_nid, max_hops)
            if hops < 0:
                return f"No path found between '{G.nodes[src_nid].get('label', src_nid)}' and '{G.nodes[tgt_nid].get('label', tgt_nid)}'."
            if hops > max_hops:
                return f"Path exceeds max_hops={max_hops} ({hops} hops)."
        else:
            path, hops = _bidirectional_shortest_path(G, src_nid, tgt_nid, max_hops, edge_types)
            if hops < 0:
                return f"No path found between '{G.nodes[src_nid].get('label', src_nid)}' and '{G.nodes[tgt_nid].get('label', tgt_nid)}'."
            if hops > max_hops:
                return f"Path exceeds max_hops={max_hops} ({hops} hops)."

        segments = []
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            edata = G.edges[u, v]
            rel = edata.get("relation", "")
            conf = edata.get("confidence", "")
            conf_str = f" [{conf}]" if conf else ""
            if i == 0:
                segments.append(G.nodes[u].get("label", u))
            segments.append(f"--{rel}{conf_str}--> {G.nodes[v].get('label', v)}")
        algo_label = f" [{algorithm}]" if algorithm != "bidirectional" else ""
        return f"Shortest path ({hops} hops{algo_label}):\n  " + " ".join(segments)

    def _tool_context(arguments: dict) -> str:
        name = arguments["name"].lower()
        matches = [(nid, d) for nid, d in G.nodes(data=True)
                    if name in (d.get("label") or "").lower() or name == nid.lower()]
        if not matches:
            return f"No symbol matching '{arguments['name']}' found."
        nid, d = matches[0]
        lines = [
            f"Symbol: {d.get('label', nid)}",
            f"  Kind: {d.get('file_type', 'code')}",
            f"  File: {d.get('source_file', '')} {d.get('source_location', '')}",
            f"  Language: {d.get('language', '')}",
        ]
        incoming = []
        outgoing = []
        imports_list = []
        for neighbor in G.neighbors(nid):
            edge_data = G.get_edge_data(nid, neighbor) or G.get_edge_data(neighbor, nid)
            if not edge_data or not isinstance(edge_data, dict):
                continue
            rel = edge_data.get("relation", "")
            conf = edge_data.get("confidence", "")
            src = edge_data.get("source", "")
            if rel in ("calls", "CALLS"):
                if nid == edge_data.get("target", ""):
                    incoming.append((G.nodes[neighbor].get("label", neighbor),
                                   edge_data.get("source_file", ""),
                                   edge_data.get("source_location", ""),
                                   conf))
                else:
                    outgoing.append((G.nodes[neighbor].get("label", neighbor),
                                   edge_data.get("source_file", ""),
                                   edge_data.get("source_location", ""),
                                   conf))
            elif rel in ("imports", "imports_from"):
                imports_list.append((G.nodes[neighbor].get("label", neighbor), rel))
        if incoming:
            lines.append(f"\n  Incoming calls ({len(incoming)}):")
            for label, f, loc, conf in incoming[:10]:
                lines.append(f"    {label} [{conf}] {f}:{loc}")
        if outgoing:
            lines.append(f"\n  Outgoing calls ({len(outgoing)}):")
            for label, f, loc, conf in outgoing[:10]:
                lines.append(f"    {label} [{conf}] {f}:{loc}")
        if imports_list:
            lines.append(f"\n  Imports ({len(imports_list)}):")
            for label, rel in imports_list[:5]:
                lines.append(f"    {label} [{rel}]")
        processes = []
        for neighbor in G.neighbors(nid):
            edge_data = G.get_edge_data(nid, neighbor) or G.get_edge_data(neighbor, nid)
            if edge_data and isinstance(edge_data, dict) and edge_data.get("relation") == "step_in_process":
                pn = edge_data.get("process_name", "")
                si = edge_data.get("step_index", 0)
                if pn:
                    processes.append((pn, si))
        if processes:
            lines.append(f"\n  Process membership ({len(processes)}):")
            for pn, si in processes[:5]:
                lines.append(f"    {pn} (step {si})")
        return "\n".join(lines)

    def _tool_impact(arguments: dict) -> str:
        target = arguments["target"].lower()
        direction = arguments.get("direction", "both")
        min_conf = float(arguments.get("min_confidence", 0.5))
        max_depth = int(arguments.get("max_depth", 5))
        matches = _find_node(G, target)
        if not matches:
            return f"No node matching '{arguments['target']}' found."
        nid = matches[0]
        label = G.nodes[nid].get("label", nid)
        kind = G.nodes[nid].get("file_type", "code")
        src_file = G.nodes[nid].get("source_file", "")

        upstream = {}
        downstream = {}
        total_affected = 0

        if direction in ("upstream", "both"):
            visited = {nid}
            frontier = {nid}
            for d in range(1, max_depth + 1):
                next_f = set()
                level_nodes = []
                for node in frontier:
                    for neighbor in G.neighbors(node):
                        edge_data = G.get_edge_data(neighbor, node)
                        if not edge_data or not isinstance(edge_data, dict):
                            continue
                        rel = edge_data.get("relation", "")
                        conf_score = edge_data.get("confidence_score", 0)
                        if rel in ("calls", "CALLS", "depends_on") and conf_score >= min_conf:
                            if neighbor not in visited:
                                visited.add(neighbor)
                                next_f.add(neighbor)
                                nd = G.nodes[neighbor]
                                level_nodes.append({
                                    "name": nd.get("label", neighbor),
                                    "file": nd.get("source_file", ""),
                                    "confidence": edge_data.get("confidence", ""),
                                })
                if level_nodes:
                    upstream[d] = level_nodes
                frontier = next_f
            total_affected += len(visited) - 1

        if direction in ("downstream", "both"):
            visited = {nid}
            frontier = {nid}
            for d in range(1, max_depth + 1):
                next_f = set()
                level_nodes = []
                for node in frontier:
                    for neighbor in G.neighbors(node):
                        edge_data = G.get_edge_data(node, neighbor)
                        if not edge_data or not isinstance(edge_data, dict):
                            continue
                        rel = edge_data.get("relation", "")
                        conf_score = edge_data.get("confidence_score", 0)
                        if rel in ("calls", "CALLS", "depends_on") and conf_score >= min_conf:
                            if neighbor not in visited:
                                visited.add(neighbor)
                                next_f.add(neighbor)
                                nd = G.nodes[neighbor]
                                level_nodes.append({
                                    "name": nd.get("label", neighbor),
                                    "file": nd.get("source_file", ""),
                                    "confidence": edge_data.get("confidence", ""),
                                })
                if level_nodes:
                    downstream[d] = level_nodes
                frontier = next_f
            total_affected += len(visited) - 1

        if total_affected > 50 and max_depth > 3:
            risk = "CRITICAL"
        elif total_affected > 10:
            risk = "HIGH"
        elif total_affected > 5:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        lines = [
            f"Impact analysis for: {label}",
            f"  Kind: {kind}",
            f"  File: {src_file}",
            f"  Total affected: {total_affected}",
            f"  Risk level: {risk}",
        ]
        if upstream:
            lines.append(f"\n  Upstream (who depends on this):")
            for depth, nodes in sorted(upstream.items()):
                lines.append(f"    Depth {depth}:")
                for n in nodes[:5]:
                    lines.append(f"      - {n['name']} [{n.get('confidence', '')}] {n['file']}")
        if downstream:
            lines.append(f"\n  Downstream (this depends on):")
            for depth, nodes in sorted(downstream.items()):
                lines.append(f"    Depth {depth}:")
                for n in nodes[:5]:
                    lines.append(f"      - {n['name']} [{n.get('confidence', '')}] {n['file']}")
        return "\n".join(lines)

    def _tool_trace(arguments: dict) -> str:
        entry = arguments["entry_point"]
        max_depth = int(arguments.get("max_depth", 20))
        try:
            from graphify.entry_points import EntryPoint, detect_entry_points
            from graphify.processes import trace_process
            extractions = []  # we don't have extractsions in serve context
            ep = None
            for nid, ndata in G.nodes(data=True):
                if entry.lower() in (ndata.get("label", "")).lower():
                    sl = ndata.get("source_location", "0")
                    try:
                        line = int(next(c for c in sl if c.isdigit()) + "0" if any(c.isdigit() for c in sl) else 0)
                    except Exception:
                        line = 0
                    ep = EntryPoint(
                        name=ndata.get("label", nid),
                        kind="EVENT",
                        file=ndata.get("source_file", ""),
                        line=line,
                        language=ndata.get("language", ""),
                    )
                    break
            if not ep:
                return f"No entry point matching '{entry}' found."
            proc = trace_process(ep, G, max_depth=max_depth)
            lines = [
                f"Process: {proc.name}",
                f"  Entry point: {proc.entry_point.file}:{proc.entry_point.line}",
                f"  Total steps: {proc.total_steps}",
                f"  Max depth: {proc.max_depth}",
                f"  Confidence: {proc.confidence:.2f}",
                f"  Complexity: {proc.cyclomatic_complexity}",
                f"  External touches: {proc.external_touches}",
                f"\n  Steps:",
            ]
            for i, step in enumerate(proc.steps[:30]):
                lines.append(f"    [{i}] depth={step.depth} {step.label} {step.file}:{step.line}")
            if proc.total_steps > 30:
                lines.append(f"    ... (+{proc.total_steps - 30} more steps)")
            return "\n".join(lines)
        except ImportError:
            return "Process tracing not available."

    def _tool_detect_changes(arguments: dict) -> str:
        scope = arguments.get("scope", "all")
        try:
            from graphify.change_detect import detect_changes as dc
            report = dc(G, scope=scope)
            return (
                f"Change Detection Report\n"
                f"  Risk: {report.risk_level}\n"
                f"  Changed symbols: {len(report.changed_symbols)}\n"
                f"  Affected processes: {len(report.affected_processes)}\n\n"
                f"  {chr(10).join(report.recommendations[:10])}"
            )
        except ImportError:
            return "Change detection not available."

    def _tool_cache_stats(_: dict) -> str:
        cache = get_cache()
        stats = cache.hit_rate
        return (
            f"Query Cache Stats\n"
            f"  Cached entries: {stats['cached_entries']}\n"
            f"  Tracked files: {stats['tracked_files']}"
        )

    _handlers = {
        "query_graph": _tool_query_graph,
        "get_node": _tool_get_node,
        "get_neighbors": _tool_get_neighbors,
        "get_community": _tool_get_community,
        "god_nodes": _tool_god_nodes,
        "graph_stats": _tool_graph_stats,
        "shortest_path": _tool_shortest_path,
        "context": _tool_context,
        "impact": _tool_impact,
        "trace": _tool_trace,
        "detect_changes": _tool_detect_changes,
        "cache_stats": _tool_cache_stats,
    }

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        handler = _handlers.get(name)
        if not handler:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
        try:
            return [types.TextContent(type="text", text=handler(arguments))]
        except Exception as exc:
            return [types.TextContent(type="text", text=f"Error executing {name}: {exc}")]

    import asyncio

    async def main() -> None:
        async with stdio_server() as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    _filter_blank_stdin()
    asyncio.run(main())


if __name__ == "__main__":
    graph_path = sys.argv[1] if len(sys.argv) > 1 else "graphify-out/graph.json"
    serve(graph_path)
