"""Background pipeline: parse → generate → validate → push → PR."""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime

from app import store
from app.agent import parse_prompt
from app.models import RequestRecord, RequestStatus
from app.terraform import generate_terraform_files, validate_and_plan

logger = logging.getLogger(__name__)

GITHUB_ENABLED = bool(os.getenv("GITHUB_TOKEN") and os.getenv("GITHUB_REPO"))


def _update(record: RequestRecord, status: RequestStatus, message: str, **kwargs) -> None:
    record.status = status
    record.message = message
    record.updated_at = datetime.utcnow()
    for k, v in kwargs.items():
        setattr(record, k, v)
    store.save(record)


def run_pipeline(request_id: str, prompt: str) -> None:
    """Full pipeline executed in a background thread."""
    record = RequestRecord(request_id=request_id, prompt=prompt)
    store.save(record)

    try:
        # 1. Parse prompt → spec
        _update(record, RequestStatus.parsing, "Parsing infrastructure request...")
        spec = parse_prompt(prompt)
        _update(record, RequestStatus.generating, "Generating Terraform code...",
                spec=spec.model_dump())

        # 2. Generate Terraform files
        files = generate_terraform_files(spec)
        record.terraform_files = files

        # 3. Validate + plan (with AI auto-fix)
        _update(record, RequestStatus.validating, "Running terraform fmt/init/validate/plan...")
        success, plan_or_error, fixed_files = validate_and_plan(files, request_id)

        if not success:
            _update(record, RequestStatus.failed,
                    "Terraform validation/plan failed.", error=plan_or_error)
            return

        record.terraform_files = fixed_files
        record.terraform_plan = plan_or_error

        if not GITHUB_ENABLED:
            _update(record, RequestStatus.plan_ready,
                    "Terraform plan is ready. GitHub integration not configured — "
                    "set GITHUB_TOKEN and GITHUB_REPO to enable PR creation.",
                    terraform_plan=plan_or_error)
            return

        # 4. Push branch + create PR
        _update(record, RequestStatus.pushing, "Pushing branch to GitHub...")
        from app.github_integration import create_pull_request, push_terraform_branch

        branch_name, _ = push_terraform_branch(request_id, fixed_files, prompt)
        record.github_branch = branch_name

        _update(record, RequestStatus.pr_created, "Creating Pull Request...")
        pr_url = create_pull_request(
            branch_name=branch_name,
            request_id=request_id,
            prompt=prompt,
            spec_dict=spec.model_dump(),
            plan_output=plan_or_error,
            files=fixed_files,
        )

        _update(record, RequestStatus.plan_ready,
                "Terraform plan is ready for approval.",
                github_pr_url=pr_url,
                github_branch=branch_name,
                terraform_plan=plan_or_error)

    except Exception as exc:
        logger.exception("Pipeline error for %s", request_id)
        _update(record, RequestStatus.failed, f"Pipeline error: {exc}", error=str(exc))


def run_apply(request_id: str) -> None:
    """Trigger terraform apply via GitHub Actions after approval."""
    record = store.get(request_id)
    if not record:
        return

    _update(record, RequestStatus.applying, "Triggering Terraform apply via GitHub Actions...")

    if not GITHUB_ENABLED:
        _update(record, RequestStatus.deployed,
                "Apply approved. GitHub Actions not configured — "
                "apply would run in CI/CD pipeline.")
        return

    try:
        from app.github_integration import trigger_workflow
        run_id = trigger_workflow(record.github_branch or "main")
        msg = (f"GitHub Actions workflow triggered (run_id={run_id}). "
               "Monitor the PR for deployment status.")
        _update(record, RequestStatus.deployed, msg)
    except Exception as exc:
        logger.exception("Apply trigger error for %s", request_id)
        _update(record, RequestStatus.failed, f"Apply trigger failed: {exc}", error=str(exc))
