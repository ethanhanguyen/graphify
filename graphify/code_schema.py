"""Typed code schema: NodeType, EdgeType enums and typed dataclasses for code-aware graph representation."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class NodeType(Enum):
    FUNCTION = auto()
    CLASS = auto()
    METHOD = auto()
    INTERFACE = auto()
    ENUM = auto()
    TYPE_ALIAS = auto()
    CONSTRUCTOR = auto()
    STRUCT = auto()
    TRAIT = auto()
    NAMESPACE = auto()
    MODULE = auto()
    ROUTE = auto()
    TOOL = auto()
    PROCESS = auto()
    CONCEPT = auto()
    FILE = auto()
    UNKNOWN = auto()


class EdgeType(Enum):
    CALLS = auto()
    IMPORTS = auto()
    IMPORTS_FROM = auto()
    EXTENDS = auto()
    IMPLEMENTS = auto()
    METHOD_OVERRIDES = auto()
    CONTAINS = auto()
    MEMBER_OF = auto()
    HANDLES_ROUTE = auto()
    STEP_IN_PROCESS = auto()
    USES = auto()
    REFERENCES = auto()
    RATIONALE_FOR = auto()
    SEMANTICALLY_SIMILAR_TO = auto()
    DEPENDS_ON = auto()
    CONFIGURES = auto()
    INFORMS = auto()
    INHERITS = auto()
    CASE_OF = auto()
    RELATES_TO = auto()


RELATION_MAP: dict[str, EdgeType] = {
    "calls": EdgeType.CALLS,
    "imports": EdgeType.IMPORTS,
    "imports_from": EdgeType.IMPORTS_FROM,
    "extends": EdgeType.EXTENDS,
    "implements": EdgeType.IMPLEMENTS,
    "method_overrides": EdgeType.METHOD_OVERRIDES,
    "contains": EdgeType.CONTAINS,
    "method": EdgeType.MEMBER_OF,
    "handles_route": EdgeType.HANDLES_ROUTE,
    "step_in_process": EdgeType.STEP_IN_PROCESS,
    "uses": EdgeType.USES,
    "references": EdgeType.REFERENCES,
    "rationale_for": EdgeType.RATIONALE_FOR,
    "semantically_similar_to": EdgeType.SEMANTICALLY_SIMILAR_TO,
    "depends_on": EdgeType.DEPENDS_ON,
    "configures": EdgeType.CONFIGURES,
    "informs": EdgeType.INFORMS,
    "inherits": EdgeType.INHERITS,
    "case_of": EdgeType.CASE_OF,
}

EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".cs": "csharp",
    ".kt": "kotlin",
    ".scala": "scala",
    ".php": "php",
    ".swift": "swift",
    ".lua": "lua",
    ".zig": "zig",
}


@dataclass
class TypedNode:
    id: str
    label: str
    node_type: NodeType
    source_file: str = ""
    source_location: str = ""
    language: str = ""
    signature: str = ""
    docstring: str = ""
    visibility: str = "public"
    is_exported: bool = False
    community: int | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "id": self.id,
            "label": self.label,
            "node_type": self.node_type.name,
            "file_type": "code",
            "source_file": self.source_file,
            "source_location": self.source_location,
        }
        if self.language:
            d["language"] = self.language
        if self.signature:
            d["signature"] = self.signature
        if self.docstring:
            d["docstring"] = self.docstring
        if self.visibility != "public":
            d["visibility"] = self.visibility
        if self.is_exported:
            d["is_exported"] = True
        if self.community is not None:
            d["community"] = self.community
        return d


@dataclass
class TypedEdge:
    source: str
    target: str
    edge_type: EdgeType
    confidence: str = "EXTRACTED"
    confidence_score: float = 1.0
    source_file: str = ""
    source_location: str = ""
    weight: float = 1.0

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.edge_type.name.lower(),
            "confidence": self.confidence,
            "confidence_score": self.confidence_score,
            "source_file": self.source_file,
            "source_location": self.source_location,
            "weight": self.weight,
        }
