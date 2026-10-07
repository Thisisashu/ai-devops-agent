from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RequestStatus(str, Enum):
    pending = "pending"
    parsing = "parsing"
    generating = "generating"
    validating = "validating"
    plan_ready = "plan_ready"
    pushing = "pushing"
    pr_created = "pr_created"
    approved = "approved"
    applying = "applying"
    deployed = "deployed"
    failed = "failed"


# ---------------------------------------------------------------------------
# Infrastructure specification (AI agent output)
# ---------------------------------------------------------------------------

class EC2Config(BaseModel):
    instance_type: str = "t3.micro"
    ami_id: Optional[str] = None
    key_name: Optional[str] = None

class NetworkConfig(BaseModel):
    vpc_cidr: str = "10.0.0.0/16"
    public_subnet_cidrs: List[str] = ["10.0.1.0/24"]
    private_subnet_cidrs: List[str] = ["10.0.2.0/24"]
    existing_vpc_id: Optional[str] = None
    existing_subnet_id: Optional[str] = None

class SecurityGroupConfig(BaseModel):
    allow_http: bool = False
    allow_https: bool = False
    allow_ssh: bool = False
    allow_mysql: bool = False
    allow_postgres: bool = False

class S3Config(BaseModel):
    versioning: bool = False
    encryption: bool = False
    bucket_name: Optional[str] = None

class RDSConfig(BaseModel):
    engine: str = "mysql"
    engine_version: str = "8.0"
    instance_class: str = "db.t3.micro"
    db_name: str = "appdb"
    username: str = "admin"
    allocated_storage: int = 20

class InfrastructureSpec(BaseModel):
    region: str = "us-east-1"
    resources: List[str] = Field(default_factory=list)
    ec2: Optional[EC2Config] = None
    network: Optional[NetworkConfig] = None
    security_group: Optional[SecurityGroupConfig] = None
    s3: Optional[S3Config] = None
    rds: Optional[RDSConfig] = None
    tags: Dict[str, str] = Field(default_factory=lambda: {
        "ManagedBy": "AI-DevOps-Agent",
        "Environment": "dev",
    })


# ---------------------------------------------------------------------------
# API request / response models
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=5, description="Natural language infrastructure request")

class GenerateResponse(BaseModel):
    request_id: str
    status: RequestStatus
    message: str
    github_pr_url: Optional[str] = None

class StatusResponse(BaseModel):
    request_id: str
    status: RequestStatus
    message: str
    prompt: str
    spec: Optional[Dict[str, Any]] = None
    terraform_plan: Optional[str] = None
    github_pr_url: Optional[str] = None
    github_branch: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class PlanResponse(BaseModel):
    request_id: str
    terraform_plan: Optional[str] = None
    spec: Optional[Dict[str, Any]] = None
    status: RequestStatus

class ApproveResponse(BaseModel):
    request_id: str
    status: RequestStatus
    message: str

class HealthResponse(BaseModel):
    status: str = "ok"
    terraform: str = "unknown"
    ollama: str = "unknown"


# ---------------------------------------------------------------------------
# Internal state record
# ---------------------------------------------------------------------------

class RequestRecord(BaseModel):
    request_id: str
    status: RequestStatus = RequestStatus.pending
    prompt: str
    message: str = ""
    spec: Optional[Dict[str, Any]] = None
    terraform_files: Dict[str, str] = Field(default_factory=dict)
    terraform_plan: Optional[str] = None
    github_branch: Optional[str] = None
    github_pr_url: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
