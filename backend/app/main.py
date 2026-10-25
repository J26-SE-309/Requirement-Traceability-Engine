"""FastAPI application for the Requirement Traceability Engine."""

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import health, trace
from app.api.v1 import routes
from app.config import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
   
    try:
        from app.api.trace import EMBEDDER_AVAILABLE, _get_story_embedding, _load_default_stories, get_embedder

        if EMBEDDER_AVAILABLE:
            embedder = get_embedder()
            stories = _load_default_stories()
            for st in stories:
                _get_story_embedding(embedder, st)
            logger.info("Pre-warmed ONNX runtime and cached %d sprint stories.", len(stories))
    except Exception as e:
        logger.warning("Model warmup warning: %s", e)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Requirement Traceability Engine API", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(routes.router, prefix="/api/v1")
    return app


app = create_app()
