"""Unit tests and benchmarks for Milestone 1: Local INT8 ONNX Inference."""

from __future__ import annotations

import numpy as np
import pytest
from trace_ml.onnx_inference import (
    ONNXEmbedder,
    benchmark_cpu_inference,
    calculate_cosine_similarity,
    get_embedder,
)


def test_embedder_initialization():
    """Verify ONNX embedder singleton initialization and session configuration."""
    embedder = get_embedder()
    assert embedder is not None
    assert embedder.session is not None
    assert embedder.tokenizer is not None


def test_embedding_shape_and_normalization():
    """Verify single and batch embeddings are of dimension 384 and unit normalized (L2=1.0)."""
    embedder = get_embedder()
    texts = [
        "User Story: User can log in with username and password.",
        "def authenticate_user(username: str, password_hash: str) -> bool: return verify_hash(username, password_hash)",
    ]
    embeddings = embedder.embed(texts)
    assert isinstance(embeddings, np.ndarray)
    assert embeddings.shape == (2, 384)

    # Check L2 normalization
    norms = np.linalg.norm(embeddings, axis=1)
    np.testing.assert_allclose(norms, [1.0, 1.0], atol=1e-4)


def test_single_embedding():
    """Verify embed_single helper returns 1D vector."""
    embedder = get_embedder()
    vec = embedder.embed_single("def test_login_success(): assert login('admin', 'pass') is True")
    assert vec.ndim == 1
    assert vec.shape == (384,)
    assert abs(np.linalg.norm(vec) - 1.0) < 1e-4


def test_semantic_similarity_discrimination():
    """Verify semantic discrimination: related code has higher similarity than unrelated code."""
    embedder = get_embedder()
    story = "As a user, I want to reset my password using an email verification token."

    # Matching function
    func_match = (
        "def reset_password(token: str, new_password: str) -> bool:\n"
        "    \"\"\"Validate reset token sent via email and update password.\"\"\"\n"
        "    return password_service.reset_with_token(token, new_password)"
    )

    # Unrelated function
    func_unrelated = (
        "def render_chart_svg(width: int, height: int, data_points: list) -> str:\n"
        "    \"\"\"Render dynamic SVG bar chart graphic.\"\"\"\n"
        "    return f'<svg width=\"{width}\" height=\"{height}\"></svg>'"
    )

    story_vec = embedder.embed_single(story)
    match_vec = embedder.embed_single(func_match)
    unrelated_vec = embedder.embed_single(func_unrelated)

    sim_match = calculate_cosine_similarity(story_vec, match_vec)
    sim_unrelated = calculate_cosine_similarity(story_vec, unrelated_vec)

    assert sim_match > sim_unrelated
    assert sim_match > 0.55
    assert sim_unrelated < 0.20


def test_cosine_similarity_edge_cases():
    """Verify cosine similarity bounds and zero vector handling."""
    zero_vec = np.zeros(384)
    ones_vec = np.ones(384)
    assert calculate_cosine_similarity(zero_vec, ones_vec) == 0.0

    # Identical vectors should have similarity 1.0
    embedder = get_embedder()
    v1 = embedder.embed_single("Traceability engine test")
    assert abs(calculate_cosine_similarity(v1, v1) - 1.0) < 1e-4


def test_cpu_latency_benchmark_under_50ms():
    """Milestone 1 strict constraint: CPU inference latency must be < 50ms."""
    results = benchmark_cpu_inference(num_iterations=25, max_budget_ms=50.0)
    assert results["passed"] == 1.0, f"P95 latency {results['p95_ms']:.2f}ms exceeds 50ms budget!"
    assert results["mean_ms"] < 50.0
