"""
Requirement Traceability Engine (RTE) — Demo Verification Script.
Evaluates the 20-story sprint backlog against real-world sample code (test_trace.py).
"""

import sys
import time
from pathlib import Path

# Setup paths
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "backend"))
sys.path.insert(0, str(repo_root / "ml-engine" / "src"))

from app.api.trace import _load_default_stories, trace_file
from app.schemas import FileTraceRequest
from app.parsers.python_ast import parse_python_file

def main():
    print("=" * 75)
    print("      Requirement Traceability Engine (RTE) - Sprint Backlog Demo")
    print("=" * 75)

    # 1. Load Backlog Stories
    stories = _load_default_stories()
    print(f"\n[*] Active Sprint Backlog: {len(stories)} stories loaded (STORY-101 .. STORY-120)")
    for i, s in enumerate(stories, 1):
        print(f"    {i:2d}. [{s.story_id}] {s.user_story[:68]}...")

    # 2. Locate target code file
    target_file = Path(r"c:\Users\DINUWA\Desktop\Reserach resources\TEsting\test_trace.py")
    if not target_file.exists():
        target_file = repo_root / "benchmarks" / "sample_code.py"
        print(f"\n[!] Notice: External path not found, using fallback: {target_file}")
    else:
        print(f"\n[*] Target Source Code: {target_file}")

    if target_file.exists():
        content = target_file.read_text(encoding="utf-8")
        parsed_funcs = parse_python_file(target_file)
        print(f"[*] AST Parsed Symbols ({len(parsed_funcs)} detected):")
        for f in parsed_funcs:
            test_tag = " [TEST FIXTURE]" if getattr(f, "kind", "") == "test" else " [CODE]"
            print(f"    - def {f.name}() (lines {f.start_line}-{f.end_line}){test_tag}")

        # 3. Benchmark Real-Time Edge Inference
        t0 = time.perf_counter()
        req = FileTraceRequest(
            file_path=str(target_file),
            file_content=content,
            stories=stories,
            delta_only=False,
        )
        response = trace_file(req)
        initial_ms = (time.perf_counter() - t0) * 1000

        # Warm save run (simulating Ctrl+S in editor with cached backlog vectors)
        t_warm = time.perf_counter()
        warm_response = trace_file(req)
        warm_ms = (time.perf_counter() - t_warm) * 1000

        print(f"\n[*] Edge AST + Semantic Inference Benchmark:")
        print(f"    - Cold Initialization Latency: {initial_ms:.2f} ms")
        print(f"    - Warm Real-Time Save Latency: {warm_ms:.2f} ms (Target budget: <350 ms)")
        print("\n" + "-" * 75)
        print(f"{'Symbol Name':<28} | {'Status':<13} | {'Similarity':<10} | {'Matched Story'}")
        print("-" * 75)

        verified = 0
        missing_test = 0
        candidate = 0
        orphan = 0

        for sym in response.functions:
            story_display = sym.matched_story_id or "-"
            sim_display = f"{sym.similarity * 100:.1f}%" if sym.similarity > 0 else "0.0%"
            print(f"{sym.name:<28} | {sym.status:<13} | {sim_display:<10} | {story_display}")
            if sym.status == "VERIFIED":
                verified += 1
            elif sym.status == "MISSING_TEST":
                missing_test += 1
            elif sym.status == "CANDIDATE":
                candidate += 1
            elif sym.status == "ORPHAN":
                orphan += 1

        print("-" * 75)
        print(f"Status Breakdown: Verified={verified} | Missing Test={missing_test} | Candidate={candidate} | Orphan={orphan}")
        print(f"Server Latency: {response.latency_ms:.2f} ms | Model: {response.model_version}")
        print("=" * 75)

if __name__ == "__main__":
    main()
