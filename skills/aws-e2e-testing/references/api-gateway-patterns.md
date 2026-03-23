# API Gateway E2E Test Patterns

Ready-to-use patterns for testing API Gateway-backed Lambda functions end-to-end.

Each test module targets **one component** (e.g., `orders-api`, `users-api`).
Env vars and Secrets Manager entries are **prefixed per component** so multiple
services coexist in the same repo without collisions.

## Setup: Choose a Secrets Strategy

### Strategy A: Environment Variables / `.env`

```python
"""E2E lifecycle test for {component_name} REST API."""
import os
import uuid
import pytest
import requests

# Component prefix — derived from service name during discovery.
# Example: for service "orders-api" → COMPONENT = "ORDERS_API"
COMPONENT = "{COMPONENT}"  # replaced per component

API_BASE_URL = os.getenv(f"{COMPONENT}_API_BASE_URL")
API_KEY = os.getenv(f"{COMPONENT}_API_KEY")

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not API_BASE_URL, reason=f"{COMPONENT}_API_BASE_URL not set"),
]


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "x-api-key": API_KEY or "",
    })
    s.base_url = API_BASE_URL
    return s
```

### Strategy B: AWS Secrets Manager / SSM Parameter Store

```python
"""E2E lifecycle test for {component_name} REST API."""
import os
import uuid
import pytest
import requests
import boto3

# Component prefix for env var overrides.
# Secret/param names in AWS vary by project — adapt to YOUR naming convention.
COMPONENT = "{COMPONENT}"  # e.g. "ORDERS_API"

_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")


def _get_secret(name: str) -> str:
    client = boto3.client("secretsmanager", region_name=_REGION)
    return client.get_secret_value(SecretId=name)["SecretString"]


def _get_parameter(name: str, decrypt: bool = False) -> str:
    client = boto3.client("ssm", region_name=_REGION)
    return client.get_parameter(Name=name, WithDecryption=decrypt)["Parameter"]["Value"]


def _resolve(env_var: str, aws_name: str | None = None, *, source: str = "ssm") -> str | None:
    """Env var first, then AWS fallback."""
    value = os.getenv(env_var)
    if value:
        return value
    if not aws_name:
        return None
    try:
        return _get_secret(aws_name) if source == "secret" else _get_parameter(aws_name)
    except Exception:
        return None


pytestmark = [
    pytest.mark.e2e,
]


@pytest.fixture(scope="module")
def api():
    # Adapt these names to your project's naming convention.
    # Multiple services may share the same API key secret.
    api_base_url = _resolve(
        f"{COMPONENT}_API_BASE_URL",
        "/myapp/dev/{component_name}/api-url",  # SSM parameter
    )
    api_key = _resolve(
        f"{COMPONENT}_API_KEY",
        "myapp/dev/{component_name}/api-key",  # Secrets Manager (or shared key)
        source="secret",
    )
    if not api_base_url:
        pytest.skip(f"{COMPONENT} API base URL not available (env or SSM)")
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "x-api-key": api_key or "",
    })
    s.base_url = api_base_url
    return s
```

## Pattern: REST CRUD Lifecycle

The tests below work with either strategy — they use `api.base_url`.


