"""Local INT8 ONNX Inference Engine for Sentence Embeddings.

Provides CPU-optimized inference for all-MiniLM-L6-v2 with mean pooling,
L2 unit-norm normalization, cosine similarity computation, and runtime benchmarking.
Zero cloud dependencies, sub-50ms CPU execution budget.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Sequence, Union

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

logger = logging.getLogger(__name__)

ML_ENGINE_ROOT = Path(__file__).resolve().parents[2]
WEIGHTS_DIR = ML_ENGINE_ROOT / "weights"
QUANTIZED_MODEL_PATH = WEIGHTS_DIR / "model_quantized.onnx"
TOKENIZER_DIR = WEIGHTS_DIR / "tokenizer"


class ONNXEmbedder:
    """High-performance CPU embedding runner using INT8 quantized ONNX MiniLM model."""

    _instance: ONNXEmbedder | None = None

    def __init__(
        self,
        model_path: Path | str = QUANTIZED_MODEL_PATH,
        tokenizer_path: Path | str = TOKENIZER_DIR / "tokenizer.json",
        max_length: int = 256,
    ) -> None:
        self.model_path = Path(model_path)
        self.tokenizer_path = Path(tokenizer_path)
        self.max_length = max_length

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Quantized model not found at {self.model_path}. "
                "Run `python -m trace_ml.quantize` to build it."
            )
        if not self.tokenizer_path.exists():
            raise FileNotFoundError(
                f"Tokenizer artifacts not found at {self.tokenizer_path}. "
                "Run `python -m trace_ml.quantize` to fetch tokenizer artifacts."
            )

        # Initialize fast Rust tokenizer with dynamic padding
        self.tokenizer = Tokenizer.from_file(str(self.tokenizer_path))
        self.tokenizer.enable_truncation(max_length=self.max_length)
        self.tokenizer.enable_padding(length=None)

        # Configure ONNX Runtime Session targeting CPUExecutionProvider
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        # Limit intra-op threads to avoid saturating CPU
        num_threads = max(1, min(4, (os.cpu_count() or 4) // 2))
        opts.intra_op_num_threads = num_threads
        opts.inter_op_num_threads = 1

        self.session = ort.InferenceSession(
            str(self.model_path),
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )

        input_names = [inp.name for inp in self.session.get_inputs()]
        self.has_token_type_ids = "token_type_ids" in input_names

        # Warm up session with a few forward passes
        self._warmup()

    def _warmup(self) -> None:
        """Run dummy forward passes to warm up JIT optimizations and caches."""
        try:
            for _ in range(3):
                self.embed("Warmup sentence for requirement traceability engine.")
        except Exception as e:
            logger.warning("Warmup failed: %s", e)

    @classmethod
    def get_instance(cls) -> ONNXEmbedder:
        """Singleton accessor for fast in-process sharing across backend requests."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def mean_pooling(token_embeddings: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
        """Compute mean pooling over token embeddings taking attention mask into account.

        Args:
            token_embeddings: Array of shape (batch_size, seq_len, hidden_dim).
            attention_mask: Array of shape (batch_size, seq_len).

        Returns:
            Mean-pooled and L2-normalized array of shape (batch_size, hidden_dim).
        """
        # Expand mask for broadcasting: (batch_size, seq_len, 1)
        input_mask_expanded = np.expand_dims(attention_mask, -1).astype(np.float32)
        sum_embeddings = np.sum(token_embeddings * input_mask_expanded, axis=1)
        sum_mask = np.clip(input_mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
        pooled = sum_embeddings / sum_mask

        # L2 unit-norm normalization
        norm = np.linalg.norm(pooled, ord=2, axis=1, keepdims=True)
        norm = np.clip(norm, a_min=1e-12, a_max=None)
        return pooled / norm

    def embed(self, texts: Union[str, Sequence[str]]) -> np.ndarray:
        """Compute 384-dimensional normalized sentence embeddings for input texts.

        Args:
            texts: Single string or sequence of text strings.

        Returns:
            np.ndarray of shape (N, 384) with L2-normalized float32 vectors.
        """
        is_single = isinstance(texts, str)
        text_list = [texts] if is_single else list(texts)

        if not text_list:
            return np.empty((0, 384), dtype=np.float32)

        # Batch tokenization
        encodings = self.tokenizer.encode_batch(text_list)
        batch_ids = [enc.ids for enc in encodings]
        batch_mask = [enc.attention_mask for enc in encodings]

        ort_inputs = {
            "input_ids": np.array(batch_ids, dtype=np.int64),
            "attention_mask": np.array(batch_mask, dtype=np.int64),
        }
        if self.has_token_type_ids:
            batch_type_ids = [enc.type_ids for enc in encodings]
            ort_inputs["token_type_ids"] = np.array(batch_type_ids, dtype=np.int64)

        ort_outputs = self.session.run(None, ort_inputs)
        token_embeddings = ort_outputs[0]

        normalized_embeddings = self.mean_pooling(token_embeddings, ort_inputs["attention_mask"])
        return normalized_embeddings

    def embed_single(self, text: str) -> np.ndarray:
        """Embed single text string returning 1D array of shape (384,)."""
        embs = self.embed(text)
        return embs[0]


def calculate_cosine_similarity(
    vec_a: np.ndarray | Sequence[float],
    vec_b: np.ndarray | Sequence[float],
) -> float:
    """Calculate cosine similarity between two vectors.

    Values range from -1.0 to 1.0. For L2-normalized vectors this is equivalent to dot product.
    """
    a = np.asarray(vec_a, dtype=np.float32).flatten()
    b = np.asarray(vec_b, dtype=np.float32).flatten()

    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    sim = float(np.dot(a, b) / (norm_a * norm_b))
    return max(-1.0, min(1.0, sim))


def get_embedder() -> ONNXEmbedder:
    """Convenience helper to retrieve singleton ONNXEmbedder."""
    return ONNXEmbedder.get_instance()


def benchmark_cpu_inference(num_iterations: int = 50, max_budget_ms: float = 50.0) -> dict[str, float]:
    """Run CPU inference benchmark verifying latency stays strictly under budget (< 50ms)."""
    embedder = get_embedder()
    test_function = (
        "def test_authenticate_user_valid_jwt():\n"
        "    token = create_test_token(user_id='usr-102', role='admin')\n"
        "    result = authenticate_user(token)\n"
        "    assert result.is_valid is True\n"
        "    assert result.user_id == 'usr-102'"
    )

    latencies: list[float] = []
    for _ in range(num_iterations):
        t0 = time.perf_counter()
        _ = embedder.embed(test_function)
        latencies.append((time.perf_counter() - t0) * 1000)

    mean_ms = float(np.mean(latencies))
    p95_ms = float(np.percentile(latencies, 95))
    min_ms = float(np.min(latencies))
    max_ms = float(np.max(latencies))

    logger.info(
        "CPU Benchmark (%d iters) - Mean: %.2fms, P95: %.2fms, Min: %.2fms, Max: %.2fms (Budget: <%.1fms)",
        num_iterations,
        mean_ms,
        p95_ms,
        min_ms,
        max_ms,
        max_budget_ms,
    )

    passed = p95_ms < max_budget_ms
    return {
        "mean_ms": mean_ms,
        "p95_ms": p95_ms,
        "min_ms": min_ms,
        "max_ms": max_ms,
        "passed": float(passed),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("Testing ONNX Embedder and running CPU latency benchmark...")
    results = benchmark_cpu_inference()
    print("Benchmark Results:", results)
    assert results["passed"] == 1.0, f"Benchmark failed: P95 latency {results['p95_ms']}ms exceeds budget!"
    print("ALL MILESTONE 1 LATENCY CONSTRAINTS PASSED (< 50ms)!")
