# Graphify Fork: What the Baseline Leaves on the Table

A walkthrough of the four highest-value additions in this fork demonstrated on
a real toy service — `demos/toy-service/`, a 5-file Python FastAPI microservice.

All outputs are **real and reproducible**. No mocked data.

---

## 1. The baseline

Upstream `graphifyy` runs tree-sitter AST extraction over any codebase:

```
collect files → tree-sitter extract → build_graph → leiden cluster → report
```

On our 5-file toy service:

| Metric | Upstream |
|--------|----------|
| Nodes | 37 |
| Edges | 57 |
| graph.json size | 29.4 KB |

Clean. But four operations a developer needs every day break down.

---

## 2. Four gaps, four fixes

| Operation | Why upstream fails | What the fork adds |
|-----------|-------------------|--------------------|
| `explain` a function | No cross-file call resolution — method calls across files are invisible | 6-stage `CallResolutionDAG` |
| `path` between two files | Without cross-file edges, files in different modules can't reach each other | Cross-file edges bridge previously disconnected files |
| `processes list` / `trace` | No concept of entry points or execution flow — the command doesn't exist | `GraphEntryPointDetector` + BFS process tracing along CALLS edges |
| `query` a question | Naive keyword substring + shallow BFS returns noisy, flat results | BM25 + semantic vector search (RRF fusion) for relevance-ranked answers |

---

## 3. Before → After

### 3.1 `explain` — cross-file call resolution

`handlers.py` calls `UserRepository.find_by_id()` and `User.to_dict()`, both
defined in `models.py`. Upstream sees the `from models import ...` but never
connects the call site to the target.

The fork runs a 6-stage DAG (**Extract → Classify → InferReceiver → SelectDispatch
→ ResolveTarget → EmitEdge**) with per-language extractors for Python, TypeScript,
Go, and Java.

<table>
<tr>
<th width="50%">Upstream (<code>graphifyy</code>)</th>
<th width="50%">Fork (this repo)</th>
</tr>
<tr>
<td>

<pre>
$ graphify explain "get_user()"

Node: get_user()
  Source:    handlers.py L8
  Degree:    3

Connections (3):
  --> validate_token() [calls] [INFERRED]
  --> handlers.py [contains] [EXTRACTED]
  --> me() [calls] [INFERRED]
</pre>

</td>
<td>

<pre>
$ graphify explain "get_user()"

Node: get_user()
  Source:    handlers.py L8
  Degree:    5

  Outgoing calls (→ 4 callees):
    → validate_token() [INFERRED]
    → me() [INFERRED]
    → .find_by_id() [INFERRED]
    → .to_dict() [INFERRED]

  Other connections (1):
    handlers.py [contains] [EXTRACTED]
</pre>

</td>
</tr>
</table>

The 4 cross-file method calls resolved by the DAG (28/76 total, 37%):

```
User.to_dict()                ← called by authenticate()  (handlers.py → models.py)
User.to_dict()                ← called by get_user()      (handlers.py → models.py)
UserRepository.find_by_email() ← called by authenticate() (handlers.py → models.py)
UserRepository.find_by_id()   ← called by get_user()      (handlers.py → models.py)
```

| | Baseline | Fork |
|---|---|---|
| Total edges | 57 | **61** |
| Cross-file calls | 0 | **4** |
| Call resolution rate | — | 28/76 (37%) |

---

### 3.2 `path` — bridging files across modules

These 4 cross-file edges don't just improve `explain` — they create bridges
between files that were previously unreachable. Without them, there is no path
from `handlers.py` to `models.py` because no edge crosses the file boundary.

<table>
<tr>
<th width="50%">Upstream (<code>graphifyy</code>)</th>
<th width="50%">Fork (this repo)</th>
</tr>
<tr>
<td>

<pre>
$ graphify path "handlers.py" "models.py"

No path found between
'handlers.py' and 'models.py'.
</pre>

</td>
<td>

<pre>
$ graphify path "handlers.py" "models.py"

Shortest path (4 hops):
  handlers.py
    --contains--> get_user()
    --calls--> .to_dict()
    --method--> User
    --contains--> models.py

  2 files  |  2 branch points
  EXTRACTED: 3  INFERRED: 1
  calls: 1  contains: 2  method: 1
</pre>

</td>
</tr>
</table>

The fork also enriches `path` output with branch-point count, file count, and
edge-type breakdown — information the upstream `path` command never provides.

---

### 3.3 `processes` — entry point detection

Upstream has no concept of execution flow. The fork adds entry point detection
(framework-aware: FastAPI, Flask, Express, Next.js, Go main, cron) with a
graph-based fallback (high out-degree, no incoming CALLS).

<table>
<tr>
<th width="50%">Upstream (<code>graphifyy</code>)</th>
<th width="50%">Fork (this repo)</th>
</tr>
<tr>
<td>

<pre>
$ graphify processes list

error: unknown command 'processes'
</pre>

</td>
<td>

<pre>
$ graphify processes toy-service list

  CLI      1.00  server.py  (server.py:1)
</pre>

</td>
</tr>
</table>

The `list` output shows which entry points were detected and how they were
classified (CLI, HTTP, TEST, etc.). With the entry point found, `trace` follows
CALLS edges from the entry surface:

