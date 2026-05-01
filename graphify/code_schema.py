"""Typed code schema — canonical node types and edge relations for code intelligence.

Defines 44 node types and 21 edge types that graphify's code extractors
can emit. Every node carries source_file + source_location. Edges carry
confidence tiers: EXTRACTED (1.0, from AST), INFERRED (0.5-0.9, from
cross-file resolution), AMBIGUOUS (0.1-0.4, low-certainty matches).
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field


class NodeType(str, Enum):
    FILE = "file"
    PACKAGE = "package"
    MODULE = "module"
    CLASS = "class"
    INTERFACE = "interface"
    ENUM = "enum"
    STRUCT = "struct"
    TRAIT = "trait"
    PROTOCOL = "protocol"
    FUNCTION = "function"
    METHOD = "method"
    CONSTRUCTOR = "constructor"
    PROPERTY = "property"
    VARIABLE = "variable"
    CONSTANT = "constant"
    TYPE_ALIAS = "type_alias"
    NAMESPACE = "namespace"
    IMPORT = "import"
    EXPORT = "export"
    CALL_SITE = "call_site"
    DECORATOR = "decorator"
    ANNOTATION = "annotation"
    GENERIC = "generic"
    LAMBDA = "lambda"
    ARROW_FUNC = "arrow_function"
    ENUM_MEMBER = "enum_member"
    FIELD = "field"
    PARAMETER = "parameter"
    RETURN_TYPE = "return_type"
    SUPERCLASS = "superclass"
    GENERIC_ARG = "generic_argument"
    TYPE_PARAM = "type_parameter"
    TEST = "test"
    FIXTURE = "fixture"
    CONFIG = "config"
    ENTRY_POINT = "entry_point"
    PROCESS = "process"
    DOC_COMMENT = "doc_comment"
    RATIONALE = "rationale"
    ERROR_HANDLER = "error_handler"
    MIDDLEWARE = "middleware"
    ROUTE = "route"
    TEMPLATE = "template"
    MIGRATION = "migration"


class EdgeType(str, Enum):
    CONTAINS = "contains"
    IMPORTS = "imports"
    IMPORTS_FROM = "imports_from"
    EXPORTS = "exports"
    CALLS = "calls"
    CALLED_BY = "called_by"
    INHERITS = "inherits"
    IMPLEMENTS = "implements"
    METHOD = "method"
    METHOD_OF = "method_of"
    CASE_OF = "case_of"
    DECORATES = "decorates"
    ANNOTATES = "annotates"
    PARAMETER_OF = "parameter_of"
    RETURNS = "returns"
    REFERENCES = "references"
    SEMANTIC_SIMILAR = "semantically_similar_to"
    RATIONALE_FOR = "rationale_for"
    STEP_IN = "step_in_process"
    TRANSITIONS_TO = "transitions_to"
    DEPENDS_ON = "depends_on"


class ConfidenceTier(str, Enum):
    EXTRACTED = "EXTRACTED"
    INFERRED = "INFERRED"
    AMBIGUOUS = "AMBIGUOUS"


CONFIDENCE_VALUES: dict[ConfidenceTier, float] = {
    ConfidenceTier.EXTRACTED: 1.0,
    ConfidenceTier.INFERRED: 0.7,
    ConfidenceTier.AMBIGUOUS: 0.3,
}

CONFIDENCE_PRIORITY: dict[ConfidenceTier, int] = {
    ConfidenceTier.EXTRACTED: 0,
    ConfidenceTier.INFERRED: 1,
    ConfidenceTier.AMBIGUOUS: 2,
}


@dataclass
class TypedNode:
    id: str
    label: str
    node_type: NodeType
    source_file: str = ""
    source_location: str = ""
    language: str = ""
    confidence: ConfidenceTier = ConfidenceTier.EXTRACTED
    extra: dict = field(default_factory=dict)


@dataclass
class TypedEdge:
    source: str
    target: str
    edge_type: EdgeType
    source_file: str = ""
    source_location: str = ""
    confidence: ConfidenceTier = ConfidenceTier.EXTRACTED
    confidence_score: float = 1.0
    weight: float = 1.0
    extra: dict = field(default_factory=dict)


SCHEMA_VERSION = 2
