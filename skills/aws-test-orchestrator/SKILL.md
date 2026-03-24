---
name: aws-test-orchestrator
description: >
  Master skill for testing AWS Python projects. Discovers project components
  (Lambda, API Gateway, Step Functions, Batch), reads handler code logic,
  and coordinates test generation across all categories (E2E, integration,
  contract, performance, load). Use when asked to: test, write tests, scaffold
  tests, run tests, analyze test results, debug test failures, or improve
  test coverage for any AWS Python microservice project.
---

# AWS Test Orchestrator

Master coordination skill. Discovers the project, delegates to category-specific skills.

## Step 1: Discover Project Components

Before writing any test, map the project. Run these discovery steps.

### Derive the Component Prefix

Every component gets a **unique env var prefix** to avoid collisions in monorepos.
Derive it from the service directory name, uppercased with hyphens replaced by
underscores:

| Directory | Prefix | Example Env Vars |
|-----------|--------|-----------------|
| `orders-api/` | `ORDERS_API` | `ORDERS_API_BASE_URL`, `ORDERS_API_KEY` |
| `processing-batch/` | `PROCESSING_BATCH` | `PROCESSING_BATCH_BATCH_JOB_QUEUE` |
| `order-processor/` | `ORDER_PROCESSOR` | `ORDER_PROCESSOR_SFN_ARN` |
| `notifications/` | `NOTIFICATIONS` | `NOTIFICATIONS_QUEUE_URL` |

Use this prefix consistently in `.env.example`, `conftest.py` fixtures, and
E2E test modules. See [references/secrets-and-config.md](references/secrets-and-config.md).

### Find Lambdas
```
Search for files named main.py, handler.py, app.py, or lambda_function.py
under directories that contain lambda, function, or handler in their path.
Each directory containing such a file is one Lambda function.
```

Record for each Lambda:
- **Component prefix** (derived from directory name)
- **Directory path** and handler file name
- **Handler function name** (look for `def lambda_handler`, `def handler`, or the entry point)
- **Event source**: API Gateway (has `httpMethod`/`requestContext`), S3 (has `Records[].s3`), SQS (has `Records[].body`), SNS, EventBridge, direct invoke
- **AWS services used**: scan imports for `boto3.client(...)` or `boto3.resource(...)` — record each service name (s3, dynamodb, rds, stepfunctions, etc.)
- **Environment variables**: scan for `os.environ[...]` or `os.getenv(...)` calls
- **Validation**: look for pydantic models, jsonschema, or manual validation logic

### Find Batch Jobs
```
Search for directories containing Dockerfile, batch, or job in their name.
Look for the main entry point (main.py, run.py, app.py).
```

Record for each Batch job:
- **Directory path** and entry file
- **Input source**: S3 file, environment variables, command-line args
- **Output target**: S3, database, API call
- **AWS services used**: same scan as Lambda

### Find Step Functions
```
Search for files named *.asl.json, state_machine.json, definition.json,
or CloudFormation templates that define AWS::StepFunctions::StateMachine.
```

Record for each Step Function:
- **Definition file path**
- **States and their types** (Task, Choice, Parallel, Map, Wait, Pass, Fail, Succeed)
- **Lambda ARNs** referenced in Task states
- **Input/output schemas** (if InputPath/OutputPath/ResultPath are defined)
- **Error handling**: Retry and Catch configurations

### Find API Specifications
```
Search for swagger.yml, swagger.yaml, openapi.yml, openapi.yaml, openapi.json,
or API Gateway definitions in CloudFormation/SAM templates.
```

Record:
- **Spec file path**
- **Endpoints**: method + path + request/response schemas
- **Authentication**: API key, IAM, Cognito, custom authorizer
- **Required headers**
- **Server URLs / stage names**

### Find Existing Tests
```
Search for existing test files: test_*.py, *_test.py
Also look for conftest.py, pytest.ini, pyproject.toml [tool.pytest], setup.cfg [tool:pytest]
```

Record:
- **Test directory structure**
- **Existing fixtures in conftest.py**
- **Existing markers and configuration**
- **Test coverage gaps**: which components have no tests?

