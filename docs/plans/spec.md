# Fork Enhancement — Technical Specification

## 1. Indexing Layer (`graphify/index.py`)

### 1.1 Edge Relation Type Index

```python
from typing import Dict, List, Tuple, Any
import networkx as nx

def build_edge_index(G: nx.Graph) -> Dict[str, List[Tuple[str, str, dict]]]:
    """Build a hash map: relation_type → [(u, v, edge_data), ...].
    Built once at graph load, speeds up filtered traversal from O(E) scan to O(1) lookup."""
    ...

def get_edges_by_relation(G: nx.Graph, relation_type: str) -> List[Tuple[str, str, dict]]:
    """Return all edges of a given relation_type using the index."""
    ...
```

### 1.2 Confidence Bitmap Filter

```python
from bitarray import bitarray  # optional dependency

def build_confidence_bitmap(G: nx.Graph) -> Dict[str, bitarray]:
    """Three bit arrays: EXTRACTED, INFERRED, AMBIGUOUS.
    Each bit corresponds to an edge index. O(1) edge exclusion before traversal."""
    ...

def filter_edges_by_confidence(G, min_confidence: str = "INFERRED") -> set:
    """Return edge indices meeting confidence threshold. EXTRACTED > INFERRED > AMBIGUOUS."""
    ...
```

### 1.3 Node Label Inverted Index

```python
def build_label_trie(G: nx.Graph) -> dict:
    """In-memory prefix trie for sub-millisecond node lookup.
    Replaces current _score_nodes() linear scan."""
    ...

def lookup_nodes_by_prefix(G, prefix: str) -> List[str]:
    """Return node IDs whose label starts with prefix."""
    ...
```

### Integration

```python
# In build.py build_from_json():
def build_from_json(extraction: dict, *, directed: bool = False, build_indexes: bool = True) -> nx.Graph:
    G = _build_graph(extraction, directed)
    if build_indexes:
        G.graph["indexes"] = {
            "edge_relation": build_edge_index(G),
            "confidence_bitmap": build_confidence_bitmap(G),
            "label_trie": build_label_trie(G),
        }
    return G
```

---

## 2. Advanced Traversal (`graphify/serve.py` additions)

### 2.1 Bidirectional BFS

```python
def _bidirectional_shortest_path(G, src: str, tgt: str, max_hops: int = 20) -> tuple[list, set, list]:
    """Bidirectional BFS from src and tgt simultaneously.
    For a 6-hop path: from 15.6B candidates (unidirectional) → ~250k (bidirectional).
    Returns (path_nodes, visited, edges_seen)."""
    ...
```

Exposed as `mode="bidirectional"` in `query_graph` and `shortest_path` MCP tools.

### 2.2 Weighted Dijkstra

```python
def _dijkstra_shortest_path(G, src: str, tgt: str, weighted: bool = True) -> tuple[list, float]:
    """Uses edge weight field. Returns (path, total_weight).
    Exposed via shortest_path with weighted=True parameter."""
    ...
```

### 2.3 A* with Community Heuristic

```python
def _astar_search(G, src: str, tgt: str, communities: dict, max_hops: int = 20) -> tuple[list, set]:
    """A* search with heuristic: h(n) = 1 if community(n) != community(target) else 0.5.
    Encourages traversal to stay within the target's community.
    Exposed as mode="astar"."""
    ...
```

### New query_graph modes

```
query_graph(question, mode="bfs")           ← existing (default)
query_graph(question, mode="dfs")           ← existing
query_graph(question, mode="bidirectional")  ← new
query_graph(question, mode="astar")          ← new
```

### New shortest_path parameters

```
shortest_path(source, target, max_hops=8)         ← existing
shortest_path(source, target, max_hops=8, weighted=True)  ← new
shortest_path(source, target, max_hops=8, mode="bidirectional")  ← new
```

---

## 3. Query Planning (`graphify/query_planner.py`)

