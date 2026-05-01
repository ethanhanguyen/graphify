from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import networkx as nx
    from graphify.code_schema import TypedNode, TypedEdge

_DETECTOR_REGISTRY: dict[str, FrameworkEntryPointDetector] = {}


@dataclass
class EntryPoint:
    name: str
    kind: str
    file: str
    line: int
    language: str
    framework: str = ""


class EntryPointDetector:
    def detect(self, graph: nx.Graph, extractions: list) -> list[EntryPoint]:
        return []


class FrameworkEntryPointDetector(EntryPointDetector):
    _NEXTJS_ROUTE = re.compile(r"(page|route|layout|loading|error|not-found|template|default)\.(tsx?|jsx?|mjs)$")
    _NEXTJS_ROUTE_DIR = re.compile(r"(api|app)/")
    _EXPRESS_VERB = re.compile(r"\b(app|router)\.(get|post|put|delete|patch|use|all|head|options)\s*\(")
    _FLASK_ROUTE = re.compile(r"@\w*\.(route|get|post|put|delete|patch)\s*\(")
    _FLASK_APP_ROUTE = re.compile(r"@app\.(route|before_request|after_request|errorhandler)\s*\(")
    _FASTAPI_ROUTE = re.compile(r"@(app|router)\.(get|post|put|delete|patch|head|options|websocket)\s*\(")
    _CLI_MAIN = re.compile(r"^(def\s+main\b|func\s+main\b)", re.MULTILINE)
    _CLI_MAIN_GUARD = re.compile(r"if\s+__name__\s*==\s*['\"]__main__['\"]")
    _GO_MAIN = re.compile(r"\bfunc\s+main\s*\(")
    _GO_INIT = re.compile(r"\bfunc\s+init\s*\(")
    _TEST_DEF = re.compile(r"\bdef\s+test_\w+")
    _TEST_JEST = re.compile(r"\b(it|describe|test)\s*\(")
    _TEST_PYTEST = re.compile(r"\btest_\w+\s*=")
    _TEST_GO = re.compile(r"\bfunc\s+Test\w+\s*\(")
    _TEST_JUNIT = re.compile(r"@Test\b")
    _CRON_DECORATOR = re.compile(r"@app\.(cron|schedule|task)")
    _CRON_NODE = re.compile(r"\bnode-cron\b|cron\.schedule\s*\(")

    def detect(self, graph: nx.Graph, extractions: list) -> list[EntryPoint]:
        results: list[EntryPoint] = []
        for node in extractions:
            if not isinstance(node, dict):
                continue
            label = node.get("label", "")
            src_file = node.get("source_file", "")
            src_loc = node.get("source_location", "")
            node_type = node.get("tree_sitter_type", "") or node.get("node_type", "")
            language = node.get("language", "")

            line = 0
            if src_loc:
                m = re.search(r"(\d+)", str(src_loc))
                if m:
                    line = int(m.group(1))

            eps = self._detect_from_node(label, src_file, node_type, language, line)
            results.extend(eps)
        return list({(ep.name, ep.file, ep.line): ep for ep in results}.values())

    def _detect_from_node(self, label: str, src_file: str, node_type: str, language: str, line: int) -> list[EntryPoint]:
        results: list[EntryPoint] = []

        if self._is_nextjs_route(src_file, node_type):
            kind = "API" if "api/" in src_file.replace("\\", "/") or "route." in src_file.split("/")[-1] else "PAGE"
            results.append(EntryPoint(
                name=src_file.split("/")[-1].split(".")[0],
                kind=kind, file=src_file, line=line,
                language="typescript", framework="nextjs"
            ))

        if self._is_express_route(label, node_type):
            results.append(EntryPoint(
                name=label, kind="HTTP", file=src_file, line=line,
                language="javascript", framework="express"
            ))

        if self._is_flask_route(label, node_type):
            results.append(EntryPoint(
                name=label, kind="HTTP", file=src_file, line=line,
                language="python", framework="flask"
            ))

        if self._is_fastapi_route(label, node_type):
            results.append(EntryPoint(
                name=label, kind="HTTP", file=src_file, line=line,
                language="python", framework="fastapi"
            ))

        if self._is_cli_main(label, node_type, src_file):
            results.append(EntryPoint(
                name=label, kind="CLI", file=src_file, line=line,
                language=language, framework=""
            ))

        if self._is_go_main(label, node_type):
            results.append(EntryPoint(
                name="main", kind="CLI", file=src_file, line=line,
                language="go", framework=""
            ))

        if self._is_go_init(label, node_type):
            results.append(EntryPoint(
                name="init", kind="EVENT", file=src_file, line=line,
                language="go", framework=""
            ))

        if self._is_test(label, node_type):
            results.append(EntryPoint(
                name=label, kind="TEST", file=src_file, line=line,
                language=language, framework=""
            ))

        if self._is_cron(label, node_type):
            results.append(EntryPoint(
                name=label, kind="CRON", file=src_file, line=line,
                language=language, framework=""
            ))

        return results

    def _is_nextjs_route(self, src_file: str, node_type: str) -> bool:
        base = src_file.split("/")[-1] if src_file else ""
        return bool(self._NEXTJS_ROUTE.search(base))

    def _is_express_route(self, label: str, node_type: str) -> bool:
        return bool(self._EXPRESS_VERB.search(label))

    def _is_flask_route(self, label: str, node_type: str) -> bool:
        return bool(self._FLASK_ROUTE.search(label)) or bool(self._FLASK_APP_ROUTE.search(label))

    def _is_fastapi_route(self, label: str, node_type: str) -> bool:
        return bool(self._FASTAPI_ROUTE.search(label))

    def _is_cli_main(self, label: str, node_type: str, src_file: str) -> bool:
        if self._CLI_MAIN_GUARD.search(label):
            return True
        if self._CLI_MAIN.search(label):
            return True
        return False

    def _is_go_main(self, label: str, node_type: str) -> bool:
        return bool(self._GO_MAIN.search(label))

    def _is_go_init(self, label: str, node_type: str) -> bool:
        return bool(self._GO_INIT.search(label))

    def _is_test(self, label: str, node_type: str) -> bool:
        return (bool(self._TEST_DEF.search(label))
                or bool(self._TEST_JEST.search(label))
                or bool(self._TEST_GO.search(label))
                or bool(self._TEST_JUNIT.search(label)))

    def _is_cron(self, label: str, node_type: str) -> bool:
        return bool(self._CRON_DECORATOR.search(label)) or bool(self._CRON_NODE.search(label))


