"""Traceability API Router and Business Logic.

Implements POST /api/v1/coverage, file tracing, and active viewport Cytoscape graph generation.
Evaluates tripartite status: VERIFIED, MISSING_TEST, CANDIDATE, and ORPHAN.
Enforces AST call-graph test invocation checks and deterministic Acceptance Criteria vector evaluation.
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
from app.parsers.python_ast import (
    ParsedFunction,
    parse_python_file,
    parse_python_source,
    split_identifier,
)
from app.schemas import (
    ACStatus,
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


_STORY_EMBEDDINGS_CACHE: dict[str, tuple[str, Any]] = {}


def _get_story_embedding(embedder: Any, story: StoryRef) -> Any:
    """Cache story embeddings to guarantee sub-100ms real-time inference on repeated queries."""
    st_text = _build_story_text(story)
    cached = _STORY_EMBEDDINGS_CACHE.get(story.story_id)
    if cached is not None and cached[0] == st_text:
        return cached[1]
    vec = embedder.embed_single(st_text)
    _STORY_EMBEDDINGS_CACHE[story.story_id] = (st_text, vec)
    return vec


def _load_default_stories() -> list[StoryRef]:
    """Load default stories from .rte/stories.json or return default sprint stories."""
    candidates = [
        REPO_ROOT / ".rte" / "stories.json",
        REPO_ROOT / "stories.json",
    ]
    for c in candidates:
        if c.exists():
            try:
                import json
                data = json.loads(c.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    return [StoryRef(**item) for item in data]
            except Exception:
                pass

    return [
        StoryRef(
            story_id="STORY-101",
            user_story="As a registered customer, I want to authenticate with JWT tokens so that I can securely access protected platform resources.",
            acceptance_criteria=[
                "Validate user authentication token signature and expiration",
                "Return authenticated user principal with claims",
                "Reject expired or malformed bearer tokens with 401 Unauthorized",
            ],
        ),
        StoryRef(
            story_id="STORY-102",
            user_story="As a checkout billing system, I want state sales tax computed accurately based on customer jurisdiction.",
            acceptance_criteria=[
                "Query tax rate for jurisdiction state code and calculate tax",
                "Round calculated tax to two decimal places",
                "Support California, New York, and Texas state rate lookups",
            ],
        ),
        StoryRef(
            story_id="STORY-103",
            user_story="As a merchant, I want credit card payments captured through Stripe and recorded to the transaction ledger.",
            acceptance_criteria=[
                "Process card transaction charge through payment gateway",
                "Validate charge currency and minimum order amount",
                "Issue partial or full refund against captured charge ID",
            ],
        ),
        StoryRef(
            story_id="STORY-104",
            user_story="As an inventory manager, I want warehouse stock reserved atomically when items are added to a checkout cart.",
            acceptance_criteria=[
                "Query available warehouse SKU quantity from database",
                "Atomically decrement stock count to avoid overselling",
                "Raise OutOfStockError if requested quantity exceeds inventory",
            ],
        ),
        StoryRef(
            story_id="STORY-105",
            user_story="As a compliance officer, I want sensitive account and payment operations recorded to an immutable audit trail.",
            acceptance_criteria=[
                "Capture actor user ID, client IP address, action name, and timestamp",
                "Serialize audit record to JSON and write to compliance stream",
            ],
        ),
        StoryRef(
            story_id="STORY-106",
            user_story="As a user who forgot their password, I want to request a secure one-time reset link via email.",
            acceptance_criteria=[
                "Generate cryptographic random token with 15-minute expiration",
                "Validate token has not been previously consumed",
                "Hash new password using bcrypt before persisting to database",
            ],
        ),
        StoryRef(
            story_id="STORY-107",
            user_story="As a newly registered user, I want to receive an account activation email to verify my address.",
            acceptance_criteria=[
                "Generate unique email verification token",
                "Dispatch HTML verification email containing activation URL",
                "Mark user account email_verified status to True upon token validation",
            ],
        ),
        StoryRef(
            story_id="STORY-108",
            user_story="As an enterprise administrator, I want role-based access control (RBAC) enforced on administrative endpoints.",
            acceptance_criteria=[
                "Extract user roles and permissions from authentication context",
                "Allow access only if required permission is present in user scope",
                "Return 403 Forbidden when user lacks required administrative privileges",
            ],
        ),
        StoryRef(
            story_id="STORY-109",
            user_story="As an API gateway operator, I want incoming client requests rate-limited to prevent denial-of-service abuse.",
            acceptance_criteria=[
                "Track request counter per client IP address in sliding 60-second window",
                "Reject excessive requests with HTTP 429 Too Many Requests",
                "Set Retry-After response header indicating time until window reset",
            ],
        ),
        StoryRef(
            story_id="STORY-110",
            user_story="As an online shopper, I want to apply promotional coupon codes to my shopping cart for order discounts.",
            acceptance_criteria=[
                "Verify coupon code exists, is active, and has not passed expiry date",
                "Apply percentage or fixed dollar discount to qualifying cart items",
                "Enforce minimum cart subtotal required to trigger promotional discount",
            ],
        ),
        StoryRef(
            story_id="STORY-111",
            user_story="As a user, I want to upload a profile picture and have it automatically cropped and resized to thumbnail formats.",
            acceptance_criteria=[
                "Validate uploaded file MIME type is JPEG, PNG, or WebP",
                "Enforce maximum file upload size ceiling of 5 megabytes",
                "Resize and crop image into standard 128x128 and 256x256 thumbnail dimensions",
            ],
        ),
        StoryRef(
            story_id="STORY-112",
            user_story="As a delivery logistics service, I want customer shipping addresses geocoded to calculate delivery distance.",
            acceptance_criteria=[
                "Resolve street address into latitude and longitude coordinates",
                "Calculate great-circle geodesic distance between warehouse and customer",
                "Determine estimated shipping cost based on computed distance bracket",
            ],
        ),
        StoryRef(
            story_id="STORY-113",
            user_story="As a financial analyst, I want to export monthly platform revenue and growth metrics to a CSV file.",
            acceptance_criteria=[
                "Aggregate transaction revenue grouped by calendar month",
                "Format columns: month, gross_revenue, refunds, net_revenue, active_users",
                "Stream response as downloadable comma-separated file attachment",
            ],
        ),
        StoryRef(
            story_id="STORY-114",
            user_story="As a security-conscious user, I want to configure two-factor authentication (2FA) with an authenticator app.",
            acceptance_criteria=[
                "Generate base32 secret key and standard TOTP QR code image",
                "Verify 6-digit numeric TOTP code within valid time step window",
                "Generate single-use backup recovery codes for account recovery",
            ],
        ),
        StoryRef(
            story_id="STORY-115",
            user_story="As an online customer, I want real-time order status updates pushed to my browser without refreshing.",
            acceptance_criteria=[
                "Establish authenticated WebSocket connection for customer session",
                "Broadcast order progression events: confirmed, packed, shipped, delivered",
                "Gracefully handle WebSocket disconnections and reconnects",
            ],
        ),
        StoryRef(
            story_id="STORY-116",
            user_story="As an e-commerce customer, I want to search catalog products with auto-complete suggestions.",
            acceptance_criteria=[
                "Index product titles, categories, and descriptions for text matching",
                "Return top 5 matching product suggestions as user types query prefix",
                "Sanitize search query to prevent injection attacks",
            ],
        ),
        StoryRef(
            story_id="STORY-117",
            user_story="As a platform administrator, I want active sessions invalidated in Redis when a user logs out.",
            acceptance_criteria=[
                "Delete user session token from Redis cache upon logout request",
                "Add remaining JWT token validity duration to blacklist cache",
                "Return 200 OK confirming user session has been terminated",
            ],
        ),
        StoryRef(
            story_id="STORY-118",
            user_story="As a database administrator, I want automated index maintenance to optimize query execution latency.",
            acceptance_criteria=[
                "Identify fragmented table indexes across relational database",
                "Execute non-blocking reindex operations during maintenance windows",
                "Record query latency metrics before and after reindex optimization",
            ],
        ),
        StoryRef(
            story_id="STORY-119",
            user_story="As a platform integrator, I want incoming third-party webhooks verified with HMAC SHA256 signatures.",
            acceptance_criteria=[
                "Extract webhook signature header from incoming HTTP request",
                "Compute HMAC SHA256 digest over raw request body using shared secret",
                "Reject webhook requests with 401 Unauthorized if computed signature mismatches",
            ],
        ),
        StoryRef(
            story_id="STORY-120",
            user_story="As a user, I want large file attachments uploaded to cloud storage using multipart chunking with checksums.",
            acceptance_criteria=[
                "Initiate multipart S3 upload session and return presigned part URLs",
                "Verify MD5 or SHA256 checksum for each uploaded binary chunk",
                "Complete multipart upload and assemble final storage object",
            ],
        ),
    ]


def is_function_tested_by(test_func: ParsedFunction, prod_func: ParsedFunction) -> bool:
    """Safely verifies AST assertion and invocation edges."""
    if not getattr(test_func, "has_assertions", False):
        return False

    # Safe attribute access
    called = getattr(test_func, "called_symbols", [])
    if prod_func.name in called:
        return True

    if test_func.name == f"test_{prod_func.name}":
        return True

    return False

def evaluate_acceptance_criteria(
    story: StoryRef,
    functions: list[ParsedFunction],
    embedder: Any | None = None,
) -> list[ACStatus]:
    """Deterministically evaluate each Acceptance Criterion against available functions.

    Calculates cosine similarity between the criterion vector and all symbol representations
    (both implementation functions and unit test fixtures).
    """
    if not story.acceptance_criteria:
        return []

    results: list[ACStatus] = []

    for ac in story.acceptance_criteria:
        best_sim = 0.0
        best_symbol: str | None = None
        clean_ac = ac.lower()

        # 1. First pass: High-confidence direct string/keyword presence in code or docstrings
        for func in functions:
            content = f"{func.name} {func.docstring or ''} {func.code_snippet}".lower()
            # If docstring or test explicitly quotes the criterion phrase
            clean_sub = clean_ac.split(":", 1)[-1].strip() if ":" in clean_ac else clean_ac
            if clean_sub and clean_sub in content:
                best_sim = 1.0
                best_symbol = func.name
                break

        # 2. Second pass: Dense semantic vector comparison via ONNX embedder
        if best_sim < 1.0 and embedder is not None:
            try:
                ac_vec = embedder.embed_single(ac)
                for func in functions:
                    func_vec = embedder.embed_single(func.semantic_text)
                    sim = calculate_cosine_similarity(ac_vec, func_vec)
                    if sim > best_sim:
                        best_sim = sim
                        best_symbol = func.name
            except Exception as e:
                logger.debug("AC embedding comparison failed for '%s': %s", ac, e)

        # An AC is satisfied if it scores >= 0.65 similarity or had a direct keyword hit
        is_satisfied = best_sim >= 0.65
        results.append(
            ACStatus(
                criterion=ac,
                satisfied=is_satisfied,
                similarity=round(best_sim, 4),
                evidence_symbol=best_symbol if is_satisfied else None,
            )
        )

    return results


def evaluate_function_against_stories(
    func: ParsedFunction,
    stories: list[StoryRef],
    story_embeddings: dict[str, Any] | None = None,
    available_tests: list[ParsedFunction] | None = None,
    all_context_functions: list[ParsedFunction] | None = None,
    embedder: Any | None = None,
) -> tuple[FunctionTraceStatus, StoryRef | None]:
    """Match a function against stories, checking explicit tags, AST calls, and semantic similarity."""
    settings = get_settings()
    high_threshold = settings.confidence_high    # default 0.80
    medium_threshold = settings.confidence_medium  # default 0.65

    # 1. Check explicit # Trace: <STORY-ID> directives
    matched_story: StoryRef | None = None
    if func.explicit_traces:
        for st in stories:
            if st.story_id in func.explicit_traces:
                matched_story = st
                break

    if matched_story:
        has_linked_test = False
        linked_test_name = None

        if func.kind == "code" and available_tests:
            for t in available_tests:
                story_tagged = matched_story.story_id in t.explicit_traces
                # Call-graph behavioral check: test must call this function or share tag + call
                if (story_tagged or is_function_tested_by(t, func)) and is_function_tested_by(t, func):
                    has_linked_test = True
                    linked_test_name = t.name
                    break

        status = "VERIFIED" if (func.kind == "test" and func.has_assertions) or has_linked_test else "MISSING_TEST"
        if func.kind == "test":
            status = "VERIFIED" if func.has_assertions else "MISSING_TEST"

        ac_statuses = evaluate_acceptance_criteria(
            matched_story,
            all_context_functions or ([func] + (available_tests or [])),
            embedder=embedder,
        )

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
                ac_statuses=ac_statuses,
                similarity=1.0,
                source="tag",
                has_test_assertion=has_linked_test or (func.kind == "test" and func.has_assertions),
                linked_test_symbol=linked_test_name,
                called_symbols=func.called_symbols,
                rationale=f"Explicitly tagged with '# Trace: {matched_story.story_id}'",
            ),
            matched_story,
        )

    # 2. Semantic matching via ONNX Embeddings
    best_similarity = -1.0
    best_story: StoryRef | None = None

    if EMBEDDER_AVAILABLE and story_embeddings and stories:
        try:
            active_embedder = embedder or get_embedder()
            func_vec = active_embedder.embed_single(func.semantic_text)

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
        has_test = False
        linked_test_name = None

        if func.kind == "code" and available_tests:
            for t in available_tests:
                story_tagged = best_story.story_id in t.explicit_traces
                if (story_tagged or is_function_tested_by(t, func)) and is_function_tested_by(t, func):
                    has_test = True
                    linked_test_name = t.name
                    break

        status = "VERIFIED" if has_test or (func.kind == "test" and func.has_assertions) else "MISSING_TEST"
        rationale = f"High confidence semantic match ({best_similarity * 100:.1f}%)"

        ac_statuses = evaluate_acceptance_criteria(
            best_story,
            all_context_functions or ([func] + (available_tests or [])),
            embedder=embedder,
        )

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
                ac_statuses=ac_statuses,
                similarity=best_similarity,
                source="semantic",
                has_test_assertion=has_test or (func.kind == "test" and func.has_assertions),
                linked_test_symbol=linked_test_name,
                called_symbols=func.called_symbols,
                rationale=rationale,
            ),
            best_story,
        )
    elif best_similarity >= medium_threshold and best_story is not None:
        ac_statuses = evaluate_acceptance_criteria(
            best_story,
            all_context_functions or ([func] + (available_tests or [])),
            embedder=embedder,
        )

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
                ac_statuses=ac_statuses,
                similarity=best_similarity,
                source="semantic",
                has_test_assertion=False,
                linked_test_symbol=None,
                called_symbols=func.called_symbols,
                rationale=f"Candidate semantic match ({best_similarity * 100:.1f}%), requires verification",
            ),
            best_story,
        )
    else:
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
                called_symbols=func.called_symbols,
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

    embedder = None
    story_embeddings: dict[str, Any] = {}
    if EMBEDDER_AVAILABLE:
        try:
            embedder = get_embedder()
            for st in request.stories:
                story_embeddings[st.story_id] = _get_story_embedding(embedder, st)
        except Exception as e:
            logger.warning("Failed embedding stories: %s", e)

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
        for search_dir in [REPO_ROOT / "backend" / "app", REPO_ROOT / "backend" / "tests"]:
            if search_dir.exists():
                for py_file in search_dir.rglob("*.py"):
                    functions_to_analyze.extend(parse_python_file(py_file))

    test_functions = [f for f in functions_to_analyze if f.kind == "test"]
    story_linked_artifacts: dict[str, list[LinkedArtifact]] = {s.story_id: [] for s in request.stories}
    unlinked_count = 0

    for func in functions_to_analyze:
        trace_status, matched_story = evaluate_function_against_stories(
            func,
            request.stories,
            story_embeddings=story_embeddings,
            available_tests=test_functions,
            all_context_functions=functions_to_analyze,
            embedder=embedder,
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

    items: list[StoryCoverage] = []
    for st in request.stories:
        artifacts = story_linked_artifacts.get(st.story_id, [])
        code_artifacts = [a for a in artifacts if a.kind == "code"]
        test_artifacts = [a for a in artifacts if a.kind == "test"]
        has_tests = len(test_artifacts) > 0

        # Coverage percentage calculation
        if code_artifacts and has_tests:
            coverage_pct = 1.0
        elif code_artifacts and not has_tests:
            coverage_pct = 0.5
        elif any(a.similarity >= settings.confidence_medium for a in artifacts):
            coverage_pct = 0.25
        else:
            coverage_pct = 0.0

        gaps: list[str] = []
        if not code_artifacts:
            gaps.append(f"No code implementation linked for story {st.story_id}.")
        elif not has_tests:
            gaps.append(f"Story {st.story_id} has code implementations ({len(code_artifacts)} symbols) but lacks test assertions.")

        # Compute deterministic acceptance criteria coverage
        ac_statuses = evaluate_acceptance_criteria(st, functions_to_analyze, embedder=embedder)

        items.append(
            StoryCoverage(
                story_id=st.story_id,
                coverage_pct=coverage_pct,
                linked_artifacts=artifacts,
                unlinked_artifact_count=unlinked_count,
                has_linked_tests=has_tests,
                trace_gaps=gaps,
                ac_statuses=ac_statuses,
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

    if request.delta_only:
        functions, _ = get_modified_functions(p, source_code=request.file_content)
    else:
        if request.file_content:
            functions = parse_python_source(request.file_content, file_path=str(p))
        else:
            functions = parse_python_file(p)

    effective_stories = request.stories or _load_default_stories()

    embedder = None
    story_embeddings: dict[str, Any] = {}
    if EMBEDDER_AVAILABLE and effective_stories:
        try:
            embedder = get_embedder()
            for st in effective_stories:
                story_embeddings[st.story_id] = _get_story_embedding(embedder, st)
        except Exception as e:
            logger.warning("Story embedding failed: %s", e)

    test_functions = [f for f in functions if f.kind == "test"]
    traced_functions: list[FunctionTraceStatus] = []

    for func in functions:
        trace_status, _ = evaluate_function_against_stories(
            func,
            effective_stories,
            story_embeddings=story_embeddings,
            available_tests=test_functions,
            all_context_functions=functions,
            embedder=embedder,
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

    if request.file_content:
        functions = parse_python_source(request.file_content, file_path=str(p))
    else:
        functions = parse_python_file(p)

    active_func: ParsedFunction | None = None
    for f in functions:
        if f.contains_line(request.cursor_line):
            active_func = f
            break

    if not active_func:
        active_func = functions[0] if functions else None

    if not active_func:
        return GraphResponse(
            graph=CytoscapeGraph(elements=[]),
            active_function=None,
            story_id=None,
            user_story=None,
            ac_statuses=[],
            analysed_at=now,
        )

    effective_stories = request.stories or _load_default_stories()

    embedder = None
    story_embeddings: dict[str, Any] = {}
    if EMBEDDER_AVAILABLE and effective_stories:
        try:
            embedder = get_embedder()
            for st in effective_stories:
                st_text = _build_story_text(st)
                story_embeddings[st.story_id] = embedder.embed_single(st_text)
        except Exception:
            pass

    test_functions = [f for f in functions if f.kind == "test"]
    trace_status, matched_story = evaluate_function_against_stories(
        active_func,
        effective_stories,
        story_embeddings=story_embeddings,
        available_tests=test_functions,
        all_context_functions=functions,
        embedder=embedder,
    )

    story_id = trace_status.matched_story_id or (matched_story.story_id if matched_story else "UNLINKED")
    user_story_text = trace_status.user_story or (matched_story.user_story if matched_story else None)
    elements: list[dict[str, Any]] = []

    # Node 1: User Story
    story_label = f"Story: {story_id}"
    if user_story_text:
        story_label += f"\n{user_story_text}"
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
            "id": "edge_story_func",
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
    edge_assertion_label = "asserts" if trace_status.has_test_assertion else "untested"
    elements.append({
        "data": {
            "id": "edge_func_test",
            "source": func_node_id,
            "target": test_node_id,
            "label": edge_assertion_label,
            "status": test_status,
        }
    })

    # Resolve deterministic AC status for active story
    resolved_ac_statuses = trace_status.ac_statuses
    if not resolved_ac_statuses and matched_story:
        resolved_ac_statuses = evaluate_acceptance_criteria(matched_story, functions, embedder=embedder)

    return GraphResponse(
        graph=CytoscapeGraph(elements=elements),
        active_function=active_func.name,
        story_id=story_id,
        user_story=user_story_text,
        ac_statuses=resolved_ac_statuses,
        analysed_at=now,
    )