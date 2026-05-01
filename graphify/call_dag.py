from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from graphify.code_schema import ConfidenceTier, EdgeType
from graphify.call_extractors import extract_calls, ExtractedCallSite
from graphify.receiver import infer_receiver
from graphify.mro import build_class_hierarchy, get_mro_strategy
from graphify.imports import resolve_all_imports
from graphify.cross_file import build_file_dependency_graph, compute_scc_order


@dataclass
class CallEdge:
    source: str
    target: str
    confidence: ConfidenceTier = ConfidenceTier.EXTRACTED
    confidence_score: float = 1.0
    source_file: str = ""
    source_location: str = ""


class CallResolutionDAG:
    def __init__(self, files: list[Path], extractions: list[dict], language: str):
        self.files = files
        self.extractions = extractions
        self.language = language
        self.call_sites: list[ExtractedCallSite] = []
        self.classified: dict[str, list[ExtractedCallSite]] = {}
        self.edges: list[CallEdge] = []
        self.stats: dict[str, int] = {
            "extract": 0,
            "classify": 0,
            "classify_direct": 0,
            "classify_method": 0,
            "classify_constructor": 0,
            "classify_import_dispatch": 0,
            "classify_anonymous": 0,
            "infer_receiver": 0,
            "select_dispatch": 0,
            "resolve_target": 0,
            "emit_edge": 0,
        }

    def stage_extract(self) -> None:
        for i, (file_path, extraction_result) in enumerate(zip(self.files, self.extractions)):
            if "error" in extraction_result:
                continue
            calls = extract_calls(file_path, self.language, extraction_result)
            self.call_sites.extend(calls)
            self.stats["extract"] += len(calls)

    def stage_classify(self) -> None:
        for call_site in self.call_sites:
            category = self._classify_call_site(call_site)
            self.classified.setdefault(category, []).append(call_site)
            self.stats["classify"] += 1
            self.stats[f"classify_{category}"] = self.stats.get(f"classify_{category}", 0) + 1

    def _classify_call_site(self, cs: ExtractedCallSite) -> str:
        if cs.is_constructor:
            return "constructor"
        if cs.callee_receiver:
            if cs.callee_receiver in ("self", "this"):
                return "direct"
            return "method"
        callee = cs.callee_name
        if not callee:
            return "anonymous"
        if "." in callee:
            return "method"
        return "direct"

    def stage_infer_receiver(self) -> None:
        class_map: dict[str, str] = {}
        for result in self.extractions:
            for node in result.get("nodes", []):
                node_id = node.get("id", "")
                nid = node_id.lower()
                class_map.setdefault(nid, node_id)

        for category, sites in self.classified.items():
            for cs in sites:
                receiver = infer_receiver(cs, cs.caller_nid, class_map)
                if receiver:
                    cs.callee_receiver = receiver
                    self.stats["infer_receiver"] += 1

    def stage_select_dispatch(self) -> None:
        self._mro_strategy = get_mro_strategy(self.language)
        self._class_hierarchy = build_class_hierarchy(self.extractions)
        self.stats["select_dispatch"] = 1

    def stage_resolve_target(self) -> None:
        all_files_map: dict[str, list[str]] = {}
        for f in self.files:
            stem = Path(f).stem
            all_files_map.setdefault(stem, []).append(str(f))
            all_files_map.setdefault(f.stem.lower(), []).append(str(f))

        suffix_index: dict[str, list[str]] = {}
        stem_index: dict[str, list[str]] = {}
        namespace_index: dict[str, list[str]] = {}
        for f in self.files:
            fs = str(f)
            suffix_index.setdefault(f"/{fs}", []).append(fs)
            suffix_index.setdefault(f"/{f.name}", []).append(fs)
            stem_index.setdefault(f.stem, []).append(fs)
            f_norm = fs.replace("\\", "/")
            namespace_index.setdefault(f_norm, []).append(fs)

        file_to_extraction = {str(f): r for f, r in zip(self.files, self.extractions)}

        import_map: dict[str, dict[str, str]] = {}
        for file_path, result in file_to_extraction.items():
            imports = [
                e for e in result.get("edges", [])
                if e.get("relation") in ("imports", "imports_from")
            ]
            resolved = resolve_all_imports(
                Path(file_path), imports, all_files_map, self.language,
                suffix_index, stem_index, namespace_index,
            )
            import_map[file_path] = resolved

        dep_graph = build_file_dependency_graph(import_map)
        self._scc_order = compute_scc_order(dep_graph)

        label_index: dict[str, dict[str, str]] = {}
        inverted_label_index: dict[str, list[tuple[str, str]]] = {}
        for fp, result in file_to_extraction.items():
            # Use absolute path keys so same-file (L171) and import
            # resolution (L193) lookups actually match caller_file values.
            for node in result.get("nodes", []):
                label_index.setdefault(fp, {})
                label = node.get("label", "").strip("()").lstrip(".").lower()
                if label:
                    label_index[fp][label] = node["id"]
                    inverted_label_index.setdefault(label, []).append((fp, node["id"]))

        for cs in self.call_sites:
            callee = cs.callee_name.lower()
            resolved_nid = self._resolve_callee_nid(cs, callee, label_index, import_map, inverted_label_index)
            if resolved_nid:
                self.edges.append(CallEdge(
                    source=cs.caller_nid,
                    target=resolved_nid,
                    confidence=ConfidenceTier.INFERRED,
                    confidence_score=0.8,
                    source_file=cs.caller_file,
                    source_location=cs.source_location,
                ))
                self.stats["resolve_target"] += 1

    def _resolve_callee_nid(
        self,
        cs: ExtractedCallSite,
        callee: str,
        label_index: dict[str, dict[str, str]],
        import_map: dict[str, dict[str, str]],
        inverted_label_index: dict[str, list[tuple[str, str]]] | None = None,
    ) -> str | None:
        caller_file = cs.caller_file

        if caller_file in label_index:
            file_labels = label_index[caller_file]
            if callee in file_labels:
                nid = file_labels[callee]
                if nid != cs.caller_nid:
                    return nid

        if cs.callee_receiver:
            receiver_lower = cs.callee_receiver.lower()
            if caller_file in label_index:
                file_labels = label_index[caller_file]
                for label, nid in file_labels.items():
                    if label.startswith(f"{receiver_lower}.") and label.endswith(f".{callee}"):
                        return nid

            if self._mro_strategy and self._class_hierarchy:
                result = self._mro_strategy.resolve(
                    callee, cs.callee_receiver, self._class_hierarchy
                )
                if result:
                    return result[0]

        imports = import_map.get(caller_file, {})
        if imports:
            for import_name, resolved_path in imports.items():
                if resolved_path in label_index:
                    file_labels = label_index[resolved_path]
                    if callee in file_labels:
                        return file_labels[callee]
                    import_base = import_name.rsplit(".", 1)[-1].lower() if "." in import_name else import_name.lower()
                    if callee == import_base:
                        continue

        if inverted_label_index:
            entries = inverted_label_index.get(callee, [])
            caller_dir = Path(caller_file).parent
            for file_key, nid in entries:
                if file_key == caller_file or nid == cs.caller_nid:
                    continue
                if Path(file_key).parent == caller_dir:
                    return nid

        return None

    def stage_emit_edge(self) -> list[dict]:
        edge_dicts: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for e in self.edges:
            key = (e.source, e.target)
            if key in seen:
                continue
            seen.add(key)
            edge_dicts.append({
                "source": e.source,
                "target": e.target,
                "relation": EdgeType.CALLS.value,
                "confidence": e.confidence.value,
                "confidence_score": e.confidence_score,
                "source_file": e.source_file,
                "source_location": e.source_location,
                "weight": 1.0,
            })
        self.stats["emit_edge"] = len(edge_dicts)
        return edge_dicts

    def run(self) -> tuple[list[dict], dict]:
        t0 = _time.time()
        self.stage_extract()
        t0 = self._log_phase("call_dag.extract", t0)
        self.stage_classify()
        t0 = self._log_phase("call_dag.classify", t0)
        self.stage_infer_receiver()
        t0 = self._log_phase("call_dag.infer_receiver", t0)
        self.stage_select_dispatch()
        t0 = self._log_phase("call_dag.select_dispatch", t0)
        self.stage_resolve_target()
        self._log_phase("call_dag.resolve_target", t0)
        edges = self.stage_emit_edge()
        return edges, self.stats

    def _log_phase(self, name: str, t0: float) -> float:
        elapsed = _time.time() - t0
        if elapsed > 0.5:
            print(f"[graphify timing]     {name}: {elapsed:.1f}s")
        return _time.time()


def run_call_resolution(
    files: list[Path],
    extractions: list[dict],
    language: str,
) -> tuple[list[dict], dict]:
    dag = CallResolutionDAG(files, extractions, language)
    return dag.run()