```python
def select_start_nodes(G, candidates: list[str]) -> list[str]:
    """From scored candidates, pick the one with lowest degree.
    This is the most selective start point, minimizing fan-out."""
    ...

def order_frontier_by_edge_preference(G, frontier: set, preference: str = "extracted") -> list:
    """Prefer traversing EXTRACTED edges before INFERRED before AMBIGUOUS.
    More reliable paths discovered first."""
    ...

def estimate_cardinality(G, node: str, relation_filter: str = None) -> int:
    """Estimate how many edges will be traversed from this node.
    Used for query planning: start from the least-connected node."""
    ...
```

---

## 4. Caching + Materialized Views

### 4.1 Query Result Cache (`graphify/query_cache.py`)

```python
import hashlib
from pathlib import Path

CACHE_TTL_SECONDS = 3600  # 1 hour

def cache_key(query_text: str, mode: str, depth: int, budget: int) -> str:
    """SHA256 of (query_text, mode, depth, budget) → hex digest."""
    return hashlib.sha256(f"{query_text}|{mode}|{depth}|{budget}".encode()).hexdigest()

def get_cached_query(cache_dir: Path, key: str) -> str | None:
    """Load cached subgraph text if exists and not expired."""
    ...

def set_cached_query(cache_dir: Path, key: str, result: str) -> None:
    """Store subgraph text in cache."""
    ...
```

### 4.2 Materialized Views (`graphify/matviews.py`)

```python
def materialize_transitive_closure(G, relation_type: str) -> nx.Graph:
    """Precompute transitive closure over edges of a given relation type.
    Returns a graph where edge (u,v) exists if there's any path of relation_type edges from u to v."""
    ...

def write_materialized_view(G, relation_type: str, output_dir: Path) -> None:
    """Write transitive closure as edge list to graphify-out/matviews/."""
    ...

def load_materialized_view(relation_type: str, input_dir: Path) -> nx.Graph | None:
    """Load precomputed transitive closure lazily."""
    ...

# Precomputed closures:
# - call_graph: all 'calls' edges transitively closed
# - import_chain: all 'imports'/'imports_from' closures
# - rationale_chain: all 'rationale_for' closures
```

### Build integration

```python
# In build.py:
def build_from_json(extraction: dict, *, directed: bool = False,
                    build_indexes: bool = True,
                    materialize: list[str] | None = None) -> nx.Graph:
    """If materialize=["calls", "imports"], precompute closures after graph construction."""
    ...
```

---

## 5. Approximate Methods

### 5.1 Bloom Filters (`graphify/approx.py`)

```python
from bitarray import bitarray
import hashlib

class GraphBloomFilter:
    """Bloom filter for O(1) "does this edge exist?" checks.
    Key format: relation:confidence:source_label:target_label"""

    def __init__(self, capacity: int, error_rate: float = 0.01):
        ...

    def add_edge(self, relation: str, confidence: str, src_label: str, tgt_label: str) -> None:
        ...

    def likely_contains(self, relation: str, confidence: str, src_label: str, tgt_label: str) -> bool:
        ...
```

### 5.2 Graph Sampling

```python
def sample_subgraph(G, sample_rate: float = 0.1, method: str = "random_walk") -> nx.Graph:
    """Random walk sampling preserving community proportions.
    query_graph(approximate=True, sample_rate=0.1) → 10x faster, ~90% accuracy."""
    ...

def estimate_graph_stats(G, sample_rate: float = 0.1) -> dict:
    """Estimate node/edge counts, avg degree, density from sample."""
    ...
```

### 5.3 Embeddings (`graphify/embed.py`, optional)

```python
import numpy as np

EMBEDDING_DIM = 128  # Default: 128D vectors, lightweight

def generate_node_embeddings(G, method: str = "node2vec") -> dict[str, np.ndarray]:
    """Generate embeddings for all nodes. Returns {node_id: embedding_vector}.
    Requires optional dependency group."""
    ...

def search_similar_nodes(G, query_node: str, top_k: int = 10) -> list[tuple[str, float]]:
    """Return top-k semantically similar nodes by embedding cosine similarity."""
    ...

# Subcommand: graphify embed
#   --method node2vec|deepwalk|line
#   --dimensions 128
#   --output graphify-out/embeddings.json
```

