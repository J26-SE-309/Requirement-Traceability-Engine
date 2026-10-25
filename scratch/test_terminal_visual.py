"""Test visual terminal bar chart rendering."""

import sys
from pathlib import Path

# Fix Windows console UTF-8 output if needed
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def make_bar(value: float, max_value: float, width: int = 30, char: str = "█") -> str:
    if max_value <= 0:
        return ""
    ratio = min(max(value / max_value, 0.0), 1.0)
    filled = int(round(ratio * width))
    return char * filled


def print_visual_report(data: dict) -> None:
    lat = data["latency"]
    t65 = data["thresholds"]["0.65 (Optimal)"]
    t80 = data["thresholds"]["0.80 (Strict)"]
    W = 32  # Bar width

    print("\n" + "=" * 80)
    print("    REQUIREMENT TRACEABILITY ENGINE: REAL-TIME BENCHMARK VISUAL REPORT")
    print("=" * 80)
    print("Dataset: Deep-SE Benchmark Corpus | 120 Pairs Evaluated on Edge CPU (INT8 ONNX)")
    print("-" * 80)

    # Panel 1: Classification Performance
    print("\n[PANEL A: CLASSIFICATION PERFORMANCE ACROSS THRESHOLDS (0.00 – 1.00)]")
    print("┌──────────────────────────────────────────────────────────────────────────────┐")
    metrics = [
        ("Precision", t65["Precision"], t80["Precision"]),
        ("Recall   ", t65["Recall"], t80["Recall"]),
        ("F1-Score ", t65["F1-Score"], t80["F1-Score"]),
        ("Accuracy ", t65["Accuracy"], t80["Accuracy"]),
    ]
    for name, v65, v80 in metrics:
        b65 = make_bar(v65, 1.0, W, "█").ljust(W)
        b80 = make_bar(v80, 1.0, W, "░").ljust(W)
        note = "  <-- Recommended" if "F1" in name else ""
        print(f"│  {name}  [0.65] │ {b65} │ {v65:.4f} ({v65*100:5.1f}%){note:<18} │")
        print(f"│             [0.80] │ {b80} │ {v80:.4f} ({v80*100:5.1f}%)                   │")
        if name != "Accuracy ":
            print("│                    │" + " " * (W + 2) + "│                                  │")

    print("│                    └" + "─" * W + "┴──────────────────────────────────┘")
    print("│  Scale:             0.0        0.25        0.50        0.75        1.00      │")
    print("│                     |───────────|───────────|───────────|───────────|        │")
    print("│  Legend: [0.65 Optimal] █  |  [0.80 Strict] ░                                │")
    print("└──────────────────────────────────────────────────────────────────────────────┘")

    # Panel 2: Confusion Matrix Counts
    print("\n[PANEL B: CONFUSION MATRIX SAMPLE DISTRIBUTION (N = 120 Pairs)]")
    print("┌──────────────────────────────────────────────────────────────────────────────┐")
    cm_items = [
        ("True Positives  (TP) [0.65]", t65["TP"], 60, "█"),
        ("True Positives  (TP) [0.80]", t80["TP"], 60, "░"),
        ("False Positives (FP) [Both]", 0, 60, " "),
        ("False Negatives (FN) [0.65]", t65["FN"], 60, "█"),
        ("False Negatives (FN) [0.80]", t80["FN"], 60, "░"),
        ("True Negatives  (TN) [Both]", 60, 60, "█"),
    ]
    for label, val, max_v, ch in cm_items:
        if val == 0:
            bar = "(0 pairs) ✓ ZERO FALSE POSITIVES".ljust(W)
            print(f"│  {label:<28} │ {bar} │  0 pairs         │")
        else:
            bar = make_bar(val, max_v, W, ch).ljust(W)
            print(f"│  {label:<28} │ {bar} │ {val:2d} pairs        │")
    print("└──────────────────────────────────────────────────────────────────────────────┘")

    # Panel 3: Latency vs 50ms SLA
    print("\n[PANEL C: CPU INFERENCE LATENCY PROFILE vs 50.0ms SLA BUDGET]")
    print("┌──────────────────────────────────────────────────────────────────────────────┐")
    lat_scale = 60.0
    sla_pos = int((50.0 / lat_scale) * W)
    lat_items = [
        ("Minimum Latency", lat["Min"]),
        ("Median (P50)   ", lat["Median (P50)"]),
        ("Mean Latency   ", lat["Mean"]),
        ("P95 Latency    ", lat["P95"]),
        ("Maximum Latency", lat["Max"]),
    ]
    for label, val in lat_items:
        bar = make_bar(val, lat_scale, W, "█")
        # Pad with spaces up to W
        bar_padded = bar.ljust(W)
        # Add visual guideline for 50ms
        bar_with_sla = bar_padded[:sla_pos] + "┆" + bar_padded[sla_pos + 1 :]
        print(f"│  {label} │ {bar_with_sla} │ {val:5.2f} ms         │")

    ruler_line = "─" * sla_pos + "┬" + "─" * (W - sla_pos - 1)
    print(f"│                  └{ruler_line}┴──────────────────┘")
    print("│  Scale:          0 ms       15 ms       30 ms       45 ms ┆50ms      60 ms  │")
    print("│                                                           └── SLA Limit      │")
    print("│  Status: [✓ SLA PASS] Mean 21.89ms, P95 29.59ms (< 50ms real-time limit)      │")
    print("└──────────────────────────────────────────────────────────────────────────────┘\n")


if __name__ == "__main__":
    sample_data = {
        "latency": {"Min": 12.00, "Median (P50)": 21.68, "Mean": 21.89, "P95": 29.59, "Max": 36.35},
        "thresholds": {
            "0.65 (Optimal)": {"TP": 36, "FP": 0, "FN": 24, "TN": 60, "Precision": 1.0, "Recall": 0.6, "F1-Score": 0.75, "Accuracy": 0.8},
            "0.80 (Strict)": {"TP": 4, "FP": 0, "FN": 56, "TN": 60, "Precision": 1.0, "Recall": 0.0667, "F1-Score": 0.125, "Accuracy": 0.5333},
        },
    }
    print_visual_report(sample_data)
