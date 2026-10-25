"""Version 1 of the traceability API."""

from __future__ import annotations

from fastapi import APIRouter
from app.api.trace import router as trace_router

router = APIRouter(tags=["traceability"])
router.include_router(trace_router)