---

## 6. Typed Code Schema (`graphify/code_schema.py`)

### Node Types (17 types for code)

```python
from enum import Enum, auto

class NodeType(Enum):
    # Structural
    FUNCTION = auto()
    CLASS = auto()
    METHOD = auto()
    INTERFACE = auto()
    ENUM = auto()
    TYPE_ALIAS = auto()
    CONSTRUCTOR = auto()
    STRUCT = auto()         # Go, C
    TRAIT = auto()          # Rust, PHP, Scala
    NAMESPACE = auto()
    MODULE = auto()
    # Behavioral
    ROUTE = auto()          # HTTP API endpoint
    TOOL = auto()           # MCP tool definition
    PROCESS = auto()        # Execution flow
    # Legacy (for non-code files)
    CONCEPT = auto()        # Docs, papers, images
    FILE = auto()           # File-level hub node
```

### Edge Types (21 types for code relationships)

```python
class EdgeType(Enum):
    # Structural
    CALLS = auto()             # function calls function
    IMPORTS = auto()           # imports module
    EXTENDS = auto()           # class extends superclass
    IMPLEMENTS = auto()        # class implements interface
    METHOD_OVERRIDES = auto()  # method overrides parent method
    CONTAINS = auto()          # file/class contains child
    MEMBER_OF = auto()         # method/enum member of class
    # Behavioral
    HANDLES_ROUTE = auto()     # handler handles HTTP route
    STEP_IN_PROCESS = auto()   # step in execution flow
    # Semantic
    USES = auto()              # generic usage
    REFERENCES = auto()        # text reference
    RATIONALE_FOR = auto()     # documentation rationale
    SEMANTICALLY_SIMILAR_TO = auto()
    # Legacy
    DEPENDS_ON = auto()
    CONFIGURES = auto()
    INFORMS = auto()
```

### Node Attributes

```python
@dataclass
class TypedNode:
    id: str
    label: str
    node_type: NodeType
    source_file: str
    source_location: str           # e.g. "L42"
    language: str = ""
    signature: str = ""            # Full function/method signature
    docstring: str = ""            # Extracted docstring
    visibility: str = "public"     # public, private, protected
    is_exported: bool = False      # Exported from module
    community: int | None = None
```

### Edge Attributes

```python
@dataclass
class TypedEdge:
    source: str
    target: str
    edge_type: EdgeType
    confidence: str                # EXTRACTED, INFERRED, AMBIGUOUS
    confidence_score: float        # 1.0, 0.5-0.9, 0.2
    source_file: str
    source_location: str
    weight: float = 1.0
```

### Code Emitter

```python
# graphify/code_emitter.py

def emit_code_node(node: TypedNode) -> dict:
    """Convert TypedNode to graphify extraction dict format (backward compatible)."""
    return {
        "id": node.id,
        "label": node.label,
        "node_type": node.node_type.name,
        "file_type": "code",
        "source_file": node.source_file,
        "source_location": node.source_location,
        "language": node.language,
        "signature": node.signature,
        "docstring": node.docstring,
        "visibility": node.visibility,
        "is_exported": node.is_exported,
    }

def emit_code_edge(edge: TypedEdge) -> dict:
    """Convert TypedEdge to graphify extraction dict format."""
    return {
        "source": edge.source,
        "target": edge.target,
        "relation": edge.edge_type.name.lower(),
        "confidence": edge.confidence,
        "confidence_score": edge.confidence_score,
        "source_file": edge.source_file,
        "source_location": edge.source_location,
        "weight": edge.weight,
    }
```

---

## 7. Call Resolution Engine

### 7.1 Import Resolution (`graphify/imports.py`)

