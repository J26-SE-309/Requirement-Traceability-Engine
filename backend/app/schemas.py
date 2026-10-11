"""Request and response models: the API contract of this service.

They mirror the JSON Schemas in Synapse-Web/contracts/traceability;
extended with behavioral call-graph links and deterministic Acceptance Criteria evaluations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class StoryRef(BaseModel):
    story_id: str
    user_story: str
    acceptance_criteria: list[str] = Field(default_factory=list)


class ACStatus(BaseModel):
    """Deterministic verification state of a single Acceptance Criterion."""

    criterion: str
    satisfied: bool = False
    similarity: float = Field(default=0.0, ge=-1.0, le=1.0)
    evidence_symbol: str | None = Field(
        default=None,
        description="Function or test symbol providing concrete implementation/assertion",
    )


class CoverageRequest(BaseModel):
    project_id: str | None = None
    stories: list[StoryRef] = Field(min_length=1)
    workspace_path: str | None = Field(default=None, description="Optional root directory of workspace to analyze")
    target_file: str | None = Field(default=None, description="Optional specific file to analyze")
    file_content: str | None = Field(default=None, description="Optional in-memory buffer content")
    delta_only: bool = Field(default=False, description="When true, only analyze modified functions from git delta")


class LinkedArtifact(BaseModel):
    path: str
    symbol: str | None = Field(default=None, description="Function, class or test name inside the file")
    kind: Literal["code", "test"]
    source: Literal["tag", "semantic"] = Field(description="Explicit '# Trace:' tag or embedding similarity")
    similarity: float = Field(ge=-1.0, le=1.0)
    rationale: str


class StoryCoverage(BaseModel):
    story_id: str
    coverage_pct: float = Field(ge=0.0, le=1.0)
    linked_artifacts: list[LinkedArtifact] = Field(default_factory=list)
    unlinked_artifact_count: int = Field(ge=0)
    has_linked_tests: bool
    trace_gaps: list[str] = Field(default_factory=list)
    ac_statuses: list[ACStatus] = Field(
        default_factory=list,
        description="Detailed verification status for each acceptance criterion",
    )
    model_version: str
    analysed_at: datetime


class CoverageResponse(BaseModel):
    items: list[StoryCoverage]


class FunctionTraceStatus(BaseModel):
    """Detailed trace state of a single function block for CodeLens and Graph."""

    name: str
    qualified_name: str
    start_line: int
    end_line: int
    kind: Literal["code", "test"]
    status: Literal["VERIFIED", "MISSING_TEST", "CANDIDATE", "ORPHAN"]
    matched_story_id: str | None = None
    user_story: str | None = None
    acceptance_criteria: list[str] = Field(default_factory=list)
    ac_statuses: list[ACStatus] = Field(
        default_factory=list,
        description="Per-criterion semantic verification status",
    )
    similarity: float = 0.0
    source: Literal["tag", "semantic", "none"] = "none"
    has_test_assertion: bool = False
    linked_test_symbol: str | None = None
    called_symbols: list[str] = Field(
        default_factory=list,
        description="Invocations extracted from AST body for call-graph validation",
    )
    rationale: str = ""


class FileTraceRequest(BaseModel):
    """Request to trace all or delta functions inside a specific editor file."""

    file_path: str
    file_content: str | None = None
    stories: list[StoryRef] = Field(default_factory=list)
    delta_only: bool = False


class FileTraceResponse(BaseModel):
    file_path: str
    functions: list[FunctionTraceStatus]
    model_version: str
    latency_ms: float
    analysed_at: datetime


class GraphElementData(BaseModel):
    id: str
    label: str
    type: Literal["story", "function", "test"]
    status: str | None = None
    similarity: float | None = None
    has_assertion: bool | None = None


class CytoscapeGraph(BaseModel):
    elements: list[dict[str, Any]] = Field(default_factory=list)


class GraphRequest(BaseModel):
    file_path: str
    cursor_line: int = 1
    file_content: str | None = None
    stories: list[StoryRef] = Field(default_factory=list)


class GraphResponse(BaseModel):
    graph: CytoscapeGraph
    active_function: str | None = None
    story_id: str | None = None
    user_story: str | None = None
    ac_statuses: list[ACStatus] = Field(
        default_factory=list,
        description="Acceptance criteria verified for the active viewport story",
    )
    analysed_at: datetime


class ScaffoldNamingRequest(BaseModel):
    story_id: str
    user_story: str
    acceptance_criteria: list[str] = Field(default_factory=list)


class ScaffoldNamingResponse(BaseModel):
    story_id: str
    module_name: str
    implementation_file: str
    test_file: str
    confidence: float
    top_candidates: list[str] = Field(default_factory=list)