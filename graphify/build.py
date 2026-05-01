# assemble node+edge dicts into a NetworkX graph, preserving edge direction
#
# Node deduplication — three layers:
#
# 1. Within a file (AST): each extractor tracks a `seen_ids` set. A node ID is
#    emitted at most once per file, so duplicate class/function definitions in
#    the same source file are collapsed to the first occurrence.
#
# 2. Between files (build): NetworkX G.add_node() is idempotent — calling it
#    twice with the same ID overwrites the attributes with the second call's
#    values. Nodes are added in extraction order (AST first, then semantic),
#    so if the same entity is extracted by both passes the semantic node
#    silently overwrites the AST node. This is intentional: semantic nodes
#    carry richer labels and cross-file context, while AST nodes have precise
#    source_location. If you need to change the priority, reorder extractions
#    passed to build().
#
# 3. Semantic merge (skill): before calling build(), the skill merges cached
#    and new semantic results using an explicit `seen` set keyed on node["id"],
#    so duplicates across cache hits and new extractions are resolved there
#    before any graph construction happens.
#
from __future__ import annotations
import json
import re
import sys
import time as _time
from pathlib import Path
import networkx as nx
from .validate import validate_extraction


def _normalize_id(s: str) -> str:
    """Normalize an ID string the same way extract._make_id does.

    Used to reconcile edge endpoints when the LLM generates IDs with slightly
    different punctuation or casing than the AST extractor.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", s)
    return cleaned.strip("_").lower()


def build_from_json(extraction: dict, *, directed: bool = False) -> nx.Graph:
    """Build a NetworkX graph from an extraction dict.

    directed=True produces a DiGraph that preserves edge direction (source→target).
    directed=False (default) produces an undirected Graph for backward compatibility.
    """
    # NetworkX <= 3.1 serialised edges as "links"; remap to "edges" for compatibility.
    if "edges" not in extraction and "links" in extraction:
        extraction = dict(extraction, edges=extraction["links"])

    # Canonicalize legacy node/edge schema before validation.
    for node in extraction.get("nodes", []):
        if isinstance(node, dict) and "source" in node and "source_file" not in node:
            # Count edges that reference this node so the warning is actionable (#479)
            node_id = node.get("id", "?")
            affected_edges = sum(
                1 for e in extraction.get("edges", [])
                if e.get("source") == node_id or e.get("target") == node_id
            )
            print(
                f"[graphify] WARNING: node '{node_id}' uses field 'source' instead of "
                f"'source_file' — {affected_edges} edge(s) may be misrouted. "
                f"Rename the field to 'source_file' to silence this warning.",
                file=sys.stderr,
            )
            node["source_file"] = node.pop("source")

    errors = validate_extraction(extraction)
    # Dangling edges (stdlib/external imports) are expected - only warn about real schema errors.
    real_errors = [e for e in errors if "does not match any node id" not in e]
    if real_errors:
        print(f"[graphify] Extraction warning ({len(real_errors)} issues): {real_errors[0]}", file=sys.stderr)
    G: nx.Graph = nx.DiGraph() if directed else nx.Graph()
    for node in extraction.get("nodes", []):
        G.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    node_set = set(G.nodes())
    # Normalized ID map: lets edges survive when the LLM generates IDs with
    # slightly different casing or punctuation than the AST extractor.
    # e.g. "Session_ValidateToken" maps to "session_validatetoken".
    norm_to_id: dict[str, str] = {_normalize_id(nid): nid for nid in node_set}
    for edge in extraction.get("edges", []):
        if "source" not in edge and "from" in edge:
            edge["source"] = edge["from"]
        if "target" not in edge and "to" in edge:
            edge["target"] = edge["to"]
        if "source" not in edge or "target" not in edge:
            continue
        src, tgt = edge["source"], edge["target"]
        # Remap mismatched IDs via normalization before dropping the edge.
        if src not in node_set:
            src = norm_to_id.get(_normalize_id(src), src)
        if tgt not in node_set:
            tgt = norm_to_id.get(_normalize_id(tgt), tgt)
        if src not in node_set or tgt not in node_set:
            continue  # skip edges to external/stdlib nodes - expected, not an error
        attrs = {k: v for k, v in edge.items() if k not in ("source", "target")}
        # Preserve original edge direction - undirected graphs lose it otherwise,
        # causing display functions to show edges backwards.
        attrs["_src"] = src
        attrs["_tgt"] = tgt
        G.add_edge(src, tgt, **attrs)
    hyperedges = extraction.get("hyperedges", [])
    if hyperedges:
        G.graph["hyperedges"] = hyperedges
    G.graph["schema_version"] = 2
    return G


def build(extractions: list[dict], *, directed: bool = False) -> nx.Graph:
    """Merge multiple extraction results into one graph.

    directed=True produces a DiGraph that preserves edge direction (source→target).
    directed=False (default) produces an undirected Graph for backward compatibility.

    Extractions are merged in order. For nodes with the same ID, the last
    extraction's attributes win (NetworkX add_node overwrites). Pass AST
    results before semantic results so semantic labels take precedence, or
    reverse the order if you prefer AST source_location precision to win.
    """
    combined: dict = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
    for ext in extractions:
        combined["nodes"].extend(ext.get("nodes", []))
        combined["edges"].extend(ext.get("edges", []))
        combined["hyperedges"].extend(ext.get("hyperedges", []))
        combined["input_tokens"] += ext.get("input_tokens", 0)
        combined["output_tokens"] += ext.get("output_tokens", 0)
    return build_from_json(combined, directed=directed)


def _norm_label(label: str) -> str:
    """Canonical dedup key — lowercase, alphanumeric only."""
    return re.sub(r"[^a-z0-9 ]", "", label.lower()).strip()


def deduplicate_by_label(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Merge nodes that share a normalised label, rewriting edge references.

    Prefers IDs without chunk suffixes (_c\\d+) and shorter IDs when tied.
    Drops self-loops created by the merge. Called in build() automatically.
    """
    _CHUNK_SUFFIX = re.compile(r"_c\d+$")
    canonical: dict[str, dict] = {}  # norm_label -> surviving node
    remap: dict[str, str] = {}       # old_id -> surviving_id

    for node in nodes:
        key = _norm_label(node.get("label", node.get("id", "")))
        if not key:
            continue
        existing = canonical.get(key)
        if existing is None:
            canonical[key] = node
        else:
            has_suffix = bool(_CHUNK_SUFFIX.search(node["id"]))
            existing_has_suffix = bool(_CHUNK_SUFFIX.search(existing["id"]))
            if has_suffix and not existing_has_suffix:
                remap[node["id"]] = existing["id"]
            elif existing_has_suffix and not has_suffix:
                remap[existing["id"]] = node["id"]
                canonical[key] = node
            elif len(node["id"]) < len(existing["id"]):
                remap[existing["id"]] = node["id"]
                canonical[key] = node
            else:
                remap[node["id"]] = existing["id"]

    if not remap:
        return nodes, edges

    print(f"[graphify] Deduplicated {len(remap)} duplicate node(s) by label.", file=sys.stderr)
    deduped_nodes = list(canonical.values())
    deduped_edges = []
    for edge in edges:
        e = dict(edge)
        e["source"] = remap.get(e["source"], e["source"])
        e["target"] = remap.get(e["target"], e["target"])
        if e["source"] != e["target"]:
            deduped_edges.append(e)
    return deduped_nodes, deduped_edges