```python
from enum import Enum

class ImportSemantics(Enum):
    NAMED = auto()               # import { Foo } from './foo' (JS/TS)
    WILDCARD_LEAF = auto()       # from foo import Bar (Python), import foo.Bar (Java)
    WILDCARD_TRANSITIVE = auto() # from foo import * (Python)
    NAMESPACE = auto()           # import foo (Python), import * as foo (JS/TS)

def resolve_import(target: str, from_file: Path, all_files: list[Path],
                   semantics: ImportSemantics, language: str) -> str | None:
    """Resolve an import to a specific node ID.
    Returns the file node ID of the resolved target, or None if external."""
    ...

# Language-specific resolvers:
# graphify/import_resolvers/python.py
# graphify/import_resolvers/typescript.py
# graphify/import_resolvers/go.py
# graphify/import_resolvers/java.py
```

### 7.2 Call Extraction (`graphify/call_extractors/`)

```python
@dataclass
class ExtractedCallSite:
    name: str                    # Called function/method name
    receiver: str | None = None  # Explicit receiver: self.foo → receiver="self"
    arity: int = 0               # Number of arguments
    line: int = 0                # Source line number
    in_class: str | None = None  # Enclosing class (if inside a method)
    is_dynamic: bool = False     # True if receiver type is uncertain

def extract_calls(parsed_file) -> list[ExtractedCallSite]:
    """Extract all call sites from a parsed file using tree-sitter AST.
    Language-specific implementations in call_extractors/."""
    ...

# Per-language implementations:
# graphify/call_extractors/python.py
# graphify/call_extractors/typescript.py
# graphify/call_extractors/go.py
# graphify/call_extractors/java.py
```

### 7.3 Receiver Inference (`graphify/receiver.py`)

```python
def infer_receiver(call: ExtractedCallSite, enclosing_class: str | None,
                   graph_nodes: dict[str, TypedNode]) -> str | None:
    """Infer the actual receiver type for a call.
    - self/this → enclosing class lookup
    - cls → enclosing class (Python classmethod)
    - super() → parent class via MRO
    - Constructor inference for MyClass() → resolves to MyClass.__init__ or MyClass constructor
    Returns None if receiver cannot be determined."""
    ...
```

### 7.4 Method Resolution Order (`graphify/mro.py`)

```python
from enum import Enum

class MROStrategy(Enum):
    FIRST_WINS = auto()    # Java, C#, C++, TypeScript, Go
    C3 = auto()            # Python
    RUBY_MIXIN = auto()    # Ruby
    NONE = auto()          # Single inheritance only

def resolve_method(target: str, class_hierarchy: dict[str, list[str]],
                   strategy: MROStrategy) -> str | None:
    """Walk the MRO to find which class actually provides the method 'target'.
    Returns the class node ID that defines the method, or None if not found."""
    ...

def build_class_hierarchy(G) -> dict[str, list[str]]:
    """Build parent→children and children→parents maps from EXTENDS/IMPLEMENTS edges."""
    ...

# Per-language MRO strategies:
def mro_first_wins(target: str, class_node: str, hierarchy) -> str | None: ...
def mro_c3(target: str, class_node: str, hierarchy) -> str | None: ...
def mro_ruby_mixin(target: str, class_node: str, hierarchy) -> str | None: ...
```

### 7.5 Cross-File Resolution (`graphify/cross_file.py`)

```python
def build_scc_processing_order(import_graph: nx.DiGraph) -> list[list[str]]:
    """Topologically sort strongly connected components for type propagation.
    Processes files in order: leaf nodes first, hub nodes last."""
    ...

def propagate_types_across_files(files: list[Path], call_sites: dict,
                                  type_registry: dict) -> dict:
    """Cross-file type propagation: resolve call targets across import boundaries.
    Updates type_registry with discovered types."""
    ...
```

### 7.6 Call Resolution DAG (`graphify/call_dag.py`)

