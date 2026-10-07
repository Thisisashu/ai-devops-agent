"""Terraform file generation, validation, and plan execution."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Tuple

from app.models import InfrastructureSpec

logger = logging.getLogger(__name__)

TERRAFORM_BASE_DIR = Path(os.getenv("TERRAFORM_BASE_DIR", "terraform"))
MAX_FIX_ATTEMPTS = 3


# ---------------------------------------------------------------------------
# Terraform file generators
# ---------------------------------------------------------------------------

def _versions_tf(spec: InfrastructureSpec) -> str:
    return f"""terraform {{
  required_version = ">= 1.0"
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }}
  }}
}}
"""


def _providers_tf(spec: InfrastructureSpec) -> str:
    return f"""provider "aws" {{
  region = var.aws_region
}}
"""


def _variables_tf(spec: InfrastructureSpec) -> str:
    lines = [
        'variable "aws_region" {\n  description = "AWS region"\n  type        = string\n  default     = "' + spec.region + '"\n}\n',
        'variable "project_name" {\n  description = "Project name used for tagging"\n  type        = string\n  default     = "ai-devops-agent"\n}\n',
    ]

    net = spec.network
    if net:
        if not net.existing_vpc_id:
            lines.append('variable "vpc_cidr" {\n  description = "VPC CIDR block"\n  type        = string\n  default     = "' + net.vpc_cidr + '"\n}\n')
        else:
            lines.append('variable "vpc_id" {\n  description = "Existing VPC ID"\n  type        = string\n  default     = "' + net.existing_vpc_id + '"\n}\n')

    if spec.ec2 and spec.ec2.key_name:
        lines.append('variable "key_name" {\n  description = "EC2 key pair name"\n  type        = string\n  default     = "' + spec.ec2.key_name + '"\n}\n')

    if spec.rds:
        lines.append('variable "db_password" {\n  description = "RDS master password"\n  type        = string\n  sensitive   = true\n  default     = "ChangeMe123!"\n}\n')

    return "\n".join(lines)


def _outputs_tf(spec: InfrastructureSpec) -> str:
    outputs = []
    if "ec2" in spec.resources:
        outputs.append('output "ec2_public_ip" {\n  description = "EC2 instance public IP"\n  value       = try(aws_instance.main[0].public_ip, null)\n}\n')
    if "vpc" in spec.resources:
        outputs.append('output "vpc_id" {\n  description = "VPC ID"\n  value       = try(aws_vpc.main[0].id, null)\n}\n')
    if "s3" in spec.resources:
        outputs.append('output "s3_bucket_name" {\n  description = "S3 bucket name"\n  value       = try(aws_s3_bucket.main[0].bucket, null)\n}\n')
    if "rds" in spec.resources:
        outputs.append('output "rds_endpoint" {\n  description = "RDS endpoint"\n  value       = try(aws_db_instance.main[0].endpoint, null)\n}\n')
    return "\n".join(outputs) if outputs else '# No outputs defined\n'


def _main_tf(spec: InfrastructureSpec) -> str:
    blocks: list[str] = []
    net = spec.network
    sg = spec.security_group
    tags_str = "\n".join(f'    {k} = "{v}"' for k, v in spec.tags.items())
    tags_block = f"""  tags = {{
{tags_str}
  }}"""

    # ---- VPC / Network ----
    if "vpc" in spec.resources:
        if net and net.existing_vpc_id:
            blocks.append(f"""data "aws_vpc" "main" {{
  id = var.vpc_id
}}
""")
        else:
            cidr = net.vpc_cidr if net else "10.0.0.0/16"
            blocks.append(f"""resource "aws_vpc" "main" {{
  count      = 1
  cidr_block = var.vpc_cidr

{tags_block}
}}
""")

    if "internet_gateway" in spec.resources:
        vpc_ref = "data.aws_vpc.main.id" if (net and net.existing_vpc_id) else "aws_vpc.main[0].id"
        blocks.append(f"""resource "aws_internet_gateway" "main" {{
  count  = 1
  vpc_id = {vpc_ref}

{tags_block}
}}
""")

    if "subnet" in spec.resources and net:
        vpc_ref = "data.aws_vpc.main.id" if net.existing_vpc_id else "aws_vpc.main[0].id"
        for i, cidr in enumerate(net.public_subnet_cidrs):
            az_index = i % 3
            blocks.append(f"""resource "aws_subnet" "public_{i}" {{
  count             = 1
  vpc_id            = {vpc_ref}
  cidr_block        = "{cidr}"
  availability_zone = "${{var.aws_region}}{chr(97 + az_index)}"
  map_public_ip_on_launch = true

{tags_block}
}}
""")
        for i, cidr in enumerate(net.private_subnet_cidrs):
            az_index = i % 3
            blocks.append(f"""resource "aws_subnet" "private_{i}" {{
  count             = 1
  vpc_id            = {vpc_ref}
  cidr_block        = "{cidr}"
  availability_zone = "${{var.aws_region}}{chr(97 + az_index)}"

{tags_block}
}}
""")

    if "route_table" in spec.resources:
        vpc_ref = "data.aws_vpc.main.id" if (net and net.existing_vpc_id) else "aws_vpc.main[0].id"
        blocks.append(f"""resource "aws_route_table" "public" {{
  count  = 1
  vpc_id = {vpc_ref}

  route {{
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main[0].id
  }}

{tags_block}
}}