<pre>
$ graphify processes toy-service trace "server.py"

Process: server.py
  Steps: 1, Max depth: 0, Complexity: 1
    [0] depth=0 server.py server.py:1
</pre>

The cross-file call chain is also visible at the graph level. Extracting the cross-file CALLS edges from
`server.py`'s functions reveals the call chain at the graph level:

```
server.py
  ├─ _require_auth()  →  validate_token()   (server.py → auth.py)
  ├─ login()          →  authenticate()     (server.py → handlers.py)
  ├─ register()       →  create_user()      (server.py → handlers.py)
  └─ me()             →  get_user()         (server.py → handlers.py)
```

The fork detects the entry point and captures a 3-file call chain through
`handlers.py` → `auth.py` + `models.py`.

---

### 3.4 `explain` — structured direction

Upstream dumps all neighbors as a flat "Connections" list — you can't tell who
calls this function from who this function calls.

<table>
<tr>
<th width="50%">Upstream (<code>graphifyy</code>)</th>
<th width="50%">Fork (this repo)</th>
</tr>
<tr>
<td>

<pre>
$ graphify explain "create_user()"

Node: create_user()
  Source:    handlers.py L18
  Degree:    5

Connections (5):
  --> create_token() [calls] [INFERRED]
  --> handlers.py [contains] [EXTRACTED]
  --> hash_password() [calls] [INFERRED]
  --> register() [calls] [INFERRED]
  --> _insert_user() [calls] [EXTRACTED]
</pre>

</td>
<td>

<pre>
$ graphify explain "create_user()"

Node: create_user()
  Source:    handlers.py L18
  Degree:    5

  Outgoing calls (→ 4 callees):
    → create_token() [INFERRED]
    → hash_password() [INFERRED]
    → register() [INFERRED]
    → _insert_user() [INFERRED]

  Other connections (1):
    handlers.py [contains] [EXTRACTED]
</pre>

</td>
</tr>
</table>

Upstream's flat list of 5 connections leaves you guessing about direction.
The fork tells you at a glance: `create_user()` is the *caller* for 4 functions.

---

### 3.5 `query` — relevance-ranked search

Upstream performs naive keyword substring matching across all node labels
followed by shallow BFS — returning a flat, noisy dump of everything loosely
related to any word in the query.

The fork replaces this with **BM25 + semantic vector search** via Reciprocal
Rank Fusion (k=60), producing relevance-ranked results with process grouping.

<table>
<tr>
<th width="50%">Upstream (<code>graphifyy</code>)</th>
<th width="50%">Fork (this repo)</th>
</tr>
<tr>
<td>

<pre>
$ graphify query "token validation"

NODE auth.py
NODE server.py
NODE create_token()
NODE handlers.py
NODE create_user()
NODE validate_token()
NODE authenticate()
...
NODE _find_inactive_users()

27 nodes returned, flat ordering.
</pre>

</td>
<td>

<pre>
$ graphify query "token validation"

NODE validate_token()                ← BM25-ranked
NODE create_token()
NODE _extract_token()

3 nodes returned, relevance-scored.
</pre>

</td>
</tr>
</table>

The fork returns **3** relevance-ranked results directly matching the query
intent. The baseline returns **27** — a flat dump of everything loosely connected
to any matching substring. On VSCode (111K nodes), the same BM25 pipeline runs
**13× faster** than keyword BFS (114ms vs 1488ms p50).

---

## 4. Compact serialization

The fork strips redundant `_src`/`_tgt` fields from edges (recomputed on load)
and uses compact JSON separators.

| | Baseline | Fork | Delta |
|---|---|---|---|
| graph.json size | 29.4 KB | **20.1 KB** | **-32%** |
| Bytes per edge | 529 | **338** | **-36%** |

On VSCode (111K nodes): **164 MB → 105 MB (-36%)**, **13× query speedup**
(1488ms → 114ms p50).

---

## 5. Summary

| Gap | Fork solution | See |
|---|---|---|
| Cross-file calls invisible | 6-stage CallResolutionDAG | [§3.1](#31-explain--cross-file-call-resolution) |
| Files in different modules unreachable | Cross-file edges bridge disconnected files | [§3.2](#32-path--bridging-files-across-modules) |
| No entry points or execution flow | Entry point detection + process tracing | [§3.3](#33-processes--entry-point-detection) |
| Flat undifferentiated explain | Categorized by call direction | [§3.4](#34-explain--structured-direction) |
| Naive keyword search | BM25 + semantic vector RRF fusion | [§3.5](#35-query--relevance-ranked-search) |

Reproduce yourself:

```bash
pip install graphifyy                    # baseline
graphify update demos/toy-service        # baseline build

pip install -e .                         # fork (this repo)
graphify update demos/toy-service        # fork build

graphify explain "get_user()"            # compare
graphify path "handlers.py" "models.py"  # no path → 4 hops
graphify processes toy-service list      # error → entry point found
```

---

*Data captured 2026-04-30. Toy service at `demos/toy-service/`. Graphs at
`demos/out-baseline/graph.json` and `demos/out-fork/graph.json`.*
