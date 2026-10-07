#!/usr/bin/env python3
"""
configure.py — One-shot setup: GitHub secrets + production environment + start server.

Usage:
    python3 configure.py --github-token ghp_xxxx
    python3 configure.py --github-token ghp_xxxx --start-server
"""
import argparse
import base64
import os
import subprocess
import sys

REPO = "Thisisashu/ai-devops-agent"
API = "https://api.github.com"
ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")


def _headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _encrypt(public_key_b64: str, secret: str) -> str:
    from nacl import encoding, public as nacl_public
    pk = nacl_public.PublicKey(public_key_b64.encode(), encoding.Base64Encoder())
    box = nacl_public.SealedBox(pk)
    return base64.b64encode(box.encrypt(secret.encode())).decode()


def _get(url, token):
    import requests
    r = requests.get(url, headers=_headers(token))
    r.raise_for_status()
    return r.json()


def _put(url, token, body):
    import requests
    r = requests.put(url, headers=_headers(token), json=body)
    r.raise_for_status()
    return r


def _post(url, token, body):
    import requests
    r = requests.post(url, headers=_headers(token), json=body)
    r.raise_for_status()
    return r


def _patch(url, token, body):
    import requests
    r = requests.patch(url, headers=_headers(token), json=body)
    return r


def set_repo_secret(token, name, value):
    pk = _get(f"{API}/repos/{REPO}/actions/secrets/public-key", token)
    encrypted = _encrypt(pk["key"], value)
    _put(f"{API}/repos/{REPO}/actions/secrets/{name}", token,
         {"encrypted_value": encrypted, "key_id": pk["key_id"]})
    print(f"  ✓ Repo secret: {name}")


def set_repo_variable(token, name, value):
    r = _patch(f"{API}/repos/{REPO}/actions/variables/{name}", token,
               {"name": name, "value": value})
    if r.status_code == 404:
        _post(f"{API}/repos/{REPO}/actions/variables", token,
              {"name": name, "value": value})
    print(f"  ✓ Repo variable: {name} = {value}")


def create_environment(token, env_name):
    _put(f"{API}/repos/{REPO}/environments/{env_name}", token,
         {"wait_timer": 0, "reviewers": [], "deployment_branch_policy": None})
    print(f"  ✓ Environment: {env_name}")


def set_env_secret(token, env_name, name, value):
    repo_id = _get(f"{API}/repos/{REPO}", token)["id"]
    pk = _get(f"{API}/repositories/{repo_id}/environments/{env_name}/secrets/public-key", token)
    encrypted = _encrypt(pk["key"], value)
    _put(f"{API}/repositories/{repo_id}/environments/{env_name}/secrets/{name}", token,
         {"encrypted_value": encrypted, "key_id": pk["key_id"]})
    print(f"  ✓ Env secret: {env_name}/{name}")


def write_env(token):
    aws_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
    aws_secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    region = os.environ.get("AWS_DEFAULT_REGION", "ap-south-1")

    lines = [
        "OLLAMA_MODEL=qwen2.5:7b\n",
        f"GITHUB_TOKEN={token}\n",
        "GITHUB_REPO=Thisisashu/ai-devops-agent\n",
        "GITHUB_BASE_BRANCH=main\n",
        "REPO_LOCAL_PATH=/home/ashu-ubuntu/ai-devops-agent\n",
        f"AWS_DEFAULT_REGION={region}\n",
    ]
    with open(ENV_FILE, "w") as f:
        f.writelines(lines)
    print(f"  ✓ .env written")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-token", required=True, help="GitHub personal access token")
    parser.add_argument("--start-server", action="store_true", help="Start the FastAPI server after setup")
    args = parser.parse_args()

    token = args.github_token
    aws_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
    aws_secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    region = os.environ.get("AWS_DEFAULT_REGION", "ap-south-1")

    print(f"\n=== Configuring {REPO} ===\n")

    print("1. Writing .env...")
    write_env(token)

    print("\n2. Setting repository secrets...")
    if aws_key:
        set_repo_secret(token, "AWS_ACCESS_KEY_ID", aws_key)
    if aws_secret:
        set_repo_secret(token, "AWS_SECRET_ACCESS_KEY", aws_secret)

    print("\n3. Setting repository variables...")
    set_repo_variable(token, "AWS_REGION", region)

    print("\n4. Creating production environment...")
    create_environment(token, "production")

    print("\n5. Setting production environment secrets...")
    if aws_key:
        set_env_secret(token, "production", "AWS_ACCESS_KEY_ID", aws_key)
    if aws_secret:
        set_env_secret(token, "production", "AWS_SECRET_ACCESS_KEY", aws_secret)

    print(f"""
=== Setup complete! ===

Repo:         https://github.com/{REPO}
Actions:      https://github.com/{REPO}/actions
Environments: https://github.com/{REPO}/settings/environments

Add yourself as a required reviewer on the 'production' environment
to enable manual approval before terraform apply.
""")

    if args.start_server:
        print("Starting FastAPI server on http://0.0.0.0:8000 ...\n")
        venv_python = os.path.join(os.path.dirname(__file__), ".venv", "bin", "python")
        python = venv_python if os.path.exists(venv_python) else sys.executable
        os.execv(python, [python, os.path.join(os.path.dirname(__file__), "server.py")])


if __name__ == "__main__":
    main()
