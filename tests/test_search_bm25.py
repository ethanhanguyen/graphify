import pytest
from graphify.search.bm25 import BM25Index


def test_bm25_add_and_search():
    idx = BM25Index()
    idx.add_document("doc1", "authentication login handler")
    idx.add_document("doc2", "user registration form validation")
    idx.add_document("doc3", "database connection pool manager")

    results = idx.search("authentication")
    assert len(results) > 0
    assert results[0][0] == "doc1"


def test_bm25_multiple_term_search():
    idx = BM25Index()
    idx.add_document("doc1", "validate email address input")
    idx.add_document("doc2", "validate password strength")
    idx.add_document("doc3", "render login page html")

    results = idx.search("validate email")
    assert len(results) > 0
    assert results[0][0] == "doc1"


def test_bm25_empty_index():
    idx = BM25Index()
    results = idx.search("anything")
    assert results == []


def test_bm25_remove_document():
    idx = BM25Index()
    idx.add_document("doc1", "auth login handler")
    idx.add_document("doc2", "user form validation")
    idx.remove_document("doc1")

    results = idx.search("auth")
    assert len(results) == 0


def test_bm25_remove_nonexistent_document():
    idx = BM25Index()
    idx.add_document("doc1", "auth login handler")
    idx.remove_document("nonexistent")
    results = idx.search("auth")
    assert len(results) == 1


def test_bm25_multiple_docs_ranking():
    idx = BM25Index()
    idx.add_document("doc1", "user authentication login handler service")
    idx.add_document("doc2", "authentication middleware token verification")
    idx.add_document("doc3", "login form component render")

    results = idx.search("authentication login")
    assert len(results) >= 2
    assert results[0][0] in ("doc1", "doc2")


def test_bm25_top_k_limits_results():
    idx = BM25Index()
    for i in range(30):
        idx.add_document(f"doc{i}", "test authentication service handler")

    results = idx.search("authentication", top_k=5)
    assert len(results) == 5


def test_bm25_default_top_k():
    idx = BM25Index()
    for i in range(30):
        idx.add_document(f"doc{i}", "test authentication service handler")

    results = idx.search("authentication")
    assert len(results) == 20


def test_bm25_index_from_graph():
    import networkx as nx
    G = nx.Graph()
    G.add_node("n1", label="validateEmail", signature="validateEmail(email: string): boolean",
                docstring="Validates email format", source_file="src/auth/validators.ts",
                node_type="FUNCTION")
    G.add_node("n2", label="UserService", signature="",
                docstring="User service with CRUD operations", source_file="src/users/service.py",
                node_type="CLASS")
    G.add_node("n3", label="renderLoginForm", signature="",
                docstring="Renders the login form component", source_file="src/ui/LoginForm.tsx",
                node_type="FUNCTION")

    idx = BM25Index()
    idx.index_from_graph(G)

    results = idx.search("validate email")
    assert len(results) > 0
    assert results[0][0] == "n1"


def test_bm25_empty_graph():
    import networkx as nx
    G = nx.Graph()
    idx = BM25Index()
    idx.index_from_graph(G)
    assert idx.total_docs == 0
    assert idx.search("test") == []


def test_bm25_avg_doc_length():
    idx = BM25Index()
    idx.add_document("doc1", "short text")
    idx.add_document("doc2", "this is a much longer document with many more tokens in it")
    assert idx.avg_doc_length > 0


def test_bm25_doc_count_per_term():
    idx = BM25Index()
    idx.add_document("doc1", "auth login")
    idx.add_document("doc2", "auth token login")
    assert idx.doc_count_per_term["auth"] == 2
    assert idx.doc_count_per_term["token"] == 1
