# Dynamic agent skill generation from graph data
#
# Generates skill templates for AI coding agents that embed:
# - God nodes and community structure for navigation
# - Per-community context with key files and concepts
# - Relationship summaries for understanding dependencies
#
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json
import networkx as nx


@dataclass
class CommunityInfo:
    community_id: int
    label: str
    node_count: int
    file_count: int
    cohesion: float | None
    top_nodes: list[dict[str, Any]] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    key_relationships: list[dict[str, str]] = field(default_factory=list)


@dataclass
class SkillContext:
    repo_name: str
    total_nodes: int
    total_edges: int
    total_communities: int
    god_nodes: list[dict[str, Any]]
    communities: list[CommunityInfo]
    languages: list[str]
    graph_statistics: dict[str, Any] = field(default_factory=dict)


def _collect_god_nodes(G: nx.Graph, top_n: int = 10) -> list[dict[str, Any]]:
    from graphify.analyze import god_nodes as _god_nodes
    return _god_nodes(G, top_n=top_n)


def _collect_communities(G: nx.Graph, min_files: int = 1) -> list[CommunityInfo]:
    from graphify.cluster import cohesion_score

    communities: dict[int, list[str]] = {}
    for nid, data in G.nodes(data=True):
        cid = data.get("community")
        if cid is not None:
            communities.setdefault(int(cid), []).append(nid)

    sorted_cids = sorted(communities.keys(), key=lambda c: len(communities[c]), reverse=True)
    result: list[CommunityInfo] = []
    for i, cid in enumerate(sorted_cids):
        node_ids = communities[cid]
        file_set = _collect_files_for_nodes(G, node_ids)
        if len(file_set) < min_files:
            continue
        sample = _sample_label((G.nodes[n].get("label", n) for n in node_ids), max_len=40)
        top = sorted(node_ids, key=lambda n: G.degree(n), reverse=True)[:10]
        top_nodes = [
            {
                "id": nid,
                "label": G.nodes[nid].get("label", nid),
                "degree": G.degree(nid),
                "file": G.nodes[nid].get("source_file", ""),
                "type": G.nodes[nid].get("file_type", ""),
            }
            for nid in top
        ]
        key_rels = _collect_key_relationships(G, node_ids, top_n=5)
        ch = cohesion_score(G, node_ids)
        result.append(CommunityInfo(
            community_id=i,
            label=sample,
            node_count=len(node_ids),
            file_count=len(file_set),
            cohesion=ch,
            top_nodes=top_nodes,
            source_files=sorted(file_set)[:10],
            key_relationships=key_rels,
        ))
    return result


def _collect_files_for_nodes(G: nx.Graph, node_ids: list[str]) -> set[str]:
    files: set[str] = set()
    for nid in node_ids:
        src = G.nodes[nid].get("source_file", "")
        if src:
            files.add(src)
    return files


def _sample_label(labels: list[str], max_len: int = 40) -> str:
    candidates = [l for l in labels if l]
    if not candidates:
        return "Community"
    best = candidates[0]
    for c in candidates:
        if len(c) <= max_len and len(c) > len(best) and "test" not in c.lower():
            best = c
    if len(best) > max_len:
        best = best[:max_len - 3] + "..."
    return best


def _collect_key_relationships(G: nx.Graph, node_ids: list[str], top_n: int = 5) -> list[dict[str, str]]:
    from collections import Counter

    rel_counts: Counter = Counter()
    rel_examples: dict[str, tuple[str, str]] = {}
    id_set = set(node_ids)
    for nid in node_ids:
        for neighbor in G.neighbors(nid):
            ed = G.edges[nid, neighbor]
            rel = ed.get("relation", "related")
            rel_counts[rel] += 1
            if rel not in rel_examples:
                u_label = G.nodes[nid].get("label", nid)
                v_label = G.nodes[neighbor].get("label", neighbor)
                rel_examples[rel] = (u_label, v_label)
    return [
        {"relation": rel, "count": str(count), "example": f"{ex[0]} -> {ex[1]}"}
        for rel, count in rel_counts.most_common(top_n)
        for ex in [rel_examples.get(rel, ("?", "?"))]
    ]


def _collect_languages(G: nx.Graph) -> list[str]:
    langs: set[str] = set()
    for _, data in G.nodes(data=True):
        lang = data.get("language", "")
        if lang:
            langs.add(lang)
    return sorted(langs)


def render_skill_template(context: SkillContext) -> str:
    lines: list[str] = []
    name = context.repo_name
    if not name:
        name = "project"

    lines.append("---")
    lines.append(f"name: graphify-{name.replace(' ', '-').lower()}")
    lines.append(f"description: >")
    lines.append(f"  Knowledge graph context for {name}: {context.total_nodes} nodes, "
                 f"{context.total_edges} edges, {context.total_communities} communities")
    lines.append("trigger: auto")
    lines.append("---")
    lines.append("")
    lines.append(f"# {name} - Graph Context")
    lines.append("")
    lines.append(f"> **Nodes:** {context.total_nodes} | **Edges:** {context.total_edges} | "
                 f"**Communities:** {context.total_communities}")
    if context.languages:
        lines.append(f"> **Languages:** {', '.join(context.languages)}")
    lines.append("")
    lines.append("## God Nodes (Core Abstractions)")
    lines.append("")
    if context.god_nodes:
        for i, gn in enumerate(context.god_nodes[:15], 1):
            lines.append(f"{i}. **{gn.get('label', '?')}** — "
                         f"{gn.get('degree', 0)} edges")
        lines.append("")
    else:
        lines.append("*No god nodes detected.*")
        lines.append("")

    lines.append("## Community Map")
    lines.append("")
    for ci in context.communities[:20]:
        lines.append(f"### {ci.label} (C{ci.community_id})")
        files_str = ", ".join(Path(f).name for f in ci.source_files[:5])
        lines.append(f"- {ci.node_count} nodes · {ci.file_count} files · cohesion={ci.cohesion or 'N/A':.2f}" if ci.cohesion is not None else f"- {ci.node_count} nodes · {ci.file_count} files")
        if ci.top_nodes:
            lines.append("- Key concepts: " + ", ".join(n["label"] for n in ci.top_nodes[:5]))
        if ci.key_relationships:
            rels = [f"{r['relation']} ({r['count']})" for r in ci.key_relationships[:3]]
            lines.append("- Relationships: " + ", ".join(rels))
        if files_str:
            lines.append(f"- Files: {files_str}")
        lines.append("")
    return "\n".join(lines)


