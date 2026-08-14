import os

import httpx

# The target host is injected as an env var by k8s/job.yaml, sourced from the
# Deployment/Service name — never hardcoded here, so this file stays out of
# fetch:template's rendering path entirely (see plan §1b).
TARGET_HOST = os.environ["TARGET_HOST"]


def test_root_returns_ok():
    response = httpx.get(f"http://{TARGET_HOST}:8000/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