resource "aws_route_table_association" "public_0" {{
  count          = 1
  subnet_id      = aws_subnet.public_0[0].id
  route_table_id = aws_route_table.public[0].id
}}
""")

    # ---- Security Group ----
    if "security_group" in spec.resources and sg:
        vpc_ref = "data.aws_vpc.main.id" if (net and net.existing_vpc_id) else "aws_vpc.main[0].id"
        ingress_rules = []
        if sg.allow_http:
            ingress_rules.append('  ingress {\n    from_port   = 80\n    to_port     = 80\n    protocol    = "tcp"\n    cidr_blocks = ["0.0.0.0/0"]\n  }')
        if sg.allow_https:
            ingress_rules.append('  ingress {\n    from_port   = 443\n    to_port     = 443\n    protocol    = "tcp"\n    cidr_blocks = ["0.0.0.0/0"]\n  }')
        if sg.allow_ssh:
            ingress_rules.append('  ingress {\n    from_port   = 22\n    to_port     = 22\n    protocol    = "tcp"\n    cidr_blocks = ["0.0.0.0/0"]\n    description = "SSH - restrict in production"\n  }')
        if sg.allow_mysql:
            ingress_rules.append('  ingress {\n    from_port   = 3306\n    to_port     = 3306\n    protocol    = "tcp"\n    cidr_blocks = ["10.0.0.0/8"]\n  }')
        if sg.allow_postgres:
            ingress_rules.append('  ingress {\n    from_port   = 5432\n    to_port     = 5432\n    protocol    = "tcp"\n    cidr_blocks = ["10.0.0.0/8"]\n  }')
        ingress_str = "\n".join(ingress_rules)
        blocks.append(f"""resource "aws_security_group" "main" {{
  count       = 1
  name        = "${{var.project_name}}-sg"
  description = "Security group managed by AI DevOps Agent"
  vpc_id      = {vpc_ref}

{ingress_str}

  egress {{
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }}

{tags_block}
}}
""")

    # ---- EC2 ----
    if "ec2" in spec.resources and spec.ec2:
        ec2 = spec.ec2
        ami_block = f'  ami = "{ec2.ami_id}"' if ec2.ami_id else """  ami = data.aws_ami.amazon_linux.id"""
        subnet_ref = (
            f'  subnet_id = "{net.existing_subnet_id}"' if (net and net.existing_subnet_id)
            else "  subnet_id = aws_subnet.public_0[0].id" if "subnet" in spec.resources
            else ""
        )
        sg_ref = '  vpc_security_group_ids = [aws_security_group.main[0].id]' if "security_group" in spec.resources else ""
        key_block = f'  key_name = var.key_name' if (ec2.key_name) else ""

        if not ec2.ami_id:
            blocks.insert(0, """data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}
""")

        blocks.append(f"""resource "aws_instance" "main" {{
  count         = 1
  instance_type = "{ec2.instance_type}"
{ami_block}
{subnet_ref}
{sg_ref}
{key_block}

{tags_block}
}}
""")

    # ---- S3 ----
    if "s3" in spec.resources and spec.s3:
        s3 = spec.s3
        bucket_name = s3.bucket_name or "${var.project_name}-bucket"
        versioning_block = ""
        if s3.versioning:
            versioning_block = """
resource "aws_s3_bucket_versioning" "main" {
  count  = 1
  bucket = aws_s3_bucket.main[0].id
  versioning_configuration {
    status = "Enabled"
  }
}
"""
        encryption_block = ""
        if s3.encryption:
            encryption_block = """
