"""Request and response models: the API contract of this service.

They mirror the JSON Schemas in Synapse-Web/contracts/traceability; change both together.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class StoryRef(BaseModel):
    story_id: str
    user_story: str
    acceptance_criteria: list[str] = []


class CoverageRequest(BaseModel):
    project_id: str | None = None
    stories: list[StoryRef] = Field(min_length=1)


class LinkedArtifact(BaseModel):
    path: str
    symbol: str | None = Field(default=None, description="Function, class or test name inside the file")
    kind: Literal["code", "test"]
    source: Literal["tag", "semantic"] = Field(description="Explicit '# Trace:' tag or embedding similarity")
    similarity: float = Field(ge=-1, le=1)
    rationale: str


class StoryCoverage(BaseModel):
    story_id: str
    coverage_pct: float = Field(ge=0, le=1)
    linked_artifacts: list[LinkedArtifact] = []
    unlinked_artifact_count: int = Field(ge=0)
    has_linked_tests: bool
    trace_gaps: list[str] = []
    model_version: str
    analysed_at: datetime


class CoverageResponse(BaseModel):
    items: list[StoryCoverage]
