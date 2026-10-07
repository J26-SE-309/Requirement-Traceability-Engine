"""Service settings, read from environment variables or backend/.env (see .env.example)."""

from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "traceability"
    # This component's own database and account. No other component connects to it.
    database_url: str = "postgresql+psycopg://trace_user:trace-local@localhost:5443/trace_db"
    cors_origins: list[str] = ["http://localhost:3000"]

    # --- ML Engine & Model Configurations ---
    ml_engine_url: str = Field(
        default="http://localhost:8001",
        description="URL of the local quantized ONNX ML engine service"
    )
    model_version: str = "all-MiniLM-L6-v2-int8-onnx"

    # --- Traceability Verification Thresholds ---
    confidence_high: float = Field(
        default=0.80,
        description="Cosine similarity threshold for verified link"
    )
    confidence_medium: float = Field(
        default=0.65,
        description="Threshold for candidate link needing manual review"
    )

    # --- Latency & Watcher Performance Budgets (ms) ---
    max_delta_latency_ms: int = 350
    max_inference_latency_ms: int = 50
    watcher_debounce_seconds: float = 0.3


@lru_cache
def get_settings() -> Settings:
    return Settings()