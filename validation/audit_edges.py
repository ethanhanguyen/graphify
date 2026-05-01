#!/usr/bin/env python3
"""Audit INFERRED edge quality in current graph vs baseline."""
import json, random, collections, sys
from pathlib import Path

RUN_DIR = Path("/Users/hoang/graphify/validation/runs/2026-05-01-143922")

def load_graph(path: Path):
    g = json.loads(path.read_text())
    nodes = {n['id']: n for n in g['nodes']}
    edges = g.get('links', g.get('edges', []))
    return nodes, edges

def main():
    b_nodes, b_edges = load_graph(RUN_DIR / "out-baseline" / "graph.json")
    c_nodes, c_edges = load_graph(RUN_DIR / "out-current" / "graph.json")

    # --- Edge class breakdown ---
    c_conf = collections.Counter(e.get('confidence', '?') for e in c_edges)
    c_rel = collections.Counter(e.get('relation', '?') for e in c_edges)
    b_conf = collections.Counter(e.get('confidence', '?') for e in b_edges)
    b_rel = collections.Counter(e.get('relation', '?') for e in b_edges)

    print("=== EDGE BREAKDOWN ===")
    print(f"{'':20} {'BASELINE':>12} {'CURRENT':>12} {'DELTA':>12}")
    print(f"{'EXTRACTED':20} {b_conf.get('EXTRACTED',0):>12,} {c_conf.get('EXTRACTED',0):>12,} {c_conf.get('EXTRACTED',0)-b_conf.get('EXTRACTED',0):>+12,}")
    print(f"{'INFERRED':20} {b_conf.get('INFERRED',0):>12,} {c_conf.get('INFERRED',0):>12,} {c_conf.get('INFERRED',0)-b_conf.get('INFERRED',0):>+12,}")
    print()

    # --- INFERRED sub-breakdown ---
    print("=== INFERRED EDGES BY RELATION ===")
    b_inf_rel = collections.Counter(e.get('relation','?') for e in b_edges if e.get('confidence')=='INFERRED')
    c_inf_rel = collections.Counter(e.get('relation','?') for e in c_edges if e.get('confidence')=='INFERRED')
    all_rels = sorted(set(list(b_inf_rel.keys()) + list(c_inf_rel.keys())))
    print(f"{'Relation':20} {'Baseline':>12} {'Current':>12} {'Delta':>12}")
    for rel in all_rels:
        print(f"{rel:20} {b_inf_rel.get(rel,0):>12,} {c_inf_rel.get(rel,0):>12,} {c_inf_rel.get(rel,0)-b_inf_rel.get(rel,0):>+12,}")

    # --- God node shift ---
    print("\n=== GOD NODE DRIFT ===")
    # Top 30 by degree in each, show overlap
    def get_top_labels(nodes, edges, n=30):
        deg = collections.Counter()
        for e in edges:
            deg[e['source']] += 1
            deg[e['target']] += 1
        result = []
        for nid, d in deg.most_common(n):
            label = nodes.get(nid, {}).get('label', nid) if nid in nodes else nid
            result.append((label, d))
        return result

    b_top = get_top_labels(b_nodes, b_edges, 30)
    c_top = get_top_labels(c_nodes, c_edges, 30)

    b_labels = set(l for l, _ in b_top)
    c_labels = set(l for l, _ in c_top)
    overlap = b_labels & c_labels
    added = c_labels - b_labels
    removed = b_labels - c_labels

    print(f"Overlap in top 30: {len(overlap)}/30")
    print(f"Added (in current, not baseline): {len(added)}")
    for l,d in c_top:
        if l in added:
            print(f"  NEW: {l} ({d} edges)")
    print(f"Removed (in baseline, not current): {len(removed)}")
    for l,d in b_top:
        if l in removed:
            print(f"  GONE: {l} ({d} edges)")

    # --- Source-of-origin analysis for INFERRED edges ---
    print("\n=== INFERRED EDGE SOURCE ANALYSIS ===")
    c_inferred = [e for e in c_edges if e.get('confidence') == 'INFERRED']
    src_files = collections.Counter()
    tgt_files = collections.Counter()
    for e in c_inferred:
        src = e['source']
        tgt = e['target']
        src_node = c_nodes.get(src, {})
        tgt_node = c_nodes.get(tgt, {})
        src_files[src_node.get('label','?').split('.')[0]] += 1
    # Show most frequent edge callers
    print("Top 20 callers (source nodes of INFERRED edges):")
    caller_deg = collections.Counter()
    for e in c_inferred:
        caller_deg[e['source']] += 1
    for nid, d in caller_deg.most_common(20):
        label = c_nodes.get(nid, {}).get('label', nid) if nid in c_nodes else nid
        print(f"  {label[:80]:80} {d:>6} outgoing INFERRED")

    # --- Check: are INFERRED edges connecting same-file or cross-file? ---
    print("\n=== CROSS-FILE vs SAME-FILE INFERRED EDGES ===")
    # Load file-to-node mapping from build logs is impractical; approximate via label patterns
    method_call_pattern = collections.Counter()
    for e in c_inferred:
        src_label = c_nodes.get(e['source'], {}).get('label', '')
        tgt_label = c_nodes.get(e['target'], {}).get('label', '')
        # Count generic method names
        if src_label.startswith('.') and not src_label.startswith('..'):
            method_call_pattern[f"method→{tgt_label[:30]}"] += 1

    print("Most common method→target patterns (top 15):")
    for pat, cnt in method_call_pattern.most_common(15):
        print(f"  {pat:60} {cnt:>6}")


if __name__ == '__main__':
    main()
