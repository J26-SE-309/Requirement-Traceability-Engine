"""Internal lightweight FastAPI service for ONNX inference.

Provides microservice HTTP interface when ML engine is deployed separately from backend.
Zero cloud dependencies, sub-50ms execution.
"""

from __future__ import annotations

from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from trace_ml.onnx_inference import ONNXEmbedder, calculate_cosine_similarity, get_embedder

app = FastAPI(title="Traceability ML Inference Service", version="0.1.0")


class EmbedRequest(BaseModel):
    texts: List[str] = Field(min_length=1, description="Texts to embed")


class EmbedResponse(BaseModel):
    embeddings: List[List[float]]
    dimensions: int = 384


class SimilarityRequest(BaseModel):
    text_a: str
    text_b: str


class SimilarityResponse(BaseModel):
    similarity: float


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "model": "all-MiniLM-L6-v2-int8-onnx"}


@app.post("/embed", response_model=EmbedResponse)
def embed(request: EmbedRequest) -> EmbedResponse:
    try:
        embedder = get_embedder()
        embs = embedder.embed(request.texts)
        return EmbedResponse(embeddings=embs.tolist(), dimensions=embs.shape[1])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/similarity", response_model=SimilarityResponse)
def similarity(request: SimilarityRequest) -> SimilarityResponse:
    try:
        embedder = get_embedder()
        emb_a = embedder.embed_single(request.text_a)
        emb_b = embedder.embed_single(request.text_b)
        sim = calculate_cosine_similarity(emb_a, emb_b)
        return SimilarityResponse(similarity=sim)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
