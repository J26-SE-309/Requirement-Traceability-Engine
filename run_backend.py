"""
Launch script for Requirement Traceability Engine (RTE) Backend.

Sets up PYTHONPATH automatically for both backend/ and ml-engine/src/,
then launches the FastAPI Uvicorn server on http://127.0.0.1:8000.
"""

import os
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent
backend_dir = repo_root / "backend"
ml_engine_dir = repo_root / "ml-engine" / "src"

sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(ml_engine_dir))



existing_pp = os.environ.get("PYTHONPATH", "")
os.environ["PYTHONPATH"] = f"{backend_dir}{os.pathsep}{ml_engine_dir}{os.pathsep}{existing_pp}".strip(os.pathsep)

import uvicorn

if __name__ == "__main__":
    print("=" * 65)
    print("  Requirement Traceability Engine (RTE) Backend API")
    print("  URL: http://127.0.0.1:8000")
    print("  Docs: http://127.0.0.1:8000/docs")
    print("=" * 65)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