def register_detector(framework_name: str, detector: FrameworkEntryPointDetector) -> None:
    _DETECTOR_REGISTRY[framework_name] = detector


class GraphEntryPointDetector:
    _ENTRY_LABELS = frozenset({"main", "run", "start", "index", "init", "bootstrap", "server", "app", "serve", "execute", "handle", "process", "entry", "launch", "setup"})
    _HTTP_PATHS = frozenset({"route", "controller", "handler", "api", "endpoint", "middleware", "service"})
    _TEST_PATTERNS = frozenset({"test_", "_test", "testspec"})

    def detect(self, graph: nx.Graph) -> list[EntryPoint]:
        results: list[EntryPoint] = []
        for nid, ndata in graph.nodes(data=True):
            label = ndata.get("label", "")
            src_file = ndata.get("source_file", "")
            node_type = ndata.get("node_type", "")
            src_loc = ndata.get("source_location", "")
            language = ndata.get("language", "")

            line = 0
            if src_loc:
                m = re.search(r"(\d+)", str(src_loc))
                if m:
                    line = int(m.group(1))

            label_lower = label.lower()

            if self._is_entry_label(label_lower, node_type):
                results.append(EntryPoint(
                    name=label, kind="CLI", file=src_file, line=line,
                    language=language, framework="",
                ))

            if self._is_http_path(src_file.lower(), node_type):
                results.append(EntryPoint(
                    name=label, kind="HTTP", file=src_file, line=line,
                    language=language, framework="",
                ))

            if self._is_test_pattern(label_lower, node_type):
                results.append(EntryPoint(
                    name=label, kind="TEST", file=src_file, line=line,
                    language=language, framework="",
                ))

        structure_eps = self._detect_structure_entry_points(graph)
        results.extend(structure_eps)

        return list({(ep.name, ep.file): ep for ep in results}.values())

    def _is_entry_label(self, label_lower: str, node_type: str) -> bool:
        if not node_type:
            return "main" in label_lower or "server" in label_lower
        return any(word in label_lower.split(".")[-1] for word in self._ENTRY_LABELS)

    def _is_http_path(self, src_lower: str, node_type: str) -> bool:
        if not node_type:
            return False
        return any(word in src_lower for word in self._HTTP_PATHS)

    def _is_test_pattern(self, label_lower: str, node_type: str) -> bool:
        if not node_type:
            return False
        return "test" in label_lower or label_lower.endswith("spec")

    def _detect_structure_entry_points(self, graph: nx.Graph) -> list[EntryPoint]:
        results: list[EntryPoint] = []
        for nid in graph.nodes:
            ndata = graph.nodes[nid]
            if not ndata.get("source_file"):
                continue
            has_callers = False
            has_callees = False
            for nb in graph.neighbors(nid):
                edata = graph.get_edge_data(nid, nb)
                if edata and edata.get("relation") in ("calls", "CALLS"):
                    if edata.get("_src") == nid:
                        has_callees = True
                    else:
                        has_callers = True
            degree = graph.degree(nid)
            if degree >= 3 and has_callees and not has_callers:
                sl = ndata.get("source_location", "0")
                line = 0
                m = re.search(r"(\d+)", str(sl))
                if m:
                    line = int(m.group(1))
                results.append(EntryPoint(
                    name=ndata.get("label", nid),
                    kind="CLI",
                    file=ndata.get("source_file", ""),
                    line=line,
                    language=ndata.get("language", ""),
                ))
        return results


