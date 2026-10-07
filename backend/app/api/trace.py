"""Traceability API Router and Business Logic.

Implements POST /api/v1/coverage, file tracing, and active viewport Cytoscape graph generation.
Evaluates tripartite status: VERIFIED, MISSING_TEST, CANDIDATE, and ORPHAN.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
import time
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.parsers.python_ast import ParsedFunction, parse_python_file, parse_python_source
from app.schemas import (
    CoverageRequest,
    CoverageResponse,
    CytoscapeGraph,
    FileTraceRequest,
    FileTraceResponse,
    FunctionTraceStatus,
    GraphRequest,
    GraphResponse,
    LinkedArtifact,
    StoryCoverage,
    StoryRef,
)
from app.watcher.git_delta import get_modified_functions

logger = logging.getLogger(__name__)
router = APIRouter(tags=["traceability"])

# Ensure ml-engine/src is on sys.path for direct in-process inference
REPO_ROOT = Path(__file__).resolve().parents[3]
ML_ENGINE_SRC = REPO_ROOT / "ml-engine" / "src"
if str(ML_ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ML_ENGINE_SRC))

try:
    from trace_ml.onnx_inference import calculate_cosine_similarity, get_embedder

    EMBEDDER_AVAILABLE = True
except Exception as e:
    logger.warning("Local ONNX embedder not available: %s", e)
    EMBEDDER_AVAILABLE = False


def _get_workspace_functions(workspace_root: Path) -> list[ParsedFunction]:
    """Scan Python files in workspace root and parse functions."""
    all_functions: list[ParsedFunction] = []
    # Avoid scanning venv or node_modules or .git
    skip_dirs = {".git", ".venv", "venv", "node_modules", ".pytest_cache", "__pycache__", "out", "dist"}

    if not workspace_root.exists():
        return []

    for p in workspace_root.rglob("*.py"):
        parts = set(p.parts)
        if any(skip in parts for skip in skip_dirs):
            continue
        funcs = parse_python_file(p)
        all_functions.extend(funcs)

    return all_functions


def _build_story_text(story: StoryRef) -> str:
    """Format user story and acceptance criteria for semantic embedding."""
    criteria = " ".join(story.acceptance_criteria)
    return f"User Story: {story.user_story}. Acceptance Criteria: {criteria}".strip()


def evaluate_function_against_stories(
    func: ParsedFunction,
    stories: list[StoryRef],
    story_embeddings: dict[str, Any] | None = None,
    available_tests: list[ParsedFunction] | None = None,
) -> tuple[FunctionTraceStatus, StoryRef | None]:
    """Match a function against stories, checking explicit tags and semantic similarity."""
    settings = get_settings()
    high_threshold = settings.confidence_high  # default 0.80
    medium_threshold = settings.confidence_medium  # default 0.65

    # 1. Check explicit # Trace: <STORY-ID> directives
    matched_story: StoryRef | None = None
    if func.explicit_traces:
        for st in stories:
            if st.story_id in func.explicit_traces:
                matched_story = st
                break

    if matched_story:
        # Check test coverage if it's code
        has_linked_test = False
        linked_test_name = None
        if func.kind == "code" and available_tests:
            for t in available_tests:
                if matched_story.story_id in t.explicit_traces and t.has_assertions:
                    has_linked_test = True
                    linked_test_name = t.name
                    break

        status = "VERIFIED" if (func.kind == "test" and func.has_assertions) or has_linked_test else "MISSING_TEST"
        if func.kind == "test":
            status = "VERIFIED" if func.has_assertions else "MISSING_TEST"

        return (
            FunctionTraceStatus(
                name=func.name,
                qualified_name=func.qualified_name,
                start_line=func.start_line,
                end_line=func.end_line,
                kind=func.kind,
                status=status,
                matched_story_id=matched_story.story_id,
                user_story=matched_story.user_story,
                acceptance_criteria=matched_story.acceptance_criteria,
                similarity=1.0,
                source="tag",
                has_test_assertion=has_linked_test or (func.kind == "test" and func.has_assertions),
                linked_test_symbol=linked_test_name,
                rationale=f"Explicitly tagged with '# Trace: {matched_story.story_id}'",
            ),
            matched_story,
        )

    # 2. Semantic matching via ONNX Embeddings
    best_similarity = -1.0
    best_story: StoryRef | None = None

    if EMBEDDER_AVAILABLE and story_embeddings and stories:
        try:
            embedder = get_embedder()
            func_vec = embedder.embed_single(func.semantic_text)

            for st in stories:
                st_vec = story_embeddings.get(st.story_id)
                if st_vec is not None:
                    sim = calculate_cosine_similarity(func_vec, st_vec)
                    if sim > best_similarity:
                        best_similarity = sim
                        best_story = st
        except Exception as e:
            logger.warning("Semantic comparison failed: %s", e)

    best_similarity = max(-1.0, min(1.0, round(best_similarity, 4)))

    # 3. Classify Tripartite Status
    if best_similarity >= high_threshold and best_story is not None:
        # High confidence match
        has_test = False
        linked_test_name = None
        if func.kind == "code" and available_tests:
            for t in available_tests:
                if (best_story.story_id in t.explicit_traces or t.has_assertions) and t.has_assertions:
                    has_test = True
                    linked_test_name = t.name
                    break

        status = "VERIFIED" if has_test or (func.kind == "test" and func.has_assertions) else "MISSING_TEST"
        rationale = f"High confidence semantic match ({best_similarity * 100:.1f}%)"
        return (
            FunctionTraceStatus(
                name=func.name,
                qualified_name=func.qualified_name,
                start_line=func.start_line,
                end_line=func.end_line,
                kind=func.kind,
                status=status,
                matched_story_id=best_story.story_id,
                user_story=best_story.user_story,
                acceptance_criteria=best_story.acceptance_criteria,
                similarity=best_similarity,
                source="semantic",
                has_test_assertion=has_test or (func.kind == "test" and func.has_assertions),
                linked_test_symbol=linked_test_name,
                rationale=rationale,
            ),
            best_story,
        )
    elif best_similarity >= medium_threshold and best_story is not None:
        return (
            FunctionTraceStatus(
                name=func.name,
                qualified_name=func.qualified_name,
                start_line=func.start_line,
                end_line=func.end_line,
                kind=func.kind,
                status="CANDIDATE",
                matched_story_id=best_story.story_id,
                user_story=best_story.user_story,
                acceptance_criteria=best_story.acceptance_criteria,
                similarity=best_similarity,
                source="semantic",
                has_test_assertion=False,
                linked_test_symbol=None,
                rationale=f"Candidate semantic match ({best_similarity * 100:.1f}%), requires verification",
            ),
            best_story,
        )
    else:
        # Orphan
        matched_id = best_story.story_id if best_story and best_similarity > 0 else None
        return (
            FunctionTraceStatus(
                name=func.name,
                qualified_name=func.qualified_name,
                start_line=func.start_line,
                end_line=func.end_line,
                kind=func.kind,
                status="ORPHAN",
                matched_story_id=matched_id,
                similarity=max(0.0, best_similarity),
                source="none",
                has_test_assertion=False,
                rationale=f"No matching requirement (best similarity {max(0.0, best_similarity) * 100:.1f}%)",
            ),
            None,
        )


@router.post("/coverage", response_model=CoverageResponse)
@router.post("/trace/coverage", response_model=CoverageResponse)
def coverage(request: CoverageRequest) -> CoverageResponse:
    """Report how well each story is covered by linked code and tests."""
    settings = get_settings()
    now = datetime.now(timezone.utc)

    # Pre-embed stories
    story_embeddings: dict[str, Any] = {}
    if EMBEDDER_AVAILABLE:
        try:
            embedder = get_embedder()
            for st in request.stories:
                st_text = _build_story_text(st)
                story_embeddings[st.story_id] = embedder.embed_single(st_text)
        except Exception as e:
            logger.warning("Failed embedding stories: %s", e)

    # Collect functions to analyze
    functions_to_analyze: list[ParsedFunction] = []

    if request.target_file:
        p = Path(request.target_file)
        if request.delta_only:
            funcs, _ = get_modified_functions(p, source_code=request.file_content)
            functions_to_analyze = funcs
        else:
            if request.file_content:
                functions_to_analyze = parse_python_source(request.file_content, file_path=str(p))
            else:
                functions_to_analyze = parse_python_file(p)
    elif request.workspace_path:
        w_path = Path(request.workspace_path)
        if w_path.exists():
            for py_file in w_path.rglob("*.py"):
                if not any(skip in py_file.parts for skip in {".git", ".venv", "venv", "node_modules", "__pycache__"}):
                    functions_to_analyze.extend(parse_python_file(py_file))
    else:
        # Default: scan current repository backend and ml-engine files
        for search_dir in [REPO_ROOT / "backend" / "app", REPO_ROOT / "backend" / "tests"]:
            if search_dir.exists():
                for py_file in search_dir.rglob("*.py"):
                    functions_to_analyze.extend(parse_python_file(py_file))

    # Segregate test functions to evaluate assertions
    test_functions = [f for f in functions_to_analyze if f.kind == "test"]

    # Match functions to stories
    story_linked_artifacts: dict[str, list[LinkedArtifact]] = {s.story_id: [] for s in request.stories}
    unlinked_count = 0

    for func in functions_to_analyze:
        trace_status, matched_story = evaluate_function_against_stories(
            func,
            request.stories,
            story_embeddings=story_embeddings,
            available_tests=test_functions,
        )

        if matched_story and trace_status.status in ("VERIFIED", "MISSING_TEST", "CANDIDATE"):
            artifact = LinkedArtifact(
                path=func.file_path or request.target_file or "unknown.py",
                symbol=func.qualified_name,
                kind=func.kind,
                source=trace_status.source if trace_status.source in ("tag", "semantic") else "semantic",
                similarity=trace_status.similarity,
                rationale=trace_status.rationale,
            )
            story_linked_artifacts[matched_story.story_id].append(artifact)
        else:
            unlinked_count += 1

    # Formulate StoryCoverage response
    items: list[StoryCoverage] = []
    for st in request.stories:
        artifacts = story_linked_artifacts.get(st.story_id, [])
        code_artifacts = [a for a in artifacts if a.kind == "code"]
        test_artifacts = [a for a in artifacts if a.kind == "test"]
        has_tests = len(test_artifacts) > 0

        # Calculate coverage percentage
        if code_artifacts and has_tests:
            coverage_pct = 1.0
        elif code_artifacts and not has_tests:
            coverage_pct = 0.5
        elif any(a.similarity >= settings.confidence_medium for a in artifacts):
            coverage_pct = 0.25
        else:
            coverage_pct = 0.0

        # Formulate trace gaps
        gaps: list[str] = []
        if not code_artifacts:
            gaps.append(f"No code implementation linked for story {st.story_id}.")
        elif not has_tests:
            gaps.append(f"Story {st.story_id} has code implementations ({len(code_artifacts)} symbols) but lacks test assertions.")

        items.append(
            StoryCoverage(
                story_id=st.story_id,
                coverage_pct=coverage_pct,
                linked_artifacts=artifacts,
                unlinked_artifact_count=unlinked_count,
                has_linked_tests=has_tests,
                trace_gaps=gaps,
                model_version=settings.model_version if EMBEDDER_AVAILABLE else "stub",
                analysed_at=now,
            )
        )

    return CoverageResponse(items=items)


@router.post("/trace/file", response_model=FileTraceResponse)
def trace_file(request: FileTraceRequest) -> FileTraceResponse:
    """Analyze a single file for CodeLens decorations and viewport filtering."""
    t0 = time.perf_counter()
    settings = get_settings()
    now = datetime.now(timezone.utc)
    p = Path(request.file_path)

    # AST Parse or Delta Parse
    if request.delta_only:
        functions, _ = get_modified_functions(p, source_code=request.file_content)
    else:
        if request.file_content:
            functions = parse_python_source(request.file_content, file_path=str(p))
        else:
            functions = parse_python_file(p)

    # Pre-embed stories
    story_embeddings: dict[str, Any] = {}
    if EMBEDDER_AVAILABLE and request.stories:
        try:
            embedder = get_embedder()
            for st in request.stories:
                st_text = _build_story_text(st)
                story_embeddings[st.story_id] = embedder.embed_single(st_text)
        except Exception as e:
            logger.warning("Story embedding failed: %s", e)

    # Evaluate each function
    test_functions = [f for f in functions if f.kind == "test"]
    traced_functions: list[FunctionTraceStatus] = []

    for func in functions:
        trace_status, _ = evaluate_function_against_stories(
            func,
            request.stories,
            story_embeddings=story_embeddings,
            available_tests=test_functions,
        )
        traced_functions.append(trace_status)

    elapsed_ms = (time.perf_counter() - t0) * 1000

    return FileTraceResponse(
        file_path=str(p),
        functions=traced_functions,
        model_version=settings.model_version if EMBEDDER_AVAILABLE else "stub",
        latency_ms=round(elapsed_ms, 2),
        analysed_at=now,
    )


@router.post("/trace/graph", response_model=GraphResponse)
def trace_graph(request: GraphRequest) -> GraphResponse:
    """Generate 3-node linear chain for the active function under cursor:

    [ User Story ] ---> [ Active Function ] ---> [ Unit Test ]
    """
    now = datetime.now(timezone.utc)
    p = Path(request.file_path)

    # Parse file
    if request.file_content:
        functions = parse_python_source(request.file_content, file_path=str(p))
    else:
        functions = parse_python_file(p)

    # Find function enclosing cursor_line
    active_func: ParsedFunction | None = None
    for f in functions:
        if f.contains_line(request.cursor_line):
            active_func = f
            break

    if not active_func:
        # Fallback to first function if cursor outside functions
        active_func = functions[0] if functions else None

    if not active_func:
        return GraphResponse(
            graph=CytoscapeGraph(elements=[]),
            active_function=None,
            story_id=None,
            analysed_at=now,
        )

    # Pre-embed stories
    story_embeddings: dict[str, Any] = {}
    if EMBEDDER_AVAILABLE and request.stories:
        try:
            embedder = get_embedder()
            for st in request.stories:
                st_text = _build_story_text(st)
                story_embeddings[st.story_id] = embedder.embed_single(st_text)
        except Exception:
            pass

    test_functions = [f for f in functions if f.kind == "test"]
    trace_status, matched_story = evaluate_function_against_stories(
        active_func,
        request.stories,
        story_embeddings=story_embeddings,
        available_tests=test_functions,
    )

    story_id = trace_status.matched_story_id or (matched_story.story_id if matched_story else "UNLINKED")
    elements: list[dict[str, Any]] = []

    # Node 1: User Story
    story_label = f"Story: {story_id}"
    if trace_status.user_story:
        story_label += f"\n{trace_status.user_story[:40]}..."
    elements.append({
        "data": {
            "id": f"story_{story_id}",
            "label": story_label,
            "type": "story",
            "status": "active" if story_id != "UNLINKED" else "orphan",
        }
    })

    # Node 2: Active Function
    func_node_id = f"func_{active_func.name}"
    elements.append({
        "data": {
            "id": func_node_id,
            "label": f"fn {active_func.name}()\n[{trace_status.status}]",
            "type": "function",
            "status": trace_status.status,
            "kind": active_func.kind,
        }
    })

    # Edge 1: Story ---> Active Function
    edge_label = f"{trace_status.similarity * 100:.1f}% ({trace_status.source})" if trace_status.similarity > 0 else "unlinked"
    elements.append({
        "data": {
            "id": f"edge_story_func",
            "source": f"story_{story_id}",
            "target": func_node_id,
            "label": edge_label,
            "similarity": trace_status.similarity,
            "status": trace_status.status,
        }
    })

    # Node 3: Unit Test
    test_node_id = "test_node"
    test_label = "Unit Test\n❌ Missing"
    test_status = "missing"
    if trace_status.has_test_assertion:
        test_label = f"Test: {trace_status.linked_test_symbol or 'test'}\n✅ Assertion Passed"
        test_status = "passed"

    elements.append({
        "data": {
            "id": test_node_id,
            "label": test_label,
            "type": "test",
            "status": test_status,
        }
    })

    # Edge 2: Active Function ---> Unit Test
    elements.append({
        "data": {
            "id": "edge_func_test",
            "source": func_node_id,
            "target": test_node_id,
            "label": "asserts" if trace_status.has_test_assertion else "untested",
            "status": test_status,
        }
    })

    return GraphResponse(
        graph=CytoscapeGraph(elements=elements),
        active_function=active_func.name,
        story_id=story_id,
        analysed_at=now,
    )