class TestCRUDLifecycle:
    """Full create → get → update → delete workflow."""

    created_id = None

    def test_01_create(self, api):
        payload = {
            "name": f"E2E-TEST-{uuid.uuid4().hex[:8]}",
            # Add required fields from handler validation
        }
        resp = api.post(f"{api.base_url}/resource", json=payload)
        assert resp.status_code in (200, 201), resp.text
        data = resp.json()
        TestCRUDLifecycle.created_id = data.get("id") or data.get("Id")
        assert TestCRUDLifecycle.created_id is not None

    def test_02_get(self, api):
        assert TestCRUDLifecycle.created_id, "Create must succeed first"
        resp = api.get(f"{api.base_url}/resource/{TestCRUDLifecycle.created_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("name", "").startswith("E2E-TEST-")

    def test_03_update(self, api):
        assert TestCRUDLifecycle.created_id, "Create must succeed first"
        payload = {
            "id": TestCRUDLifecycle.created_id,
            "name": f"E2E-TEST-UPDATED-{uuid.uuid4().hex[:8]}",
        }
        resp = api.put(f"{api.base_url}/resource", json=payload)
        assert resp.status_code == 200

    def test_04_search(self, api):
        resp = api.post(
            f"{api.base_url}/resource/search",
            json={"name": "E2E-TEST"},
        )
        assert resp.status_code == 200
        results = resp.json()
        assert isinstance(results, (list, dict))

    def test_05_delete(self, api):
        if not TestCRUDLifecycle.created_id:
            pytest.skip("No resource to delete")
        resp = api.delete(f"{api.base_url}/resource/{TestCRUDLifecycle.created_id}")
        assert resp.status_code in (200, 204)


## Pattern: Error Response Validation

```python
class TestErrorHandling:
    """Verify all error paths return correct status codes and shapes."""

    def test_missing_required_field_returns_400(self, api):
        resp = api.post(f"{api.base_url}/resource", json={})
        assert resp.status_code == 400
        body = resp.json()
        assert "message" in body or "error" in body

    def test_missing_auth_returns_403(self, api):
        # Unauthenticated session
        resp = requests.get(f"{api.base_url}/resource/test-id")
        assert resp.status_code in (401, 403)

    def test_nonexistent_resource_returns_404(self, api):
        resp = api.get(f"{api.base_url}/resource/NONEXISTENT-{uuid.uuid4().hex}")
        assert resp.status_code in (404, 200)  # Some APIs return empty 200

    def test_invalid_json_returns_400(self, api):
        resp = api.post(
            f"{api.base_url}/resource",
            data="not-json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
```

## Pattern: File Upload

```python
import base64
import hashlib


class TestFileUpload:
    """Test file upload endpoints."""

    def test_upload_pdf(self, api):
        # Minimal valid PDF
        pdf_bytes = b"%PDF-1.0\n1 0 obj<</Type/Catalog>>endobj\n"
        b64 = base64.b64encode(pdf_bytes).decode()
        sig = hashlib.md5(pdf_bytes).hexdigest()

        payload = {
            "fileType": "pdf",
            "document": b64,
            "signature": sig,
        }
        resp = api.post(f"{api.base_url}/resource/upload", json=payload)
        assert resp.status_code in (200, 202)

    def test_upload_invalid_type_returns_400(self, api):
        payload = {
            "fileType": "exe",
            "document": base64.b64encode(b"data").decode(),
            "signature": "abc",
        }
        resp = api.post(f"{api.base_url}/resource/upload", json=payload)
        assert resp.status_code == 400
```

## Pattern: Latency SLA Checks

```python
import time


class TestLatencySLA:
    """Verify response times are within acceptable bounds."""

    SLA_SECONDS = 3.0

    @pytest.mark.parametrize("path", [
        "/resource/test-id",
        "/resource/search",
    ])
    def test_get_under_sla(self, api, path):
        start = time.monotonic()
        api.get(f"{api.base_url}{path}")
        elapsed = time.monotonic() - start
        assert elapsed < self.SLA_SECONDS, f"{path} took {elapsed:.2f}s"
```

## Pattern: Pagination

```python
class TestPagination:
    """Test paginated list endpoints."""

    def test_first_page(self, api):
        resp = api.get(f"{API_BASE_URL}/resource?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        items = data.get("items", data.get("results", data))
        assert len(items) <= 10

    def test_next_page_with_token(self, api):
        resp1 = api.get(f"{API_BASE_URL}/resource?limit=1")
        data1 = resp1.json()
        token = data1.get("nextToken") or data1.get("next_token")
        if not token:
            pytest.skip("No pagination token returned")
        resp2 = api.get(f"{API_BASE_URL}/resource?limit=1&nextToken={token}")
        assert resp2.status_code == 200
```

## Pattern: Concurrent Requests

```python
import concurrent.futures


class TestConcurrency:
    """Verify the API handles concurrent requests correctly."""

    def test_concurrent_reads(self, api):
        def fetch():
            return api.get(f"{API_BASE_URL}/resource/test-id")

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(fetch) for _ in range(10)]
            results = [f.result() for f in futures]

        statuses = [r.status_code for r in results]
        assert all(s in (200, 404, 429) for s in statuses)
```
