import json
from pathlib import Path


def _make_search_judgments_file(tmp_path):
    judgments = {
        "authentication login handler": ["n1", "n2"],
        "user database operations": ["n3", "n4"],
        "form validation component": ["n5"],
        "email sending service": ["n6"],
        "file upload handler": ["n7"],
        "payment processing": ["n8"],
        "cache invalidation strategy": ["n9"],
    }
    p = tmp_path / "search_judgments.json"
    p.write_text(json.dumps(judgments), encoding="utf-8")
    return p


def _make_search_graph():
    import networkx as nx
    G = nx.Graph()
    G.add_node("n1", label="authenticateUser", node_type="FUNCTION",
               signature="authenticateUser(login: str, password: str): User",
               docstring="Authenticates a user with login and password", source_file="src/auth/login.py")
    G.add_node("n2", label="loginHandler", node_type="FUNCTION",
               signature="loginHandler(req: Request): Response",
               docstring="Handles login POST requests with authentication", source_file="src/auth/login.py")
    G.add_node("n3", label="UserRepository", node_type="CLASS",
               signature="class UserRepository",
               docstring="Repository for user database CRUD operations", source_file="src/db/users.py")
    G.add_node("n4", label="findUserById", node_type="FUNCTION",
               signature="findUserById(id: str): User | None",
               docstring="Finds a user in the database by ID", source_file="src/db/users.py")
    G.add_node("n5", label="validateForm", node_type="FUNCTION",
               signature="validateForm(data: FormData): ValidationResult",
               docstring="Validates form input data", source_file="src/components/Form.tsx")
    G.add_node("n6", label="sendEmail", node_type="FUNCTION",
               signature="sendEmail(to: str, subject: str, body: str): void",
               docstring="Sends an email via SMTP service", source_file="src/services/email.ts")
    G.add_node("n7", label="uploadFile", node_type="FUNCTION",
               signature="uploadFile(file: File): string",
               docstring="Handles file upload to storage", source_file="src/services/upload.ts")
    G.add_node("n8", label="processPayment", node_type="FUNCTION",
               signature="processPayment(amount: number, source: PaymentMethod): Transaction",
               docstring="Processes payment via payment gateway", source_file="src/services/payment.ts")
    G.add_node("n9", label="invalidateCache", node_type="FUNCTION",
               signature="invalidateCache(key: string): void",
               docstring="Invalidates cache entry by key", source_file="src/services/cache.ts")
    G.add_node("n_unique_1", label="someRandomHelper", node_type="FUNCTION",
               signature="someRandomHelper(x: number): number",
               docstring="A random utility function", source_file="src/utils/random.ts")
    G.add_node("n_unique_2", label="anotherRandomThing", node_type="FUNCTION",
               signature="anotherRandomThing(): void",
               docstring="Another random function", source_file="src/utils/misc.ts")
    return G


def test_search_judgments_file_created(tmp_path):
    p = _make_search_judgments_file(tmp_path)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert len(data) >= 5
    assert "authentication login handler" in data


def test_benchmark_search_latency_returns_metrics():
    from graphify.benchmark import benchmark_search_latency
    G = _make_search_graph()
    from graphify.search.bm25 import BM25Index
    bm25 = BM25Index()
    bm25.index_from_graph(G)
    from graphify.search.embeddings import generate_embeddings
    embeddings = generate_embeddings(G)

    result = benchmark_search_latency(G, bm25, embeddings, num_queries=5, seed=42)
    assert "bm25_ms" in result
    assert "semantic_ms" in result
    assert "hybrid_ms" in result
    assert "rrf_overhead_ms" in result


def test_benchmark_search_overlap_returns_metrics():
    from graphify.benchmark import benchmark_search_overlap
    G = _make_search_graph()
    from graphify.search.bm25 import BM25Index
    bm25 = BM25Index()
    bm25.index_from_graph(G)
    from graphify.search.embeddings import generate_embeddings
    embeddings = generate_embeddings(G)

    result = benchmark_search_overlap(G, bm25, embeddings, num_queries=5, seed=42, k=20)
    assert "overlap_at_5" in result
    assert "overlap_at_10" in result
    assert "overlap_at_20" in result
    assert "rrf_boost_pct" in result


