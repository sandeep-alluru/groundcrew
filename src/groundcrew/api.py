"""FastAPI REST wrapper for groundcrew.

Start:   uvicorn groundcrew.api:app --reload
Install: pip install "groundcrew[api]"
Docs:    http://localhost:8000/docs
"""

from __future__ import annotations

import os
import shlex
import subprocess
from typing import Any

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field
except ImportError as exc:
    raise ImportError("API server requires: pip install 'groundcrew[api]'") from exc

from groundcrew import __version__
from groundcrew.codec import ActionSpec
from groundcrew.oracle import Oracle, ReceiptStore

_DEFAULT_DB = ".groundcrew/receipts.db"


def _db_path() -> str:
    return os.environ.get("GROUNDCREW_DB", _DEFAULT_DB)


app = FastAPI(
    title="groundcrew API",
    description="Deterministic state oracle and semantic action codec for computer-use agents",
    version=__version__,
    license_info={
        "name": "MIT",
        "url": "https://github.com/sandeep-alluru/groundcrew/blob/main/LICENSE",
    },
)


class CaptureRequest(BaseModel):
    """Request body for POST /capture."""

    root: str = Field(".", description="Directory to snapshot.")
    verb: str = Field(..., description="Semantic verb for the action.")
    target: str = Field(..., description="Target the action acts upon.")
    params: dict = Field(default_factory=dict)
    run_cmd: str | None = Field(None, description="Optional shell command to execute.")


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    status: str
    version: str


@app.get("/health", response_model=HealthResponse)
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "version": __version__}


@app.post("/capture")
async def capture(request: CaptureRequest) -> Any:
    """Capture before/after state around an action and persist a receipt."""
    spec = ActionSpec(verb=request.verb, target=request.target, params=request.params)
    with Oracle(request.root, spec) as oracle:
        if request.run_cmd:
            result = subprocess.run(shlex.split(request.run_cmd), cwd=request.root, check=False)  # noqa: S603
            if result.returncode != 0:
                oracle._success = False
    receipt = oracle.record(spec)
    store = ReceiptStore(_db_path())
    store.save(receipt)
    store.close()
    return receipt.to_dict()


@app.get("/receipt/{receipt_id}")
async def get_receipt(receipt_id: str) -> Any:
    """Return a single receipt by ID."""
    store = ReceiptStore(_db_path())
    receipt = store.get(receipt_id)
    store.close()
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"Receipt not found: {receipt_id}")
    return receipt.to_dict()


@app.get("/receipts")
async def list_receipts() -> Any:
    """Return all stored receipts."""
    store = ReceiptStore(_db_path())
    receipts = store.list_receipts()
    store.close()
    return {"receipts": [r.to_dict() for r in receipts]}


@app.get("/diff/{receipt_id}")
async def get_diff(receipt_id: str) -> Any:
    """Return the snapshot diff for a stored receipt."""
    store = ReceiptStore(_db_path())
    receipt = store.get(receipt_id)
    store.close()
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"Receipt not found: {receipt_id}")
    return receipt.diff.to_dict()