def build_merge(
    new_chunks: list[dict],
    graph_path: str | Path = "graphify-out/graph.json",
    prune_sources: list[str] | None = None,
    *,
    directed: bool = False,
) -> nx.Graph:
    """Load existing graph.json, merge new chunks into it, and save back.

    Never replaces — only grows (or prunes deleted-file nodes via prune_sources).
    Safe to call repeatedly: existing nodes and edges are preserved.
    """
    from graphify.serve import _load_graph_file

    graph_path_obj = Path(graph_path)
    if graph_path_obj.exists():
        existing_G = _load_graph_file(graph_path_obj)
        # Reconstruct as a plain extraction dict so build() can merge it
        existing_nodes = [{"id": n, **existing_G.nodes[n]} for n in existing_G.nodes]
        existing_edges = [
            {"source": u, "target": v, **d} for u, v, d in existing_G.edges(data=True)
        ]
        base = [{"nodes": existing_nodes, "edges": existing_edges}]
    else:
        base = []

    all_chunks = base + list(new_chunks)
    G = build(all_chunks, directed=directed)

    # Prune nodes from deleted source files
    if prune_sources:
        to_remove = [
            n for n, d in G.nodes(data=True)
            if d.get("source_file") in prune_sources
        ]
        G.remove_nodes_from(to_remove)
        if to_remove:
            print(f"[graphify] Pruned {len(to_remove)} node(s) from deleted sources.", file=sys.stderr)

    # Safety check: refuse to shrink the graph silently (#479)
    if graph_path_obj.exists():
        existing_n = len(existing_nodes)
        new_n = G.number_of_nodes()
        if new_n < existing_n:
            raise ValueError(
                f"graphify: build_merge would shrink graph from {existing_n} → {new_n} nodes. "
                f"Pass prune_sources explicitly if you intend to remove nodes."
            )

    return G


