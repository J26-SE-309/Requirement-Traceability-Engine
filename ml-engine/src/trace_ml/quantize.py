"""Model Quantization Pipeline for Requirement Traceability Engine.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from huggingface_hub import hf_hub_download
import onnx
from onnxruntime.quantization import QuantType, quantize_dynamic

logger = logging.getLogger(__name__)

REPO_ID = "sentence-transformers/all-MiniLM-L6-v2"
ML_ENGINE_ROOT = Path(__file__).resolve().parents[2]
WEIGHTS_DIR = ML_ENGINE_ROOT / "weights"
TOKENIZER_DIR = WEIGHTS_DIR / "tokenizer"
QUANTIZED_MODEL_PATH = WEIGHTS_DIR / "model_quantized.onnx"

TOKENIZER_FILES = [
    "tokenizer.json",
    "vocab.txt",
    "tokenizer_config.json",
    "special_tokens_map.json",
]


def download_tokenizer_artifacts(target_dir: Path = TOKENIZER_DIR) -> None:
    """Download tokenizer files from HuggingFace to target directory."""
    target_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading tokenizer artifacts from %s to %s", REPO_ID, target_dir)
    for fname in TOKENIZER_FILES:
        try:
            cached_path = hf_hub_download(repo_id=REPO_ID, filename=fname)
            dest_file = target_dir / fname
            shutil.copyfile(cached_path, dest_file)
            logger.info("Saved tokenizer artifact: %s", dest_file.name)
        except Exception as e:
            logger.warning("Could not download %s: %s", fname, e)


def download_and_quantize(
    weights_dir: Path = WEIGHTS_DIR,
    model_output_path: Path = QUANTIZED_MODEL_PATH,
    clean_intermediate: bool = True,
) -> Path:
    """Download base FP32 ONNX model, dynamically quantize to INT8, and cleanup intermediate files."""
    weights_dir.mkdir(parents=True, exist_ok=True)
    download_tokenizer_artifacts(weights_dir / "tokenizer")

    intermediate_fp32_path = weights_dir / "model_fp32_temp.onnx"

    logger.info("Downloading base FP32 ONNX model from %s...", REPO_ID)
    cached_model = hf_hub_download(repo_id=REPO_ID, filename="onnx/model.onnx")
    shutil.copyfile(cached_model, intermediate_fp32_path)
    logger.info("Base FP32 model copied to: %s (size: %.2f MB)", intermediate_fp32_path, intermediate_fp32_path.stat().st_size / (1024 * 1024))

 
    logger.info("Checking model integrity...")
    model_proto = onnx.load(str(intermediate_fp32_path))
    onnx.checker.check_model(model_proto)

    logger.info("Quantizing model to INT8 (dynamic quantization for CPU)...")
    quantize_dynamic(
        model_input=str(intermediate_fp32_path),
        model_output=str(model_output_path),
        weight_type=QuantType.QInt8,
    )

    quantized_size_mb = model_output_path.stat().st_size / (1024 * 1024)
    logger.info("Quantization complete! Output: %s (size: %.2f MB)", model_output_path, quantized_size_mb)

    if clean_intermediate and intermediate_fp32_path.exists():
        intermediate_fp32_path.unlink()
        logger.info("Cleaned up intermediate FP32 artifact: %s", intermediate_fp32_path.name)

    return model_output_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    download_and_quantize()
