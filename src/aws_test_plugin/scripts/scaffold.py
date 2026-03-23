#!/usr/bin/env python3
"""
Scaffold test infrastructure for an AWS Python project.

Usage:
    python scaffold.py [--project-root /path/to/project]

Discovers Lambda handlers, Batch jobs, Step Functions, and API specs,
then creates the test directory structure with conftest.py and pytest.ini.
"""

import argparse
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

HANDLER_FILENAMES = {"main.py", "handler.py", "app.py", "lambda_function.py"}
BATCH_INDICATORS = {"Dockerfile", "docker-compose.yml"}
SFN_PATTERNS = {"*.asl.json"}
API_SPEC_NAMES = {"swagger.yml", "swagger.yaml", "openapi.yml", "openapi.yaml"}


def discover_lambdas(root: Path) -> list[Path]:
    """Find Lambda handler directories."""
    results = []
    for dirpath, _dirs, files in os.walk(root):
        dp = Path(dirpath)
        if dp.name in ("node_modules", ".git", "__pycache__", ".aws-sam"):
            continue
        for hf in HANDLER_FILENAMES:
            if hf in files and "test" not in dp.name.lower():
                results.append(dp)
                break
    return results


def discover_batch_jobs(root: Path) -> list[Path]:
    """Find Batch job directories (contain Dockerfile)."""
    results = []
    for dirpath, _dirs, files in os.walk(root):
        dp = Path(dirpath)
        if any(ind in files for ind in BATCH_INDICATORS):
            if "batch" in dp.name.lower() or "batch" in str(dp).lower():
                results.append(dp)
    return results


def discover_step_functions(root: Path) -> list[Path]:
    """Find Step Function ASL definitions."""
    results = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith(".asl.json"):
                results.append(Path(dirpath) / f)
    return results


def discover_api_specs(root: Path) -> list[Path]:
    """Find OpenAPI/Swagger spec files."""
    results = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f in API_SPEC_NAMES:
                results.append(Path(dirpath) / f)
    return results


# ---------------------------------------------------------------------------
# Template generators
# ---------------------------------------------------------------------------

CONFTEST_TEMPLATE = '''\
"""Shared fixtures for all test types.

Secrets and config are loaded from .env (never hardcoded in test files).
Copy .env.example to .env and fill in values for E2E/load tests.
Unit/integration/contract tests work with the defaults.
"""
import os
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv():
    """Load .env file if present (no python-dotenv dependency)."""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\'\'\"")
        if key not in os.environ:
            os.environ[key] = value


_load_dotenv()


@pytest.fixture(autouse=True)
def aws_env_vars(monkeypatch):
    """Set safe fake AWS credentials for moto (prevents real AWS calls)."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def lambda_context():
    """Fake Lambda context object."""
    ctx = MagicMock()
    ctx.function_name = "test-function"
    ctx.memory_limit_in_mb = 256
    ctx.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789:function:test"
    ctx.get_remaining_time_in_millis.return_value = 30000
    return ctx


@pytest.fixture
def api_gw_event():
    """Factory for API Gateway proxy events."""
    def _make(method="GET", path="/", body=None, path_params=None,
              query_params=None, headers=None):
        event = {
            "httpMethod": method,
            "path": path,
            "pathParameters": path_params or {},
            "queryStringParameters": query_params or {},
            "headers": headers or {"Content-Type": "application/json"},
            "body": json.dumps(body) if body else None,
            "requestContext": {"stage": "test"},
        }
        return event
    return _make
'''

PYTEST_INI_TEMPLATE = """\
[pytest]
testpaths = tests
markers =
    unit: Unit tests (pure business logic, no external dependencies)
    integration: Integration tests (moto/testcontainers)
    contract: API contract validation tests
    e2e: End-to-end tests (requires deployed environment)
    performance: Performance benchmark tests
    load: Load/stress tests (Locust)

addopts =
    -v
    --tb=short
    --strict-markers
"""