```python
@dataclass
class ResolvedCall:
    caller_id: str
    callee_id: str
    confidence: str               # EXTRACTED or INFERRED
    resolution_path: list[str]    # Steps: [extract, infer_receiver, select_dispatch, resolve_target]

def resolve_call_graph(G, extraction: dict) -> list[ResolvedCall]:
    """6-stage call resolution DAG:
    1. extract → extract_calls() from tree-sitter AST
    2. infer-receiver → self/this resolution, constructor inference
    3. select-dispatch → static dispatch by default, virtual dispatch where needed
    4. resolve-target → import resolution + cross-file type propagation
    5. resolve-method → MRO walk to find actual method definition
    6. emit-edge → create CALLS edges with confidence scores
    Returns list of resolved calls ready for edge emission."""
    ...
```

### New MCP tools (Phase 9)

```
context({name: "validateUser"})  →
  symbol: {kind, file, line, signature, visibility}
  incoming: {calls: [...], imports: [...]}
  outgoing: {calls: [...]}
  processes: [{name, step_index, total_steps}]

impact({target: "UserService", direction: "upstream", minConfidence: 0.8})  →
  target: {kind, file}
  upstream: {
    depth_1: [{symbol, relation, confidence, file}],
    depth_2: [{symbol, relation, confidence, file}],
    ...
  }
  downstream: { depth_1: [...], depth_2: [...], ... }
  summary: {total_affected, risk_level}
```

---

## 8. Process Tracing (`graphify/processes.py`)

```python
@dataclass
class EntryPoint:
    node_id: str
    label: str
    kind: str                    # route_handler, cli_main, middleware, test, cron, library_export
    route: str | None = None     # HTTP route pattern e.g. "/api/users"
    method: str | None = None    # HTTP method e.g. "GET", "POST"
    score: float = 0.0           # Priority score

@dataclass
class ProcessStep:
    node_id: str
    step_index: int
    call_chain: list[str]        # Path from entry to this step
    file: str
    line: str
    is_branching: bool = False   # Calls multiple different targets

@dataclass  
class Process:
    id: str
    name: str
    entry_point: EntryPoint
    steps: list[ProcessStep]
    confidence: float            # 0-1, based on edge confidences
    total_calls: int
    unique_files: int

def detect_entry_points(G) -> list[EntryPoint]:
    """Framework-aware entry point detection.
    Next.js: route.ts files, getServerSideProps, API route handlers
    Express: app.get(), app.post(), router.use()
    Flask: @app.route() decorator functions
    CLI: main() in root files, click/argparse entry points
    Test: test_* functions, *Test classes
    Cron: scheduled functions, cron job handlers
    """

def trace_process(G, entry: EntryPoint, max_depth: int = 20) -> Process:
    """Trace execution from entry point following CALLS edges.
    BFS along CALLS edges, deduplicating cycles.
    Stops at max_depth or when no more CALLS edges exist."""

def score_entry_points(entries: list[EntryPoint]) -> list[tuple[EntryPoint, float]]:
    """Score entry points by relevance:
    route_handler (10) > CLI (7) > test (3) > library_export (1)"""

def build_processes(G) -> list[Process]:
    """Full process construction: detect → trace → deduplicate → write."""

def cluster_processes(processes: list[Process]) -> list[list[Process]]:
    """Group overlapping processes by shared call paths.
    Deduplicate near-identical traces (>90% symbol overlap)."""
```

### New MCP tool

```
detect_changes({scope: "all"})  →
  summary: {changed_count, affected_count, changed_files, risk_level}
  changed_symbols: [{name, kind, file, changed_lines}]
  affected_processes: [{name, step_count, affected_steps}]
  recommendations: [{action, reason}]
```

### Output: `graphify-out/processes.json`

```json
{
  "processes": [
    {
      "id": "proc_user_registration",
      "name": "User Registration Flow",
      "entry_point": {
        "node_id": "routes_users_register",
        "kind": "route_handler",
        "route": "/api/users/register",
        "method": "POST"
      },
      "steps": [
        {"step_index": 0, "file": "routes/users.ts", "line": "L42"},
        {"step_index": 1, "file": "services/user.ts", "line": "L15"},
        ...
      ],
      "confidence": 0.92,
      "total_calls": 12,
      "unique_files": 4
    }
  ]
}
```

