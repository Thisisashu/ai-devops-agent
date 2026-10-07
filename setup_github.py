#!/usr/bin/env python3
"""
setup_github.py — Configure GitHub repo secrets, variables, and production environment.

Usage:
    export GITHUB_TOKEN=ghp_your_token_here
    python3 setup_github.py
"""
import base64
import json
import os
import sys

import requests
from nacl import encoding, public

REPO = "Thisisashu/ai-devops-agent"
API = "https://api.github.com"

TOKEN = os.environ.get("GITHUB_TOKEN", "")
if not TOKEN:
    print("ERROR: Set GITHUB_TOKEN environment variable first.")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "ap-south-1")


def encrypt_secret(public_key_value: str, secret_value: str) -> str:
    pk = public.PublicKey(public_key_value.encode(), encoding.Base64Encoder())
    box = public.SealedBox(pk)
    encrypted = box.encrypt(secret_value.encode())
    return base64.b64encode(encrypted).decode()


def get_repo_public_key():
    r = requests.get(f"{API}/repos/{REPO}/actions/secrets/public-key", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def set_secret(name: str, value: str, key_id: str, key_value: str):
    encrypted = encrypt_secret(key_value, value)
    r = requests.put(
        f"{API}/repos/{REPO}/actions/secrets/{name}",
        headers=HEADERS,
        json={"encrypted_value": encrypted, "key_id": key_id},
    )
    r.raise_for_status()
    print(f"  ✓ Secret {name} set")


def set_variable(name: str, value: str):
    # Try update first, then create
    r = requests.patch(
        f"{API}/repos/{REPO}/actions/variables/{name}",
        headers=HEADERS,
        json={"name": name, "value": value},
    )
    if r.status_code == 404:
        r = requests.post(
            f"{API}/repos/{REPO}/actions/variables",
            headers=HEADERS,
            json={"name": name, "value": value},
        )
    r.raise_for_status()
    print(f"  ✓ Variable {name} = {value}")


def create_environment(env_name: str):
    r = requests.put(
        f"{API}/repos/{REPO}/environments/{env_name}",
        headers=HEADERS,
        json={
            "wait_timer": 0,
            "reviewers": [],
            "deployment_branch_policy": None,
        },
    )
    r.raise_for_status()
    print(f"  ✓ Environment '{env_name}' created/updated")
    return r.json()


def get_repo_id():
    r = requests.get(f"{API}/repos/{REPO}", headers=HEADERS)
    r.raise_for_status()
    return r.json()["id"]


def set_environment_secret(env_name: str, name: str, value: str, key_id: str, key_value: str):
    repo_id = get_repo_id()
    encrypted = encrypt_secret(key_value, value)
    r = requests.put(
        f"{API}/repositories/{repo_id}/environments/{env_name}/secrets/{name}",
        headers=HEADERS,
        json={"encrypted_value": encrypted, "key_id": key_id},
    )
    r.raise_for_status()
    print(f"  ✓ Environment secret {env_name}/{name} set")


def get_env_public_key(env_name: str):
    repo_id = get_repo_id()
    r = requests.get(
        f"{API}/repositories/{repo_id}/environments/{env_name}/secrets/public-key",
        headers=HEADERS,
    )
    r.raise_for_status()
    return r.json()


def main():
    print(f"\n=== Configuring GitHub repo: {REPO} ===\n")

    # 1. Repo-level secrets
    print("1. Setting repository secrets...")
    pk = get_repo_public_key()
    key_id, key_value = pk["key_id"], pk["key"]

    if AWS_ACCESS_KEY_ID:
        set_secret("AWS_ACCESS_KEY_ID", AWS_ACCESS_KEY_ID, key_id, key_value)
    else:
        print("  ⚠ AWS_ACCESS_KEY_ID not set in environment — skipping")

    if AWS_SECRET_ACCESS_KEY:
        set_secret("AWS_SECRET_ACCESS_KEY", AWS_SECRET_ACCESS_KEY, key_id, key_value)
    else:
        print("  ⚠ AWS_SECRET_ACCESS_KEY not set in environment — skipping")

    # 2. Repo-level variables
    print("\n2. Setting repository variables...")
    set_variable("AWS_REGION", AWS_REGION)

    # 3. Create production environment
    print("\n3. Creating 'production' environment...")
    create_environment("production")

    # 4. Set secrets in production environment too
    print("\n4. Setting production environment secrets...")
    try:
        env_pk = get_env_public_key("production")
        env_key_id, env_key_value = env_pk["key_id"], env_pk["key"]
        if AWS_ACCESS_KEY_ID:
            set_environment_secret("production", "AWS_ACCESS_KEY_ID", AWS_ACCESS_KEY_ID, env_key_id, env_key_value)
        if AWS_SECRET_ACCESS_KEY:
            set_environment_secret("production", "AWS_SECRET_ACCESS_KEY", AWS_SECRET_ACCESS_KEY, env_key_id, env_key_value)
    except Exception as e:
        print(f"  ⚠ Could not set environment secrets: {e}")

    print("\n=== Done! ===")
    print(f"\nRepo: https://github.com/{REPO}")
    print(f"Actions: https://github.com/{REPO}/actions")
    print(f"Environments: https://github.com/{REPO}/settings/environments")
    print("\nNext: Add required reviewers to the 'production' environment for manual approval.")


if __name__ == "__main__":
    main()
