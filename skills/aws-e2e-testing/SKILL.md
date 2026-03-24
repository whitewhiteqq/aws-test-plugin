---
name: aws-e2e-testing
description: >
  Generate comprehensive end-to-end tests for AWS Python services by reading
  the actual handler code logic. Covers API Gateway Lambda proxies,
  Step Function workflows, and Batch job executions. Use when asked to write
  E2E tests, end-to-end tests, workflow tests, API tests against a deployed
  environment, or smoke tests for any AWS Python project.
---

# AWS E2E Testing Skill

Generate comprehensive E2E tests by reading the handler code and producing tests
that exercise every endpoint, workflow branch, and failure mode against a deployed environment.

## How to Generate E2E Tests

### Phase 1: Understand the System Under Test

1. **Read the handler source code** — do NOT guess the API shape
2. **Read the OpenAPI/Swagger spec** (if one exists) — get exact paths, methods, schemas
3. **Read CloudFormation/SAM templates** — find API Gateway resource definitions, stage names
4. **Identify the full workflow** — which Lambdas call which other services?

### Phase 2: Map Code Paths to E2E Scenarios

For each endpoint or workflow, generate tests for:

| Code Pattern Found | E2E Test to Generate |
|-------------------|---------------------|
| `if httpMethod == "GET"` | `test_get_resource_returns_200` |
| `if httpMethod == "POST"` + validation | `test_create_resource_valid_payload_returns_200` |
| Validation with required fields | `test_create_resource_missing_required_field_returns_400` |
| Authorization check | `test_request_without_auth_returns_403` |
| Database lookup by ID | `test_get_nonexistent_resource_returns_404` |
| try/except around DB call | `test_get_resource_db_error_returns_500` |
| PUT with ID in body | `test_update_resource_returns_200` |
| DELETE endpoint | `test_delete_resource_returns_200_or_204` |
| Search/list with filters | `test_search_with_valid_filter_returns_results` |
| File upload handling | `test_upload_file_returns_document_id` |
| Async processing (Step Function) | `test_async_request_returns_202_with_request_id` |
| Pagination logic | `test_list_with_pagination_returns_next_token` |

### Phase 3: Write the Tests

Follow these patterns — see [references/api-gateway-patterns.md](references/api-gateway-patterns.md)
for API tests, [references/step-function-patterns.md](references/step-function-patterns.md) for
workflow tests, and [references/batch-patterns.md](references/batch-patterns.md) for batch tests.

#### General E2E Test Structure

#### Component-Prefixed Naming

Each component gets its own prefixed env vars so multiple services coexist
in the same repo without collisions:

- Env vars: `{COMPONENT}_API_BASE_URL`, `{COMPONENT}_API_KEY`, `{COMPONENT}_SFN_ARN`, etc.
- Secrets Manager: individual secrets — per-service or shared across services
  (e.g., `myapp/dev/stripe-key`, `myapp/dev/db-password`)
- SSM Parameter Store: config params, usually per-service
  (e.g., `/myapp/dev/orders/api-url`)

Naming conventions vary by project — adapt to whatever your team uses.

For a polyrepo (single service per repo), the prefix is simply the service name.
For a monorepo, each service directory gets its own prefix derived from discovery.