---

## 9. Hybrid Search (`graphify/search/`)

### 9.1 BM25 Index (`graphify/search/bm25.py`)

```python
class BM25Index:
    """BM25 keyword search on symbol names, file paths, docstrings.
    Built at graph load time. Incrementally updateable."""

    def __init__(self):
        self.documents: dict[str, str] = {}  # node_id → indexed text

    def index_node(self, node_id: str, node: TypedNode) -> None:
        """Add a node to the BM25 index.
        Indexes: label + signature + docstring + file path."""
        ...

    def search(self, query: str, top_k: int = 20) -> list[tuple[str, float]]:
        """Return (node_id, score) sorted by BM25 score."""
        ...
```

### 9.2 Semantic Embeddings (`graphify/search/embeddings.py`)

```python
import numpy as np

# Model: Snowflake arctic-embed-xs (384D) or all-MiniLM-L6-v2 (384D)
# Incremental via SHA1 content hash — only re-embed changed symbols.
# Stored in graphify-out/embeddings/ with sharding (>50k symbols splits into batches).

def generate_embeddings(G, symbols: list[str], model_name: str = "all-MiniLM-L6-v2") -> dict[str, np.ndarray]:
    """Generate embeddings for code symbols. Returns {node_id: embedding_vector}.
    Incremental: only re-embedded if SHA1(content) changed from last run."""
    ...

def search_by_embedding(query: str, embeddings: dict[str, np.ndarray],
                         top_k: int = 20, model_name: str = "all-MiniLM-L6-v2") -> list[tuple[str, float]]:
    """Search for nodes semantically similar to query text.
    Returns (node_id, cosine_similarity) sorted descending."""
    ...

def save_embeddings(embeddings: dict[str, np.ndarray], output_dir: Path) -> None:
    """Shard embeddings into batches of 10000 nodes per file."""

def load_embeddings(input_dir: Path) -> dict[str, np.ndarray]:
    """Load and merge all embedding shards."""
```

### 9.3 Reciprocal Rank Fusion (`graphify/search/fusion.py`)

```python
def reciprocal_rank_fusion(result_sets: list[list[tuple[str, float]]], k: int = 60) -> list[tuple[str, float]]:
    """Merge multiple ranked result lists via Reciprocal Rank Fusion.
    RRF_score(node) = sum(1 / (k + rank_in_list))
    Merges by rank, not score — avoids calibration issues between BM25 and vector scorers."""
    ...

def hybrid_search(G, query: str, bm25_index: BM25Index, embeddings, top_k: int = 20) -> list[tuple[str, float]]:
    """Orchestrate BM25 + semantic search + RRF fusion.
    1. BM25 search → ranked results
    2. Semantic vector search → ranked results
    3. RRF merge → combined ranked results
    Returns (node_id, rrf_score) sorted."""
    ...
```

### 9.4 Process-Grouped Results (`graphify/search/grouping.py`)

```python
@dataclass
class SearchResult:
    node_id: str
    score: float
    process: str | None = None      # Which process this node belongs to
    is_cross_community: bool = False

def group_by_process(results: list[SearchResult], processes: list[Process]) -> dict[str, list[SearchResult]]:
    """Group search results by the process they belong to.
    Cross-community results flagged.
    Priority score per process based on symbol match density."""

def format_grouped_results(grouped: dict[str, list[SearchResult]]) -> str:
    """Format grouped results for MCP tool response.
    processes: [{summary, priority, symbol_count, process_type, step_count}]
    definitions: [{name, type, file, confidence}]
    references: [{name, type, file, process_context}]"""
```

### Integration into serve.py