## Step 2: Choose Test Category

Based on what the user asked, delegate to the appropriate skill:

| User Says | Skill | What It Does |
|-----------|-------|-------------|
| "unit test", "test business logic", "branch coverage", "boundary test" | `aws-unit-testing` | Tests pure logic, every branch and boundary |
| "E2E test", "end-to-end", "full workflow", "test the API" | `aws-e2e-testing` | Tests real deployed endpoints |
| "integration test", "test with S3", "test with DynamoDB" | `aws-integration-testing` | Tests service + mocked AWS |
| "contract test", "schema test", "API contract" | `aws-contract-testing` | Validates schemas offline |
| "performance", "benchmark", "latency", "memory" | `aws-perf-load-testing` | Benchmarks and profiling |
| "load test", "stress test", "concurrent users" | `aws-perf-load-testing` | Locust-based load testing |
| "all tests", "full test suite", "scaffold tests" | All skills | Run discovery → scaffold → generate |

## Secrets & Configuration

Before generating any tests, ensure secrets management is set up correctly.
See [references/secrets-and-config.md](references/secrets-and-config.md) for full details.

**Key rules:**
- **Never** hardcode API keys, tokens, passwords, or URLs in test files
- Two strategies for managing secrets (see [references/secrets-and-config.md](references/secrets-and-config.md)):
  - **Strategy A**: `.env` files (gitignored) + `os.getenv()` — quick local dev
  - **Strategy B**: AWS Secrets Manager + SSM Parameter Store — production teams, shared secrets
- **AWS credentials**: use the default AWS profile (`~/.aws/credentials`) — accessed via `boto3` automatically
- Unit/integration/contract tests need only fake AWS credentials (`"testing"` via moto)
- E2E/load tests load real credentials from `.env` or Secrets Manager / SSM with `pytest.skip()` fallback
- Scaffold generates `.env.example` (committed) and `.gitignore` entry for `.env`

## Step 3: Read Code and Generate Tests

This is the core differentiator. Do NOT use generic templates. Instead:

### For each handler/function to test:

1. **Read the full source code** of the handler file
2. **Identify all code paths**:
   - Happy path (normal execution)
   - Each if/elif/else branch
   - Each try/except block (what errors are caught?)
   - Each early return or guard clause
   - Each loop iteration pattern
3. **Identify AWS interactions**:
   - Every `boto3` call → what service, method, and expected parameters?
   - What does the code do with the response?
   - What happens if the AWS call fails?
4. **Identify data transformations**:
   - Input parsing and validation
   - Business logic computations
   - Output formatting
5. **Generate one test per code path**:
   - Name tests descriptively: `test_<function>_<scenario>_<expected_outcome>`
   - Include both positive and negative cases
   - Mock external dependencies at the correct level
   - Assert on specific return values, not just status codes

### Test Naming Convention
```python
def test_handler_valid_get_request_returns_200():
def test_handler_missing_path_param_returns_400():
def test_handler_s3_object_not_found_returns_404():
def test_handler_dynamodb_condition_check_fails_returns_409():
def test_handler_unexpected_error_returns_500():
```

## Step 4: Scaffold Test Infrastructure

If the project doesn't have a test directory, create one:

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures (auto-generated from discovery)
├── pytest.ini               # Markers: unit, contract, integration, e2e, performance, load
├── unit/                    # Pure business logic tests
│   └── __init__.py
├── contract/
│   └── __init__.py
├── integration/
│   └── __init__.py
├── e2e/
│   └── __init__.py
├── performance/
│   └── __init__.py
├── load/
│   └── __init__.py
└── reports/                 # Output directory
.env.example                 # Non-secret config template (committed)
.env                         # Non-secret config values (gitignored, NEVER committed)
```

### conftest.py Generation

Generate `conftest.py` from discovery results:

```python
# Auto-generated fixtures based on project discovery

