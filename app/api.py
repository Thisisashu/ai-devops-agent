"""FastAPI application — all routes."""
from __future__ import annotations

import subprocess
import threading
import uuid
from datetime import datetime

from fastapi import FastAPI, HTTPException

from app import store
from app.models import (
    ApproveResponse,
    GenerateRequest,
    GenerateResponse,
    HealthResponse,
    PlanResponse,
    RequestStatus,
    StatusResponse,
)
from app.pipeline import run_apply, run_pipeline

app = FastAPI(
    title="AI DevOps Infrastructure Agent",
    description="Natural language → Terraform → GitHub PR → AWS",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
def health():
    tf_ok = "ok"
    try:
        r = subprocess.run(["terraform", "version"], capture_output=True, timeout=5)
        if r.returncode != 0:
            tf_ok = "error"
    except Exception:
        tf_ok = "not found"

    ollama_ok = "ok"
    try:
        import ollama
        ollama.list()
    except Exception:
        ollama_ok = "not reachable"

    return HealthResponse(status="ok", terraform=tf_ok, ollama=ollama_ok)


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------

@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    request_id = str(uuid.uuid4())
    thread = threading.Thread(
        target=run_pipeline,
        args=(request_id, req.prompt),
        daemon=True,
    )
    thread.start()

    return GenerateResponse(
        request_id=request_id,
        status=RequestStatus.pending,
        message="Pipeline started. Poll /status/{request_id} for updates.",
    )


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@app.get("/status/{request_id}", response_model=StatusResponse)
def status(request_id: str):
    record = store.get(request_id)
    if not record:
        raise HTTPException(status_code=404, detail="Request not found")
    return StatusResponse(
        request_id=record.request_id,
        status=record.status,
        message=record.message,
        prompt=record.prompt,
        spec=record.spec,
        terraform_plan=record.terraform_plan,
        github_pr_url=record.github_pr_url,
        github_branch=record.github_branch,
        error=record.error,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

@app.get("/plan/{request_id}", response_model=PlanResponse)
def plan(request_id: str):
    record = store.get(request_id)
    if not record:
        raise HTTPException(status_code=404, detail="Request not found")
    return PlanResponse(
        request_id=record.request_id,
        terraform_plan=record.terraform_plan,
        spec=record.spec,
        status=record.status,
    )


# ---------------------------------------------------------------------------
# Approve
# ---------------------------------------------------------------------------

@app.post("/approve/{request_id}", response_model=ApproveResponse)
def approve(request_id: str):
    record = store.get(request_id)
    if not record:
        raise HTTPException(status_code=404, detail="Request not found")
    if record.status not in (RequestStatus.plan_ready, RequestStatus.pr_created):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve request in status '{record.status}'. "
                   "Request must be in 'plan_ready' or 'pr_created' status.",
        )

    thread = threading.Thread(
        target=run_apply,
        args=(request_id,),
        daemon=True,
    )
    thread.start()

    return ApproveResponse(
        request_id=request_id,
        status=RequestStatus.applying,
        message="Approval received. Triggering Terraform apply via GitHub Actions.",
    )