```python
# serve.py: replace _bfs()/_dfs() as default query_graph implementation
# Keep _bfs()/_dfs() available as mode="bfs"/mode="dfs"

def _hybrid_query(G, question: str, bm25: BM25Index, embeddings, processes,
                  top_k: int = 20, token_budget: int = 2000) -> str:
    """Default query mode. BM25 + semantic + RRF fusion + process grouping."""
    ...

# query_graph defaults to mode="hybrid" (backward compatible via mode="bfs"/"dfs")
```

---

## 10. Agent Integration (`graphify/skills/`)

### Subcommand

```
graphify skills                    # Generate 4 base skills
graphify skills --repo             # Generate per-community SKILL.md
graphify skills --hooks            # Generate PreToolUse + PostToolUse hooks
graphify skills --all              # All of the above
```

### Output files

```
.claude/skills/graphify/
├── exploring.md              # Graph navigation instructions
├── debugging.md              # Call chain tracing instructions
├── impact-analysis.md        # Blast radius instructions
└── refactoring.md            # Dependency mapping instructions

.claude/skills/generated/
├── auth-module.md            # Per-community SKILL.md
├── payment-processing.md
└── ...

.claude/hooks/
├── pre-tool-use-graphify.sh  # Enrich searches with graph context
└── post-tool-use-graphify.sh # Detect stale index after writes
```

### Hook generation (`graphify/skills/hooks.py`)

```python
def generate_pre_tool_use_hook(output_dir: Path) -> None:
    """PreToolUse hook: enriches search queries with relevant graph nodes
    before tool calls. Output to .claude/hooks/pre-tool-use-graphify.sh"""

def generate_post_tool_use_hook(output_dir: Path) -> None:
    """PostToolUse hook: detects stale index after file writes,
    prompts agent to reindex. Output to .claude/hooks/post-tool-use-graphify.sh"""
```

---

## 11. Multi-Repo Groups (`graphify/registry.py`, `graphify/groups.py`, etc.)

### Global Registry

```python
# graphify/registry.py — ~/.graphify/registry.json

@dataclass
class RepoEntry:
    repo_id: str
    name: str
    path: str                     # Absolute path
    last_commit: str              # HEAD commit hash at last index
    group: str | None = None      # Group membership
    url: str | None = None        # Remote URL

class Registry:
    def register(self, repo_path: str, meta: dict = None) -> RepoEntry: ...
    def unregister(self, repo_id: str) -> None: ...
    def list_repos(self) -> list[RepoEntry]: ...
    def get(self, repo_id: str) -> RepoEntry | None: ...
    def update_commit(self, repo_id: str, commit: str) -> None: ...
```

### Lazy Connection Pool

```python
# graphify/lazy_pool.py

class GraphPool:
    """Lazy graph connection pool.
    Opens graphs on first query, evicts after 5-minute inactivity, max 5 concurrent."""

    def get_graph(self, repo_id: str) -> nx.Graph: ...
    def evict(self, repo_id: str) -> None: ...
    def evict_inactive(self, ttl_minutes: int = 5) -> int: ...
```

### Repository Groups

```python
# graphify/groups.py

def group_create(name: str) -> dict: ...
def group_add(group: str, path: str, repo: str) -> None: ...
def group_sync(name: str) -> dict:
    """Extract contracts (shared interfaces, APIs, type exports)
    and build cross-repo bridge edges. Returns {contracts_found, bridges_created}."""
def group_contracts(name: str) -> dict: ...
def group_query(name: str, q: str) -> dict:
    """Search execution flows across all repos in a group."""
def group_status(name: str) -> dict: ...
```

### Contract Bridge

```python
# graphify/contract_bridge.py

def detect_shared_interfaces(repos: list[nx.Graph]) -> list[dict]:
    """Cross-repo dependency mapping.
    Detects shared interfaces via type name + signature matching."""

def map_api_consumers(apis: list[EntryPoint], repos: list[nx.Graph]) -> list[dict]:
    """API route → consumer mapping across repos."""
```

### Group-Aware MCP Tools

