#!/usr/bin/env python3
"""Validate the local account/project registry and documentation without AWS."""

import ast
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def check():
    errors = []
    accounts = json.loads((ROOT / "config/accounts.json").read_text())
    projects = json.loads((ROOT / "config/projects.json").read_text())
    if accounts.get("version") != 1 or projects.get("version") != 1:
        errors.append("Registry version must be 1")
    aliases = set()
    account_ids = set()
    for account in accounts["accounts"]:
        alias = account.get("alias", "")
        account_id = account.get("account_id", "")
        if not isinstance(alias, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", alias) or alias in aliases:
            errors.append("Invalid or duplicate account alias")
        if not isinstance(account_id, str) or not re.fullmatch(r"[0-9]{12}", account_id) or account_id in account_ids:
            errors.append("Account IDs must be unique 12-digit strings")
        if not account.get("default_regions"):
            errors.append(f"Missing explicit default region scope for {alias}")
        aliases.add(alias)
        account_ids.add(account_id)
    seen = set()
    for project in projects["projects"]:
        name = project.get("id")
        if not name or name in seen:
            errors.append("Missing or duplicate project ID")
        seen.add(name)
        if project.get("account_alias") is not None and project["account_alias"] not in aliases:
            errors.append(f"Unknown account alias in project {name}")
        url = urlsplit(project.get("repository", ""))
        if url.scheme != "https" or url.username or url.password or not url.hostname:
            errors.append(f"Invalid repository URL for {name}")
        if not project.get("status") or not project.get("mechanism"):
            errors.append(f"Missing ownership/verification context for {name}")

    for path in ROOT.rglob("*.md"):
        if ".git" in path.parts or "inventory" in path.parts:
            continue
        for target in re.findall(r"\]\(([^)\s]+)\)", path.read_text()):
            if target.startswith("#") or urlsplit(target).scheme:
                continue
            local = unquote(target.split("#", 1)[0])
            if not (path.parent / local).exists():
                errors.append(f"Broken local link: {path.relative_to(ROOT)} -> {target}")
    for directory in (ROOT / "scripts", ROOT / "tests"):
        for path in directory.glob("*.py"):
            ast.parse(path.read_text(), filename=str(path))
    for path in (ROOT / "policies").glob("*.json"):
        policy = json.loads(path.read_text())
        if not isinstance(policy, dict) or policy.get("Version") != "2012-10-17" or not isinstance(policy.get("Statement"), list) or not policy["Statement"]:
            errors.append(f"Invalid IAM policy document: {path.name}")

    # Check the actual Git policy rather than assuming a comment protects output.
    for local in ("inventory/local/example.json", ".env", "terraform.tfstate", "tfplan", "secret.tfvars", ".aws/credentials"):
        result = subprocess.run(["git", "check-ignore", "--quiet", "--no-index", "--", local], cwd=ROOT)
        if result.returncode != 0:
            errors.append(f"Sensitive local artifact is not ignored: {local}")
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True).stdout.decode().split("\0")
    for name in filter(None, tracked):
        if name.startswith(("inventory/local/", ".aws/")) or Path(name).name.startswith(".env") and name != ".env.example":
            errors.append(f"Local-only file tracked by Git: {name}")
        if re.search(r"(?:\.tfstate(?:\..*)?|\.tfplan|\.tfvars(?:\.json)?|\.pem|\.key|\.p12)$", name) or Path(name).name == "tfplan":
            errors.append(f"State/plan/key file tracked by Git: {name}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Registry valid: {len(aliases)} accounts, {len(seen)} projects; links, Python syntax and Git exclusions checked.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(check())
    except (OSError, ValueError, KeyError, TypeError, SyntaxError, subprocess.SubprocessError) as exc:
        print(f"Repository check failed: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)
