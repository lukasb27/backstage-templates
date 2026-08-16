#!/usr/bin/env python3
"""
Static checks for templates/http-service/, run on every PR touching it
(see .github/workflows/verify-template.yml).

Deliberately doesn't call Backstage's dry-run API (POST /v2/scaffolder/dry-run)
— that would need a GitHub-hosted runner to reach backstage.example, which is
only resolvable inside the homelab's VPN. Everything here is static: it checks
the template.yaml + skeleton tree on disk against the same failure patterns
already hit live (see the plan's "Bugs found and fixed" list) —
directory-name/enum mismatches (bug #4), copyWithoutTemplating glob patterns
that don't actually match anything (bugs #5/#6) — plus basic Template-entity
structure and the documented one-time-setup secrets.
"""

import sys
from pathlib import Path

import yaml

TEMPLATE_ROOT = Path(__file__).resolve().parent.parent / "templates" / "http-service"
TEMPLATE_YAML = TEMPLATE_ROOT / "template.yaml"
REQUIRED_SECRETS = ["ANTHROPIC_API_KEY", "ARGO_CD_REPO_TOKEN", "RELEASE_PLEASE_TOKEN"]

errors: list[str] = []
warnings: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def load_template() -> dict:
    if not TEMPLATE_YAML.exists():
        fail(f"{TEMPLATE_YAML} does not exist")
        sys.exit(report())
    with TEMPLATE_YAML.open() as f:
        return yaml.safe_load(f)


def check_structure(template: dict) -> None:
    api_version = template.get("apiVersion", "")
    if not api_version.startswith("scaffolder.backstage.io/"):
        fail(f"apiVersion {api_version!r} doesn't start with scaffolder.backstage.io/")

    if template.get("kind") != "Template":
        fail(f"kind is {template.get('kind')!r}, expected 'Template'")

    if not template.get("metadata", {}).get("name"):
        fail("metadata.name is missing")

    steps = template.get("spec", {}).get("steps", [])
    if not steps:
        fail("spec.steps is empty")

    seen_ids = set()
    for step in steps:
        step_id = step.get("id")
        if not step_id:
            fail(f"step {step!r} has no id")
        elif step_id in seen_ids:
            fail(f"duplicate step id: {step_id}")
        else:
            seen_ids.add(step_id)
        if not step.get("action"):
            fail(f"step {step_id!r} has no action")


def enum_values_for(template: dict, param_name: str) -> list[str]:
    for group in template.get("spec", {}).get("parameters", []):
        prop = group.get("properties", {}).get(param_name)
        if prop and "enum" in prop:
            return [str(v) for v in prop["enum"]]
    return []


def expand_url(template: dict, url: str) -> list[str]:
    """Expand a fetch:template url containing a single ${{ parameters.X }}
    token into one candidate path per enum value of X. Returns [url]
    unchanged if there's no such token."""
    import re

    m = re.search(r"\$\{\{\s*parameters\.(\w+)\s*\}\}", url)
    if not m:
        return [url]
    param = m.group(1)
    values = enum_values_for(template, param)
    if not values:
        warn(f"can't statically expand '{{{{ parameters.{param} }}}}' in url {url!r} — no enum found, skipping existence check")
        return []
    return [url.replace(m.group(0), v) for v in values]


def check_fetch_urls_and_copy_patterns(template: dict) -> None:
    for step in template.get("spec", {}).get("steps", []):
        action = step.get("action")
        if action not in ("fetch:template", "fetch:template:file"):
            continue
        raw_url = step.get("input", {}).get("url", "")
        if not raw_url:
            fail(f"step {step.get('id')!r} ({action}) has no input.url")
            continue

        for candidate in expand_url(template, raw_url):
            rel = candidate[2:] if candidate.startswith("./") else candidate
            resolved = TEMPLATE_ROOT / rel
            if action == "fetch:template" and not resolved.is_dir():
                fail(f"step {step.get('id')!r}: url {candidate!r} -> {resolved} does not exist as a directory")
                continue
            if action == "fetch:template:file" and not resolved.is_file():
                fail(f"step {step.get('id')!r}: url {candidate!r} -> {resolved} does not exist as a file")
                continue

            for pattern in step.get("input", {}).get("copyWithoutTemplating", []):
                if pattern.startswith("./"):
                    fail(
                        f"step {step.get('id')!r}: copyWithoutTemplating pattern {pattern!r} has a leading './' — "
                        "fetch:template's own glob matching does exact string equality against paths with no "
                        "leading './' (globby's '**/*' never returns one), so this pattern will silently match "
                        "nothing and every file it should exclude gets Nunjucks-rendered instead"
                    )
                    continue
                matches = list(resolved.glob(pattern))
                if not matches:
                    fail(
                        f"step {step.get('id')!r}: copyWithoutTemplating pattern {pattern!r} matches no files "
                        f"under {resolved} — files it should exclude from Nunjucks rendering will get mangled instead"
                    )


def check_readme_secrets() -> None:
    readme = TEMPLATE_ROOT / "skeletons" / "app" / "base" / "README.md"
    if not readme.exists():
        fail(f"{readme} does not exist")
        return
    text = readme.read_text()
    for secret in REQUIRED_SECRETS:
        if f"gh secret set {secret}" not in text:
            fail(f"README.md is missing the 'gh secret set {secret}' one-time-setup line")


def report() -> int:
    for w in warnings:
        print(f"WARN: {w}")
    for e in errors:
        print(f"FAIL: {e}")
    if errors:
        print(f"\n{len(errors)} check(s) failed.")
        return 1
    print("All static template checks passed.")
    return 0


def main() -> int:
    template = load_template()
    check_structure(template)
    check_fetch_urls_and_copy_patterns(template)
    check_readme_secrets()
    return report()


if __name__ == "__main__":
    sys.exit(main())