def test_benchmark_search_relevance_returns_metrics():
    from graphify.benchmark import benchmark_search_relevance
    G = _make_search_graph()
    from graphify.search.bm25 import BM25Index
    bm25 = BM25Index()
    bm25.index_from_graph(G)
    from graphify.search.embeddings import generate_embeddings
    embeddings = generate_embeddings(G)

    judgments = {
        "authentication login handler": {"n1", "n2"},
        "user database operations": {"n3", "n4"},
    }

    result = benchmark_search_relevance(G, bm25, embeddings, judgments, ks=[5, 10])
    for method in ("bm25", "semantic", "hybrid"):
        assert method in result
        for k_str in ("5", "10"):
            assert k_str in result[method]
            metrics = result[method][k_str]
            assert "precision" in metrics
            assert "recall" in metrics
            assert "ndcg" in metrics


def test_load_relevance_judgments(tmp_path):
    from graphify.benchmark import load_relevance_judgments
    p = _make_search_judgments_file(tmp_path)
    judgments = load_relevance_judgments(str(p))
    assert len(judgments) == 7
    assert "authentication login handler" in judgments
    assert judgments["authentication login handler"] == {"n1", "n2"}


def test_hybrid_search_pipeline():
    from graphify.search.hybrid import hybrid_search
    from graphify.search.bm25 import BM25Index
    from graphify.search.embeddings import generate_embeddings

    G = _make_search_graph()
    bm25 = BM25Index()
    bm25.index_from_graph(G)
    embeddings = generate_embeddings(G)

    results = hybrid_search(G, "authentication login", bm25, embeddings, processes=None, top_k=10)
    assert len(results) > 0
    assert len(results) <= 10
    assert results[0][0] in ("n1", "n2")


def test_hybrid_search_empty_graph():
    from graphify.search.hybrid import hybrid_search
    from graphify.search.bm25 import BM25Index

    import networkx as nx
    G = nx.Graph()
    bm25 = BM25Index()
    bm25.index_from_graph(G)
    embeddings = {}

    results = hybrid_search(G, "anything", bm25, embeddings)
    assert results == []


def test_benchmark_search_latency_empty_index():
    from graphify.benchmark import benchmark_search_latency

    import networkx as nx
    G = nx.Graph()
    from graphify.search.bm25 import BM25Index
    bm25 = BM25Index()
    bm25.index_from_graph(G)
    embeddings = {}

    result = benchmark_search_latency(G, bm25, embeddings, num_queries=0, seed=42)
    assert result["bm25_ms"]["avg"] == 0
    assert result["semantic_ms"]["avg"] == 0
    assert result["hybrid_ms"]["avg"] == 0


def test_benchmark_search_overlap_empty_index():
    from graphify.benchmark import benchmark_search_overlap

    import networkx as nx
    G = nx.Graph()
    from graphify.search.bm25 import BM25Index
    bm25 = BM25Index()
    bm25.index_from_graph(G)
    embeddings = {}

    result = benchmark_search_overlap(G, bm25, embeddings, num_queries=0, seed=42, k=20)
    assert result["overlap_at_5"] == 0.0
    assert result["overlap_at_10"] == 0.0


def test_benchmark_search_relevance_empty():
    from graphify.benchmark import benchmark_search_relevance

    import networkx as nx
    G = nx.Graph()
    from graphify.search.bm25 import BM25Index
    bm25 = BM25Index()
    bm25.index_from_graph(G)
    embeddings = {}

    result = benchmark_search_relevance(G, bm25, embeddings, {}, ks=[5])
    for method in ("bm25", "semantic", "hybrid"):
        assert result[method]["5"]["precision"] == 0.0
        assert result[method]["5"]["recall"] == 0.0
