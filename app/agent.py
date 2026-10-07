"""AI agent: parse natural language → InfrastructureSpec → Terraform files."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict

import ollama

from app.models import (
    EC2Config,
    InfrastructureSpec,
    NetworkConfig,
    RDSConfig,
    S3Config,
    SecurityGroupConfig,
)

logger = logging.getLogger(__name__)

MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_PARSE_SYSTEM = """You are an AWS infrastructure planning assistant.
Convert the user's natural-language request into a JSON object.

IMPORTANT: The "resources" array MUST list every AWS resource type needed.
Valid resource type strings: "vpc", "subnet", "internet_gateway", "route_table",
"security_group", "ec2", "s3", "rds".

Examples:
- "Create an S3 bucket with versioning and encryption"
  → resources: ["s3"], s3: {versioning: true, encryption: true}
- "Create an EC2 instance in a new VPC with HTTP and SSH"
  → resources: ["vpc","subnet","internet_gateway","route_table","security_group","ec2"]
- "Create an RDS MySQL database in a private subnet"
  → resources: ["vpc","subnet","security_group","rds"]

Schema (omit sections not needed):
{
  "region": "us-east-1",
  "resources": ["..."],
  "ec2": {"instance_type": "t3.micro", "ami_id": null, "key_name": null},
  "network": {
    "vpc_cidr": "10.0.0.0/16",
    "public_subnet_cidrs": ["10.0.1.0/24"],
    "private_subnet_cidrs": ["10.0.2.0/24"],
    "existing_vpc_id": null,
    "existing_subnet_id": null
  },
  "security_group": {"allow_http": false, "allow_https": false, "allow_ssh": false, "allow_mysql": false, "allow_postgres": false},
  "s3": {"versioning": false, "encryption": false, "bucket_name": null},
  "rds": {"engine": "mysql", "engine_version": "8.0", "instance_class": "db.t3.micro", "db_name": "appdb", "username": "admin", "allocated_storage": 20},
  "tags": {"ManagedBy": "AI-DevOps-Agent", "Environment": "dev"}
}

Rules:
- The "resources" array must never be empty.
- If the user mentions an existing VPC ID, set existing_vpc_id to that ID.
- If the user mentions HTTP access, set allow_http=true.
- If the user mentions SSH access, set allow_ssh=true.
- If the user mentions S3 versioning, set versioning=true.
- If the user mentions S3 encryption, set encryption=true.
- Output ONLY valid JSON. No markdown fences, no explanation.
"""

_FIX_SYSTEM = """You are a Terraform expert. Fix the Terraform configuration error below.
Return ONLY the corrected Terraform HCL content for the file. No explanation, no markdown fences."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> Dict[str, Any]:
    """Extract first JSON object from LLM response."""
    # Strip markdown fences
    text = re.sub(r"```(?:json)?", "", text).strip()
    # Find first { ... }
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(text)


def _chat(system: str, user: str) -> str:
    response = ollama.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response["message"]["content"].strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_prompt(prompt: str) -> InfrastructureSpec:
    """Convert natural language prompt to InfrastructureSpec."""
    raw = _chat(_PARSE_SYSTEM, prompt)
    logger.debug("LLM parse response: %s", raw)
    data = _extract_json(raw)
    return InfrastructureSpec(**data)


def fix_terraform(filename: str, content: str, error: str) -> str:
    """Ask the LLM to fix a broken Terraform file."""
    user_msg = f"""File: {filename}

Error:
{error}

Current content:
{content}

Return the corrected Terraform HCL only."""
    return _chat(_FIX_SYSTEM, user_msg)