def _build_skill_context(G: nx.Graph, repo_name: str = "") -> SkillContext:
    return SkillContext(
        repo_name=repo_name,
        total_nodes=G.number_of_nodes(),
        total_edges=G.number_of_edges(),
        total_communities=len(_communities_from_graph(G)),
        god_nodes=_collect_god_nodes(G),
        communities=_collect_communities(G, min_files=1),
        languages=_collect_languages(G),
        graph_statistics={
            "nodes": G.number_of_nodes(),
            "edges": G.number_of_edges(),
        },
    )


def _communities_from_graph(G: nx.Graph) -> dict[int, list[str]]:
    comms: dict[int, list[str]] = {}
    for nid, data in G.nodes(data=True):
        cid = data.get("community")
        if cid is not None:
            comms.setdefault(int(cid), []).append(nid)
    return comms


def generate_repo_skill(graph_path: str | Path = "graphify-out/graph.json", repo_name: str = "") -> str:
    from networkx.readwrite import json_graph as _jg

    p = Path(graph_path)
    if not p.exists():
        return f"# No graph found at {graph_path}"

    data = json.loads(p.read_text(encoding="utf-8"))
    try:
        G = _jg.node_link_graph(data, edges="links")
    except TypeError:
        G = _jg.node_link_graph(data)

    if not repo_name:
        repo_name = p.parent.parent.name if p.parent.name == "graphify-out" else "project"

    context = _build_skill_context(G, repo_name)
    return render_skill_template(context)


def generate_community_skill(
    graph_path: str | Path,
    community_id: int,
    repo_name: str = "",
) -> str:
    from networkx.readwrite import json_graph as _jg

    p = Path(graph_path)
    if not p.exists():
        return f"# No graph found at {graph_path}"

    data = json.loads(p.read_text(encoding="utf-8"))
    try:
        G = _jg.node_link_graph(data, edges="links")
    except TypeError:
        G = _jg.node_link_graph(data)

    communities = _collect_communities(G, min_files=3)
    target = None
    for ci in communities:
        if ci.community_id == community_id:
            target = ci
            break

    if target is None:
        return f"# Community {community_id} not found or has fewer than 3 files."

    if not repo_name:
        repo_name = p.parent.parent.name if p.parent.name == "graphify-out" else "project"

    lines: list[str] = []
    lines.append("---")
    lines.append(f"name: graphify-{repo_name.replace(' ', '-').lower()}-c{community_id}")
    lines.append(f"description: Community {community_id} ({target.label}) - {target.node_count} nodes in {target.file_count} files")
    lines.append("trigger: auto")
    lines.append("---")
    lines.append("")
    lines.append(f"# Community {community_id}: {target.label}")
    lines.append("")
    lines.append(f"> **Nodes:** {target.node_count} | **Files:** {target.file_count}")
    if target.cohesion is not None:
        lines.append(f"> **Cohesion:** {target.cohesion:.2f}")
    lines.append("")
    lines.append("## Key Concepts")
    lines.append("")
    for n in target.top_nodes:
        lines.append(f"- **{n['label']}** [{n.get('type', '')}] — {n.get('file', '')}")
    lines.append("")
    lines.append("## Files")
    lines.append("")
    for f in target.source_files:
        lines.append(f"- `{f}`")
    lines.append("")
    lines.append("## Relationships")
    lines.append("")
    for r in target.key_relationships:
        lines.append(f"- **{r['relation']}** ({r['count']} edges) e.g. `{r.get('example', '')}`")
    return "\n".join(lines)


def generate_all_community_skills(
    graph_path: str | Path = "graphify-out/graph.json",
    output_dir: str | Path = "graphify-out/skills/",
    repo_name: str = "",
    *,
    min_files: int = 3,
) -> list[Path]:
    from networkx.readwrite import json_graph as _jg

    p = Path(graph_path)
    if not p.exists():
        return []

    data = json.loads(p.read_text(encoding="utf-8"))
    try:
        G = _jg.node_link_graph(data, edges="links")
    except TypeError:
        G = _jg.node_link_graph(data)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    communities = _collect_communities(G, min_files=min_files)
    saved: list[Path] = []

    for ci in communities:
        content = generate_community_skill(graph_path, ci.community_id, repo_name)
        fname = f"skill-community-{ci.community_id}.md"
        fpath = out / fname
        try:
            fpath.write_text(content, encoding="utf-8")
            saved.append(fpath)
        except OSError:
            pass

    return saved