import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- Environment fixtures ---
@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Reset env vars between tests."""
    # Set each env var discovered in Step 1
    for key, default in DISCOVERED_ENV_VARS.items():
        monkeypatch.setenv(key, default)

# --- AWS credential fixtures ---
@pytest.fixture
def aws_credentials(monkeypatch):
    """Mock AWS credentials for moto."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

# --- Lambda context fixture ---
@pytest.fixture
def mock_lambda_context():
    ctx = MagicMock()
    ctx.function_name = "test-function"
    ctx.memory_limit_in_mb = 256
    ctx.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789:function:test"
    ctx.get_remaining_time_in_millis.return_value = 30000
    return ctx

# --- API spec fixture (if OpenAPI found) ---
@pytest.fixture(scope="session")
def api_spec():
    spec_path = REPO_ROOT / "PATH_TO_SPEC"  # Replace with discovered path
    if spec_path.exists():
        import yaml
        return yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    return None

@pytest.fixture(scope="session")
def api_schemas(api_spec):
    if api_spec:
        return api_spec.get("components", {}).get("schemas", {})
    return {}
```

## Step 5: Run Tests

### Commands Reference

| Category | Command |
|----------|---------|
| Unit | `pytest tests/unit/ -v -m unit --cov=src/ --cov-branch` |
| Contract | `pytest tests/contract/ -v -m contract --tb=short` |
| Integration | `pytest tests/integration/ -v -m integration --tb=short` |
| E2E | `pytest tests/e2e/ -v -m e2e -s` (loads secrets from `.env` or SM/SSM) |
| Performance | `pytest tests/performance/ -v --benchmark-only` |
| Load | `locust -f tests/load/locustfile.py --host=$LOAD_TEST_HOST --users=50 --run-time=5m --headless` |
| All offline | `pytest tests/unit/ tests/contract/ tests/integration/ tests/performance/ -v` |
| With reports | `pytest tests/ -v --junitxml=tests/reports/junit.xml --html=tests/reports/report.html --self-contained-html` |

### Using the Orchestrator Script

```bash
python scripts/run_tests.py unit                 # Unit tests only
python scripts/run_tests.py contract             # Run one category
python scripts/run_tests.py all                  # All offline categories (unit+contract+integration+performance)
python scripts/run_tests.py e2e                  # E2E (tests self-skip if per-component env vars missing)
python scripts/run_tests.py load --users 100     # Load test (requires --base-url or LOAD_TEST_HOST)
python scripts/run_tests.py full                 # Everything: offline + E2E (tests self-skip if secrets unavailable)
```

## Step 6: Analyze & Fix

### Parse Results
```bash
python scripts/analyze_results.py                # All reports
python scripts/analyze_results.py --json          # Machine-readable
```

### Failure Classification

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| `ValidationError` in contract test | Schema mismatch | Update OpenAPI spec or handler code |
| `ClientError` in integration test | Wrong boto3 call | Fix service name, method, or params |
| `AssertionError` on response body | Handler logic bug | Fix the handler's data transformation |
| `TimeoutError` in E2E | Slow downstream | Check Lambda timeout, DB query, SFN wait |
| `ConnectionError` in E2E | Wrong URL or no VPN | Verify API_BASE_URL and network access |
| Benchmark regression | Code got slower | Profile with cProfile/tracemalloc |
| Load test error rate > 1% | Throttling or crashes | Check CloudWatch, scale up, optimize |

### Iterative Fix Loop

```
1. RUN    → Execute failing test(s) only
2. READ   → Parse the failure traceback
3. TRACE  → Find the failing line in handler code
4. FIX    → Apply minimal fix
5. RE-RUN → Run ONLY the previously failing test
6. REPEAT → Until green
7. FULL   → Run full category suite to check for regressions
```

## Safety Constraints

- **Never** run load/E2E tests against production without explicit user confirmation
- E2E test data must use identifiable prefixes (e.g., `E2E-TEST-`, `LOAD-TEST-`)
- Load tests must have `--run-time` set (no unbounded runs)
- Only use documented commands — never invent new ones
- All tests must be idempotent (safe to re-run)
- Never expose real credentials in test code — use moto for mocks, `.env` or Secrets Manager / SSM for real secrets
