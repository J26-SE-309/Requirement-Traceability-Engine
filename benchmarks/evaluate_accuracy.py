"""Evaluates local INT8 ONNX SBERT model on Deep-SE benchmark dataset."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import sys
import time
from typing import Any, Dict

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
ML_ENGINE_SRC = REPO_ROOT / "ml-engine" / "src"
BACKEND_SRC = REPO_ROOT / "backend"

for p in [ML_ENGINE_SRC, BACKEND_SRC]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from trace_ml.onnx_inference import calculate_cosine_similarity, get_embedder

logger = logging.getLogger(__name__)

BENCHMARKS_DIR = Path(__file__).resolve().parent
GROUND_TRUTH_FILE = BENCHMARKS_DIR / "datasets" / "deep_se" / "ground_truth.json"


def load_ground_truth(dataset_path: Path = GROUND_TRUTH_FILE) -> list[dict[str, Any]]:
    """Load ground truth pairs or generate them if file does not exist."""
    if not dataset_path.exists():
        from benchmarks.datasets.fetch_deep_se import fetch_or_generate_dataset
        return fetch_or_generate_dataset(dataset_path)

    with dataset_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def evaluate_model(
    pairs: list[dict[str, Any]],
    thresholds: list[float] = [0.65, 0.80],
) -> dict[str, Any]:
    """Run evaluation on benchmark pairs with local INT8 ONNX SBERT model."""
    embedder = get_embedder()

    latencies_ms: list[float] = []
    similarities: list[float] = []
    ground_truth: list[bool] = []

    logger.info("Running INT8 ONNX CPU inference across %d benchmark pairs...", len(pairs))

    for item in pairs:
        query_text = (
            f"User Story: {item['user_story']}. "
            f"Acceptance Criteria: {' '.join(item['acceptance_criteria'])}"
        )
        code_text = item["code_artifact"]
        gt = bool(item["is_ground_truth_link"])
        ground_truth.append(gt)

        
        t0 = time.perf_counter()
        query_vec = embedder.embed_single(query_text)
        code_vec = embedder.embed_single(code_text)
        sim = calculate_cosine_similarity(query_vec, code_vec)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        latencies_ms.append(elapsed_ms)
        similarities.append(sim)

   
    latency_summary = {
        "mean_ms": float(np.mean(latencies_ms)),
        "p50_ms": float(np.percentile(latencies_ms, 50)),
        "p95_ms": float(np.percentile(latencies_ms, 95)),
        "min_ms": float(np.min(latencies_ms)),
        "max_ms": float(np.max(latencies_ms)),
    }

    
    threshold_results: dict[str, dict[str, Any]] = {}

    for thresh in thresholds:
        tp = fp = fn = tn = 0
        for sim, gt in zip(similarities, ground_truth):
            pred = (sim >= thresh)
            if pred and gt:
                tp += 1
            elif pred and not gt:
                fp += 1
            elif not pred and gt:
                fn += 1
            else:
                tn += 1

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        accuracy = (tp + tn) / len(ground_truth) if ground_truth else 0.0

        key = f"threshold_{thresh:.2f}"
        threshold_results[key] = {
            "threshold": thresh,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "accuracy": round(accuracy, 4),
        }

    return {
        "total_pairs": len(pairs),
        "latency": latency_summary,
        "metrics_by_threshold": threshold_results,
    }


def print_evaluation_report(results: dict[str, Any]) -> None:
    """Print clean ASCII evaluation tables."""
    lat = results["latency"]
    print("\n" + "=" * 78)
    print("      REQUIREMENT TRACEABILITY ENGINE: INT8 ONNX SBERT BENCHMARK REPORT      ")
    print("=" * 78)
    print(f"Total Evaluated Pairs: {results['total_pairs']}")
    print("-" * 78)
    print("CPU INFERENCE LATENCY BREAKDOWN (per story-to-code pair):")
    print(f"  • Mean Latency:  {lat['mean_ms']:.2f} ms")
    print(f"  • Median (P50):  {lat['p50_ms']:.2f} ms")
    print(f"  • P95 Latency:   {lat['p95_ms']:.2f} ms")
    print(f"  • Min / Max:     {lat['min_ms']:.2f} ms / {lat['max_ms']:.2f} ms")
    print("-" * 78)
    print(f"{'Threshold':<12} | {'TP':<4} | {'FP':<4} | {'FN':<4} | {'TN':<4} | {'Precision':<10} | {'Recall':<8} | {'F1-Score':<8} | {'Accuracy':<8}")
    print("-" * 78)

    for k, m in results["metrics_by_threshold"].items():
        print(
            f"{m['threshold']:<12.2f} | "
            f"{m['tp']:<4} | {m['fp']:<4} | {m['fn']:<4} | {m['tn']:<4} | "
            f"{m['precision']:<10.4f} | {m['recall']:<8.4f} | {m['f1']:<8.4f} | {m['accuracy']:<8.4f}"
        )
    print("=" * 78 + "\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    pairs = load_ground_truth()
    results = evaluate_model(pairs, thresholds=[0.65, 0.80])
    print_evaluation_report(results)

    
    try:
        from visualize_benchmark import generate_html_report, generate_pure_svg_charts
        generate_html_report(BENCHMARKS_DIR, results)
        generate_pure_svg_charts(BENCHMARKS_DIR, results)
    except Exception as e:
        logger.debug("Visual export error: %s", e)

   
    if "--no-gui" not in sys.argv:
        print("\n[⚡] Displaying real graphical bar chart window...")
        try:
            from gui_chart import show_real_bar_chart
            show_real_bar_chart(results)
        except Exception as err:
            print(f"[i] GUI window display note: {err}")