def enrich_by_language(G: nx.Graph, files: list, extractions: list[dict]) -> nx.Graph:
    language_groups: dict[str, list[tuple]] = {}
    language_map = {
        ".py": "python", ".ts": "typescript", ".tsx": "typescript",
        ".js": "javascript", ".jsx": "javascript", ".go": "go",
        ".java": "java", ".cs": "csharp", ".rs": "rust",
        ".cpp": "cpp", ".c": "c", ".rb": "ruby", ".kt": "kotlin",
        ".scala": "scala", ".php": "php", ".swift": "swift",
    }

    _MAX_FILES_PER_LANG = 10000

    for f, ext in zip(files, extractions):
        p = Path(f) if isinstance(f, str) else f
        lang = language_map.get(p.suffix.lower(), "unknown")
        language_groups.setdefault(lang, []).append((p, ext))

    call_stats = {"resolved": 0, "total": 0}
    process_stats = {"traced": 0, "total_steps": 0, "clustered": 0}

    for lang, group in language_groups.items():
        if lang == "unknown" or len(group) > _MAX_FILES_PER_LANG:
            call_stats.setdefault("skipped", {})[lang] = len(group)
            continue
        try:
            t_lang = _time.time()
            from graphify.call_dag import run_call_resolution
            g_files = [f for f, _ in group]
            g_extractions = [e for _, e in group]
            call_edges, cstats = run_call_resolution(g_files, g_extractions, lang)
            elapsed = _time.time() - t_lang
            if elapsed > 1.0:
                print(f"[graphify timing]   call_dag({lang}, {len(group)} files): {elapsed:.1f}s (resolved={cstats.get('resolve_target', 0)}/{cstats.get('extract', 0)})")
            for edge in call_edges:
                G.add_edge(edge["source"], edge["target"], **{k: v for k, v in edge.items() if k not in ("source", "target")})
            call_stats["resolved"] += cstats.get("resolve_target", 0)
            call_stats["total"] += cstats.get("extract", 0)
        except Exception:
            pass

    G.graph["call_resolution_stats"] = call_stats

    try:
        from graphify.entry_points import detect_entry_points, score_entry_points
        from graphify.processes import trace_all_entry_points
        t_eps = _time.time()
        _MAX_ENTRY_POINTS = 50
        entry_points = detect_entry_points(G, extractions, "")
        scored = score_entry_points(entry_points, G)
        capped = scored[:_MAX_ENTRY_POINTS]
        print(f"[graphify timing]   entry_points (detect+score): {_time.time() - t_eps:.1f}s ({len(scored)} candidates)")
        t_proc = _time.time()
        processes = trace_all_entry_points([ep for ep, _ in capped], G)
        process_stats["traced"] = len(processes)
        process_stats["total_steps"] = sum(p.total_steps for p in processes)
        print(f"[graphify timing]   process_tracing: {_time.time() - t_proc:.1f}s ({len(processes)} processes, {process_stats['total_steps']} steps)")

        for proc in processes:
            for i, step in enumerate(proc.steps):
                if i > 0:
                    prev_id = proc.steps[i - 1].node_id
                    G.add_edge(prev_id, step.node_id,
                               relation="step_in_process",
                               confidence="INFERRED",
                               confidence_score=0.8,
                               process_name=proc.name,
                               step_index=i)
    except Exception:
        pass

    G.graph["process_stats"] = process_stats
    return G