ENV_EXAMPLE_TEMPLATE = """\
# .env.example — copy to .env and fill in real values
# .env is gitignored and NEVER committed
#
# Naming convention: {COMPONENT}_{VAR_NAME}
# Derive COMPONENT from the service directory name uppercased,
# e.g. orders-api/ → ORDERS_API, processing-batch/ → PROCESSING_BATCH
#
# Unit, integration, contract, and performance tests work without any values.
# Only fill in E2E/load test values when you need to test against a deployed API.
# Fake AWS credentials for moto are set automatically in conftest.py.

AWS_DEFAULT_REGION=us-east-1

# ── Handler environment variables (per-component, adjust per project) ──
# ORDERS_API_TABLE_NAME=orders-table
# UPLOADS_BUCKET_NAME=uploads-bucket
# NOTIFICATIONS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789/notifications-queue

# ── E2E tests (per-component, uncomment and set real values) ──
# ORDERS_API_BASE_URL=https://xxx.execute-api.us-east-1.amazonaws.com/dev
# ORDERS_API_KEY=your-api-key-here
# PAYMENTS_API_BASE_URL=https://yyy.execute-api.us-east-1.amazonaws.com/dev

# ── Step Function tests (per-component) ──
# ORDER_PROCESSOR_SFN_ARN=arn:aws:states:us-east-1:123456789:stateMachine:order-processor

# ── Batch tests (per-component) ──
# DATA_INGESTION_BATCH_JOB_QUEUE=data-ingestion-queue
# DATA_INGESTION_BATCH_JOB_DEFINITION=data-ingestion-job-def

# ── Database tests (testcontainers auto-configures, but override here if needed) ──
# DB_HOST=localhost
# DB_PORT=5432
# DB_NAME=testdb
# DB_USER=testuser
# DB_PASSWORD=testpassword
"""

GITKEEP = ""


def create_test_structure(root: Path, lambdas: list, batches: list):
    """Create test directory tree."""
    tests_dir = root / "tests"
    dirs = [
        tests_dir / "unit",
        tests_dir / "integration",
        tests_dir / "contract",
        tests_dir / "e2e",
        tests_dir / "performance",
        tests_dir / "load",
        tests_dir / "fixtures",
        tests_dir / "reports",
    ]

    created = []
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        gitkeep = d / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text(GITKEEP)
        created.append(str(d))

    # conftest.py
    conftest = tests_dir / "conftest.py"
    if not conftest.exists():
        conftest.write_text(CONFTEST_TEMPLATE)
        created.append(str(conftest))

    # pytest.ini
    pytest_ini = root / "pytest.ini"
    if not pytest_ini.exists():
        pytest_ini.write_text(PYTEST_INI_TEMPLATE)
        created.append(str(pytest_ini))

    # .env.example (committed — template for developers)
    env_example = root / ".env.example"
    if not env_example.exists():
        env_example.write_text(ENV_EXAMPLE_TEMPLATE)
        created.append(str(env_example))

    # Ensure .env is gitignored
    gitignore = root / ".gitignore"
    env_ignored = False
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        env_ignored = ".env" in content
    if not env_ignored:
        with open(gitignore, "a", encoding="utf-8") as f:
            f.write("\n# Environment / secrets\n.env\n.env.local\n.env.*.local\n!.env.example\n")
        created.append(str(gitignore))

    return created


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Scaffold AWS test infrastructure")
    parser.add_argument(
        "--project-root",
        "-r",
        default=".",
        help="Root of the AWS Python project (default: current directory)",
    )
    args = parser.parse_args()
    root = Path(args.project_root).resolve()

    print(f"Scanning {root} ...\n")

    lambdas = discover_lambdas(root)
    batches = discover_batch_jobs(root)
    sfns = discover_step_functions(root)
    specs = discover_api_specs(root)

    print(f"Found {len(lambdas)} Lambda handler(s):")
    for lam in lambdas:
        print(f"  - {lam.relative_to(root)}")

    print(f"\nFound {len(batches)} Batch job(s):")
    for b in batches:
        print(f"  - {b.relative_to(root)}")

    print(f"\nFound {len(sfns)} Step Function definition(s):")
    for s in sfns:
        print(f"  - {s.relative_to(root)}")

    print(f"\nFound {len(specs)} API spec(s):")
    for sp in specs:
        print(f"  - {sp.relative_to(root)}")

    print("\nCreating test structure...")
    created = create_test_structure(root, lambdas, batches)
    for c in created:
        rel = Path(c).relative_to(root)
        print(f"  + {rel}")

    print("\nDone! Next steps:")
    print("  1. Install test dependencies: pip install 'aws-test-plugin[test]'")
    print("  2. Ask Claude to generate tests: 'Write integration tests for my Lambdas'")
    print("  3. Run tests: pytest tests/integration/ -m integration")


if __name__ == "__main__":
    main()