```
group_list        → [{name, member_count, repo_paths}]
group_sync        → {contracts_found, bridges_created}
group_contracts   → {providers: [...], consumers: [...], cross_links: [...]}
group_query       → {repo_results: {...}, merged: [...RRF merged]}
group_status      → {repos: [{repo, last_indexed, head_commit, stale}]}
```

---

## 12. Test Strategy

### Per-Module Tests (follow existing pattern: `tests/test_<module>.py`)

| New Module | Test File | Min Tests |
|------------|-----------|-----------|
| `graphify/index.py` | `tests/test_index.py` | 8 |
| `graphify/query_cache.py` | `tests/test_query_cache.py` | 6 |
| `graphify/matviews.py` | `tests/test_matviews.py` | 4 |
| `graphify/approx.py` | `tests/test_approx.py` | 5 |
| `graphify/code_schema.py` | `tests/test_code_schema.py` | 6 |
| `graphify/code_emitter.py` | `tests/test_code_emitter.py` | 5 |
| `graphify/imports.py` | `tests/test_imports.py` | 6 |
| `graphify/receiver.py` | `tests/test_receiver.py` | 5 |
| `graphify/mro.py` | `tests/test_mro.py` | 6 |
| `graphify/cross_file.py` | `tests/test_cross_file.py` | 4 |
| `graphify/call_dag.py` | `tests/test_call_dag.py` | 5 |
| `graphify/processes.py` | `tests/test_processes.py` | 8 |
| `graphify/search/bm25.py` | `tests/test_search_bm25.py` | 5 |
| `graphify/search/embeddings.py` | `tests/test_search_embeddings.py` | 4 |
| `graphify/search/fusion.py` | `tests/test_search_fusion.py` | 4 |
| `graphify/skills/` | `tests/test_skills.py` | 6 |
| `graphify/registry.py` | `tests/test_registry.py` | 5 |

### Serve Tests (extend `tests/test_serve.py`)

- Bidirectional BFS traversal (3 tests)
- A* with community heuristic (2 tests)
- Weighted Dijkstra (2 tests)
- Hybrid search mode (3 tests)
- Process-grouped query results (2 tests)
- Context tool response format (2 tests)
- Impact tool response format (2 tests)
- Detect changes tool (2 tests)

### Integration Tests

- `tests/test_benchmark_query.py` — BSBM-synthetic benchmark (Phase 1)
- `tests/test_call_resolution_fixtures.py` — Standard fixtures for call DAG validation (Phase 9)
- `tests/test_process_tracing_fixtures.py` — Fixture repos for process trace validation (Phase 10)

### Benchmark Suite (Phase 1)

```python
# tests/test_benchmark_query.py

def test_benchmark_bsbm_50k_nodes(benchmark):
    """Benchmark query performance on BSBM-synthetic 50k-node graph."""
    ...

def test_benchmark_4hop_path(benchmark):
    """Benchmark 4-hop shortest path query."""
    ...

def test_benchmark_6hop_path(benchmark):
    """Benchmark 6-hop shortest path query."""
    ...

def test_benchmark_10hop_path(benchmark):
    """Benchmark 10-hop shortest path query."""
    ...

def test_benchmark_throughput(benchmark):
    """Benchmark queries/sec on 50k-node graph."""
    ...

def test_benchmark_memory_overhead():
    """Measure: index overhead vs. raw NetworkX memory."""
    ...
```

---

## 13. Dependencies

### New Required
- `bitarray>=3.0` — Confidence bitmap filters

### New Optional (extras groups)
- `approximate = ["numpy>=1.24", "scipy>=1.10"]` — Node2vec, bloom filters
- `search = ["numpy>=1.24", "scikit-learn>=1.3"]` — BM25, embeddings
- `skills = []` — No extra deps (pure Python)

### Add to pyproject.toml

```toml
[project.optional-dependencies]
# ... existing groups ...
approximate = ["numpy", "scipy"]
search = ["numpy", "scikit-learn"]
skills = []

[project.extras]
all = ["...", "bitarray", "numpy", "scipy", "scikit-learn"]
```
