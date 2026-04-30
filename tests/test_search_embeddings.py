import pytest
from graphify.search.embeddings import (
    EMBEDDING_DIM,
    compute_cosine,
    generate_embedding,
    generate_embeddings,
    node_embedding_text,
    save_embeddings,
    load_embeddings,
    search_by_embedding,
)


def test_generate_embedding_deterministic():
    emb1 = generate_embedding("def authenticate(user: User) -> bool")
    emb2 = generate_embedding("def authenticate(user: User) -> bool")
    assert emb1 == emb2


def test_generate_embedding_different_texts():
    emb1 = generate_embedding("def authenticate(user: User) -> bool")
    emb2 = generate_embedding("def validate(email: str) -> bool")
    assert emb1 != emb2


def test_generate_embedding_shape():
    emb = generate_embedding("def foo()")
    assert len(emb) == EMBEDDING_DIM


def test_generate_embedding_normalized():
    emb = generate_embedding("def foo()")
    import math
    norm = math.sqrt(sum(v * v for v in emb))
    assert abs(norm - 1.0) < 1e-9


def test_cosine_similarity_identical():
    emb = generate_embedding("def authenticate(user: User) -> bool")
    sim = compute_cosine(emb, emb)
    assert abs(sim - 1.0) < 1e-9


def test_cosine_similarity_orthogonal_approx():
    emb1 = generate_embedding("aaaaaaaaaaaaaaaaaaaaaaaa")
    emb2 = generate_embedding("bbbbbbbbbbbbbbbbbbbbbbbb")
    sim = compute_cosine(emb1, emb2)
    assert sim < 0.5


def test_cosine_similarity_range():
    emb1 = generate_embedding("def auth()")
    emb2 = generate_embedding("def login()")
    sim = compute_cosine(emb1, emb2)
    assert -1.0 <= sim <= 1.0


def test_node_embedding_text_with_signature():
    node = {"label": "validateEmail", "signature": "validateEmail(email: string): boolean",
            "docstring": "Validates email format"}
    text = node_embedding_text(node)
    assert "validateEmail" in text
    assert "validateEmail(email: string): boolean" in text
    assert "Validates email format" in text


def test_node_embedding_text_minimal():
    node = {"label": "MyClass"}
    text = node_embedding_text(node)
    assert text == "MyClass"


def test_generate_embeddings():
    import networkx as nx
    G = nx.Graph()
    G.add_node("n1", label="validateEmail", node_type="FUNCTION", signature="validateEmail(email: string)")
    G.add_node("n2", label="UserService", node_type="CLASS", docstring="User service")
    G.add_node("n3", label="utils.py", node_type="FILE", source_file="utils.py")
    G.add_node("n4", label="config.png", file_type="image", label_text="config")
    G.add_node("n5", label="concept", node_type="CONCEPT", docstring="some concept")

    embeddings = generate_embeddings(G)
    assert "n1" in embeddings
    assert "n2" in embeddings
    assert "n3" not in embeddings
    assert "n4" not in embeddings
    assert "n5" not in embeddings


def test_search_by_embedding():
    import networkx as nx
    G = nx.Graph()
    G.add_node("n1", label="validateEmail", node_type="FUNCTION",
               signature="validateEmail(email: string): boolean",
               docstring="Validates email format using regex")
    G.add_node("n2", label="UserService", node_type="CLASS",
               docstring="User service with CRUD operations for user management")
    G.add_node("n3", label="renderLoginForm", node_type="FUNCTION",
               docstring="Renders the login form HTML component with email and password fields")

    embeddings = generate_embeddings(G)
    results = search_by_embedding("email validation", embeddings, top_k=2)
    assert len(results) == 2
    assert results[0][0] == "n1"


def test_search_by_embedding_empty():
    results = search_by_embedding("anything", {}, top_k=5)
    assert results == []


def test_save_and_load_embeddings(tmp_path):
    embeddings = {
        "node_1": [0.1, 0.2, 0.3],
        "node_2": [0.4, 0.5, 0.6],
    }
    save_embeddings(embeddings, tmp_path)
    loaded = load_embeddings(tmp_path)
    assert loaded == embeddings


def test_save_and_load_empty_embeddings(tmp_path):
    save_embeddings({}, tmp_path)
    loaded = load_embeddings(tmp_path)
    assert loaded == {}


def test_load_embeddings_nonexistent_dir():
    from pathlib import Path
    loaded = load_embeddings(Path("/nonexistent/path"))
    assert loaded == {}


def test_cosine_different_lengths():
    with pytest.raises(ValueError):
        compute_cosine([1.0, 2.0], [1.0, 2.0, 3.0])


def test_cosine_zero_vectors():
    sim = compute_cosine([0.0, 0.0], [0.0, 0.0])
    assert sim == 0.0


def test_l2_normalize_zero_vector():
    from graphify.search.embeddings import _l2_normalize
    result = _l2_normalize([0.0, 0.0, 0.0])
    assert result == [0.0, 0.0, 0.0]


def test_pseudorandom_vector_pure_python(monkeypatch):
    import graphify.search.embeddings as emb
    monkeypatch.setattr(emb, "_import_numpy", lambda: None)
    from graphify.search.embeddings import _pseudorandom_vector
    v = _pseudorandom_vector(42, 10)
    assert len(v) == 10


def test_compute_node_hash():
    import networkx as nx
    from graphify.search.embeddings import compute_node_hash
    G = nx.Graph()
    G.add_node("n1", label="testFunc", signature="testFunc(a: int): bool")
    h = compute_node_hash(G, "n1")
    assert len(h) == 64
    assert h == compute_node_hash(G, "n1")