def detect_entry_points(graph: nx.Graph, extractions: list, language: str = "") -> list[EntryPoint]:
    default = FrameworkEntryPointDetector()
    results: list[EntryPoint] = []
    results.extend(default.detect(graph, extractions))
    for fw, detector in _DETECTOR_REGISTRY.items():
        results.extend(detector.detect(graph, extractions))
    results = list({(ep.name, ep.file, ep.line): ep for ep in results}.values())
    if not results:
        results = GraphEntryPointDetector().detect(graph)
    return results


def score_entry_points(entry_points: list[EntryPoint], graph: nx.Graph) -> list[tuple[EntryPoint, float]]:
    file_stats: dict[str, tuple[int, int, str]] = {}
    for nid, ndata in graph.nodes(data=True):
        nfile = ndata.get("source_file", "")
        if not nfile:
            continue
        count, bonus, _ = file_stats.get(nfile, (0, 0, ""))
        count += 1
        nlabel = ndata.get("label", "").lower()
        if "main" in nlabel or "handler" in nlabel:
            bonus += 1
        file_stats[nfile] = (count, bonus, nid)

    scored: list[tuple[EntryPoint, float]] = []
    for ep in entry_points:
        count, bonus, node_id = file_stats.get(ep.file, (0, 0, None))
        score = float(count) + float(bonus)
        if node_id:
            degree = graph.degree(node_id) if node_id in graph else 0
            score += degree * 0.5
        kind_bonus = {"CLI": 2.0, "HTTP": 2.0, "CRON": 1.5, "TEST": 1.0, "EXPORT": 1.5, "EVENT": 1.0, "PAGE": 1.5}
        score += kind_bonus.get(ep.kind, 0.0)
        scored.append((ep, score))
    max_score = max([s for _, s in scored], default=1.0)
    if max_score > 0:
        scored = [(ep, s / max_score) for ep, s in scored]
    return sorted(scored, key=lambda x: x[1], reverse=True)

def _resolve_node_id(graph: nx.Graph, ep: EntryPoint) -> str | None:
    return None