resource "aws_s3_bucket_server_side_encryption_configuration" "main" {
  count  = 1
  bucket = aws_s3_bucket.main[0].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
"""
        blocks.append(f"""resource "aws_s3_bucket" "main" {{
  count  = 1
  bucket = "{bucket_name}"

{tags_block}
}}
{versioning_block}{encryption_block}""")

    # ---- RDS ----
    if "rds" in spec.resources and spec.rds:
        rds = spec.rds
        subnet_group_block = ""
        if "subnet" in spec.resources:
            subnet_group_block = """resource "aws_db_subnet_group" "main" {
  count      = 1
  name       = "${var.project_name}-db-subnet-group"
  subnet_ids = [aws_subnet.private_0[0].id]

""" + tags_block + "\n}\n"
            blocks.append(subnet_group_block)

        sg_ref = '[aws_security_group.main[0].id]' if "security_group" in spec.resources else '[]'
        subnet_group_ref = 'aws_db_subnet_group.main[0].name' if "subnet" in spec.resources else 'null'
        blocks.append(f"""resource "aws_db_instance" "main" {{
  count                  = 1
  engine                 = "{rds.engine}"
  engine_version         = "{rds.engine_version}"
  instance_class         = "{rds.instance_class}"
  db_name                = "{rds.db_name}"
  username               = "{rds.username}"
  password               = var.db_password
  allocated_storage      = {rds.allocated_storage}
  db_subnet_group_name   = {subnet_group_ref}
  vpc_security_group_ids = {sg_ref}
  skip_final_snapshot    = true

{tags_block}
}}
""")

    return "\n".join(blocks)


def _tfvars_example(spec: InfrastructureSpec) -> str:
    lines = [
        f'aws_region   = "{spec.region}"',
        f'project_name = "ai-devops-agent"',
    ]
    if spec.rds:
        lines.append('db_password  = "ChangeMe123!"')
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Generate all files for a spec
# ---------------------------------------------------------------------------

def generate_terraform_files(spec: InfrastructureSpec) -> Dict[str, str]:
    """Return a dict of filename → content for the generated Terraform."""
    return {
        "versions.tf": _versions_tf(spec),
        "providers.tf": _providers_tf(spec),
        "variables.tf": _variables_tf(spec),
        "main.tf": _main_tf(spec),
        "outputs.tf": _outputs_tf(spec),
        "terraform.tfvars.example": _tfvars_example(spec),
    }


# ---------------------------------------------------------------------------
# Run terraform commands in a temp directory
# ---------------------------------------------------------------------------

def _run(cmd: list[str], cwd: Path) -> Tuple[int, str, str]:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
    return result.returncode, result.stdout, result.stderr


def validate_and_plan(
    files: Dict[str, str],
    request_id: str,
) -> Tuple[bool, str, Dict[str, str]]:
    """
    Write files to a temp dir, run fmt/init/validate/plan.
    Returns (success, plan_output_or_error, possibly_fixed_files).
    """
    from app.agent import fix_terraform  # avoid circular at module level

    work_dir = Path(tempfile.mkdtemp(prefix=f"tf_{request_id}_"))
    logger.info("Terraform work dir: %s", work_dir)

    try:
        # Write files
        for name, content in files.items():
            (work_dir / name).write_text(content)

        # fmt
        _run(["terraform", "fmt"], work_dir)

        # init (no backend)
        rc, out, err = _run(
            ["terraform", "init", "-backend=false", "-input=false", "-no-color"],
            work_dir,
        )
        if rc != 0:
            return False, f"terraform init failed:\n{err}", files

        # validate + auto-fix loop
        current_files = dict(files)
        for attempt in range(MAX_FIX_ATTEMPTS):
            rc, out, err = _run(["terraform", "validate", "-no-color"], work_dir)
            if rc == 0:
                break
            if attempt == MAX_FIX_ATTEMPTS - 1:
                return False, f"terraform validate failed after {MAX_FIX_ATTEMPTS} attempts:\n{err}", current_files

            logger.warning("Validation error (attempt %d): %s", attempt + 1, err)
            # Ask AI to fix main.tf (most likely culprit)
            fixed = fix_terraform("main.tf", current_files.get("main.tf", ""), err)
            current_files["main.tf"] = fixed
            (work_dir / "main.tf").write_text(fixed)
            _run(["terraform", "fmt"], work_dir)

        # plan
        rc, out, err = _run(
            ["terraform", "plan", "-input=false", "-no-color"],
            work_dir,
        )
        plan_output = out + (f"\n{err}" if err else "")
        if rc not in (0, 2):  # 2 = changes present (normal)
            return False, f"terraform plan failed:\n{plan_output}", current_files

        return True, plan_output, current_files

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
