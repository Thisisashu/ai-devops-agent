# AI DevOps Infrastructure Agent

An AI agent that converts natural-language infrastructure requests into
Terraform code, validates it, pushes a GitHub PR, and deploys to AWS via
GitHub Actions.

## Flow

```
User Prompt → AI Agent → Infrastructure Spec → Terraform Files
→ terraform fmt/init/validate/plan → GitHub Branch → Pull Request
→ GitHub Actions (plan) → Human Approval → Terraform Apply → AWS
```

## Quick Start

```bash
# 1. Copy and fill in environment variables
cp .env.example .env

# 2. Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Start Ollama (separate terminal)
ollama serve
ollama pull qwen2.5:7b

# 4. Start the API server
python server.py
```

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/health` | Health check |
| `POST` | `/generate` | Submit infrastructure request |
| `GET`  | `/status/{id}` | Poll pipeline status |
| `GET`  | `/plan/{id}` | View Terraform plan |
| `POST` | `/approve/{id}` | Approve and trigger apply |

### Example

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Create an EC2 instance inside a new VPC with HTTP and SSH access"}'

# Poll status
curl http://localhost:8000/status/<request_id>

# Approve after plan_ready
curl -X POST http://localhost:8000/approve/<request_id>
```

## GitHub Actions Setup

1. Create a GitHub environment named `production` with required reviewers.
2. Add repository secrets:
   - `AWS_ROLE_ARN` — IAM role ARN for OIDC
3. Add repository variable:
   - `AWS_REGION` — e.g. `us-east-1`

## Docker

```bash
docker build -t ai-devops-agent .
docker run -p 8000:8000 --env-file .env ai-devops-agent
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OLLAMA_MODEL` | Ollama model name (default: `qwen2.5:7b`) |
| `GITHUB_TOKEN` | GitHub personal access token |
| `GITHUB_REPO` | GitHub repo in `owner/repo` format |
| `GITHUB_BASE_BRANCH` | Base branch for PRs (default: `main`) |
| `REPO_LOCAL_PATH` | Local path to the git repository (default: `.`) |