```python
"""E2E tests for {service_name}. Generated from code analysis of {handler_path}."""
import os
import pytest
import requests

# Component prefix derived from service name during discovery.
# Example: for service "orders", env vars are ORDERS_API_BASE_URL, ORDERS_API_KEY
COMPONENT = "{COMPONENT}"  # e.g. "ORDERS", "USERS", "PAYMENTS"

# ── Strategy A: secrets from .env / environment variables ──
API_BASE_URL = os.getenv(f"{COMPONENT}_API_BASE_URL")
API_KEY = os.getenv(f"{COMPONENT}_API_KEY")

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not API_BASE_URL, reason=f"{COMPONENT}_API_BASE_URL not set"),
]

@pytest.fixture(scope="module")
def api_session():
    """Authenticated session for all tests in this module."""
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        # Add auth headers discovered from handler code:
        # "x-api-key": API_KEY,
        # "Authorization": f"Bearer {token}",
    })
    s.base_url = API_BASE_URL
    return s

# ── Strategy B: secrets from AWS Secrets Manager / SSM Parameter Store ──
# Sensitive values (API keys, tokens) → Secrets Manager (individual entries)
# Config values (URLs, ARNs) → SSM Parameter Store
# Secrets can be shared across services — use the same name in multiple fixtures.
# Adapt names to YOUR project's naming convention.
# See conftest.py for _get_secret(), _get_parameter(), and _resolve() helpers
#
# @pytest.fixture(scope="module")
# def api_session():
#     """Authenticated session. Config from SSM, secrets from SM."""
#     api_base_url = _resolve(
#         f"{COMPONENT}_API_BASE_URL",
#         "/myapp/dev/{component}/api-url",  # SSM param
#     )
#     api_key = _resolve(
#         f"{COMPONENT}_API_KEY",
#         "myapp/dev/{component}/api-key",   # Secrets Manager
#         source="secret",
#     )
#     if not api_base_url:
#         pytest.skip(f"{COMPONENT} API base URL not available")
#     s = requests.Session()
#     s.headers.update({
#         "Content-Type": "application/json",
#         "x-api-key": api_key or "",
#     })
#     s.base_url = api_base_url
#     return s

class TestResourceCRUD:
    """E2E: Full create → read → update → delete lifecycle."""

    def test_create_resource(self, api_session):
        # Payload derived from handler's validation logic
        payload = {
            # Fields from pydantic model or manual validation in handler
        }
        resp = api_session.post(f"{api_session.base_url}/path", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        # Assert fields that handler returns
        assert "id" in data

    def test_get_created_resource(self, api_session):
        # Use ID from create
        resp = api_session.get(f"{api_session.base_url}/path/{{id}}")
        assert resp.status_code == 200

class TestErrorHandling:
    """E2E: Verify error responses match handler's except blocks."""

    def test_missing_required_field(self, api_session):
        resp = api_session.post(f"{api_session.base_url}/path", json={})
        assert resp.status_code == 400

    def test_unauthorized_request(self, api_session):
        s = requests.Session()  # No auth headers
        resp = s.get(f"{api_session.base_url}/path/test-id")
        assert resp.status_code in (401, 403)

class TestLatency:
    """E2E: Response time within SLA."""

    def test_get_response_under_sla(self, api_session):
        import time
        start = time.monotonic()
        resp = api_session.get(f"{api_session.base_url}/path/test-id")
        elapsed = time.monotonic() - start
        assert elapsed < 3.0, f"GET took {elapsed:.2f}s, SLA is 3s"
```

### Phase 4: Handle Test Data

- **Prefix** all test data with `E2E-TEST-` for easy identification and cleanup
- **Create before each test class** using `setup_class` or module-scoped fixtures
- **Clean up** in `teardown_class` when possible
- **Never rely on pre-existing data** — tests must be self-contained

## Configuration

Each component gets **its own prefixed** env vars / Secrets Manager entries.
The prefix is derived from the component name discovered in Step 1 of the
orchestrator (e.g., `orders-api` → `ORDERS_API`).

| Item | Env Var Pattern | Example (for "orders" component) |
|------|----------------|----------------------------------|
| API base URL | `{COMPONENT}_API_BASE_URL` | `ORDERS_API_BASE_URL` |
| API key | `{COMPONENT}_API_KEY` | `ORDERS_API_KEY` |
| SFN ARN | `{COMPONENT}_SFN_ARN` | `ORDERS_SFN_ARN` |
| Batch queue | `{COMPONENT}_BATCH_JOB_QUEUE` | `INGESTION_BATCH_JOB_QUEUE` |
| Batch job def | `{COMPONENT}_BATCH_JOB_DEFINITION` | `INGESTION_BATCH_JOB_DEFINITION` |
| Test env | `TEST_ENV` (shared) | `dev`, `staging` |

For Strategy B (Secrets Manager / SSM Parameter Store), store each value
individually — sensitive secrets (API keys, tokens) in Secrets Manager,
config params (URLs, ARNs) in SSM Parameter Store. Adapt naming to your
project's convention (e.g., `prod/orders/api-key`, `/app/dev/orders/base-url`).

## Safety

- Never run against production without explicit confirmation
- Always use `E2E-TEST-` prefix for created resources
- Set reasonable timeouts for polling loops (max 5-10 minutes)
