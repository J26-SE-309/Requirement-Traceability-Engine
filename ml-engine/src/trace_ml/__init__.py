"""Requirement Traceability Engine: research code for datasets, model training and evaluation."""

from trace_ml.onnx_inference import ONNXEmbedder, calculate_cosine_similarity, get_embedder

__version__ = "0.1.0"
__all__ = ["ONNXEmbedder", "get_embedder", "calculate_cosine_similarity", "__version__"]
