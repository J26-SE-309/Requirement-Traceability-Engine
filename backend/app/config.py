"""Service settings, read from environment variables or backend/.env (see .env.example)."""

from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "traceability"
    
    database_url: str = "postgresql+psycopg://trace_user:trace-local@localhost:5443/trace_db"
    cors_origins: list[str] = ["http://localhost:3000"]

   
    ml_engine_url: str = Field(
        default="http://localhost:8001",
        description="URL of the local quantized ONNX ML engine service"
    )
    model_version: str = "all-MiniLM-L6-v2-int8-onnx"

    confidence_high: float = Field(
        default=0.65,
        description="Cosine similarity threshold for verified link (1.0000 precision on Deep-SE N=120)"
    )
    confidence_medium: float = Field(
        default=0.55,
        description="Threshold for candidate link needing manual review"
    )


    max_delta_latency_ms: int = 350
    max_inference_latency_ms: int = 50
    watcher_debounce_seconds: float = 0.3


@lru_cache
def get_settings() -> Settings:
    return Settings()