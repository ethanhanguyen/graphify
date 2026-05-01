from __future__ import annotations

from pathlib import Path


def build_file_dependency_graph(import_map: dict[str, dict[str, str]]) -> dict[str, set[str]]:
    dep_graph: dict[str, set[str]] = {}
    for file_key, imports in import_map.items():
        dep_graph.setdefault(file_key, set())
        for _, resolved_path in imports.items():
            if resolved_path and resolved_path in import_map:
                dep_graph[file_key].add(resolved_path)
    return dep_graph


def compute_scc_order(dependency_graph: dict[str, set[str]]) -> list[set[str]]:
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    sccs: list[set[str]] = []

    nodes = list(dependency_graph.keys())

    def strongconnect(v: str) -> None:
        nonlocal index
        indices[v] = index
        lowlink[v] = index
        index += 1
        stack.append(v)
        on_stack.add(v)

        for w in dependency_graph.get(v, set()):
            if w not in indices:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], indices[w])

        if lowlink[v] == indices[v]:
            scc: set[str] = set()
            while True:
                w = stack.pop()
                on_stack.discard(w)
                scc.add(w)
                if w == v:
                    break
            sccs.append(scc)

    for node in nodes:
        if node not in indices:
            strongconnect(node)

    return sccs


def propagate_types(
    scc_order: list[set[str]], symbols: dict[str, dict]
) -> dict[str, dict]:
    resolved: dict[str, dict] = dict(symbols)

    for scc in scc_order:
        local_additions: dict[str, dict] = {}
        for file_key in scc:
            file_symbols = resolved.get(file_key, {})
            for other_file in scc:
                if other_file == file_key:
                    continue
                other_symbols = resolved.get(other_file, {})
                for sym_name, sym_info in other_symbols.items():
                    if sym_name not in file_symbols:
                        file_symbols[sym_name] = sym_info
            local_additions[file_key] = file_symbols
        resolved.update(local_additions)

    return resolved
