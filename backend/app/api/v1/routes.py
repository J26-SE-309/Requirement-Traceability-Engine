"""Version 1 of the traceability API.

Until the embedding model and workspace observer are plugged in, the endpoint returns
placeholder coverage (model_version "stub") so the gateway and frontend can be built
against the real contract.
"""

from datetime import UTC, datetime

from fastapi import APIRouter

from app.schemas import CoverageRequest, CoverageResponse, StoryCoverage

router = APIRouter(tags=["traceability"])


@router.post("/coverage", response_model=CoverageResponse)
def coverage(request: CoverageRequest) -> CoverageResponse:
    """Report how well each story is covered by linked code and tests."""
    now = datetime.now(UTC)
    return CoverageResponse(
        items=[
            StoryCoverage(
                story_id=story.story_id,
                coverage_pct=0.0,
                unlinked_artifact_count=0,
                has_linked_tests=False,
                trace_gaps=["Placeholder result: traceability analysis is not implemented yet."],
                model_version="stub",
                analysed_at=now,
            )
            for story in request.stories
        ]
    )
