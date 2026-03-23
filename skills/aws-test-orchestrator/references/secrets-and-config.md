# Secrets & Configuration Management for Tests

Best practices for managing API keys, tokens, credentials, and environment
configuration so tests run safely without hardcoded secrets.

## Golden Rule

**Never commit secrets to version control.** Not in test files, not in
conftest.py, not in config files. No exceptions.

## Two Strategies

Choose the approach that fits your team, or combine them:

| Strategy | Best For | Secrets Location |
|----------|----------|-----------------|
| **A. Environment Variables + `.env`** | Quick local dev, small teams | `.env` file (gitignored) |
| **B. AWS Secrets Manager / SSM Parameter Store** | Production teams, CI/CD, shared secrets | Secrets Manager + SSM |

Both strategies share:
- Unit/integration/contract tests use **fake** AWS credentials (`"testing"`) via moto
- **AWS access** for E2E/load tests uses the default profile (`~/.aws/credentials`)
  accessed via `boto3` — never set `AWS_ACCESS_KEY_ID` as an env var for real access
- `.env` file is always gitignored

---

## Strategy A: Environment Variables + `.env` Files

Simple and self-contained. Good for getting started quickly.

### 1. Create `.env.example` (committed to git)

Use **component-prefixed** env var names so multiple services can coexist
in the same repo without collisions (e.g., `ORDERS_API_BASE_URL`,
`PAYMENTS_SFN_ARN`).

```env
# .env.example — copy to .env and fill in real values
# .env is gitignored and NEVER committed
#
# Naming convention: {COMPONENT}_{VAR_NAME}
# Derive COMPONENT from the service directory name uppercased,
# e.g. orders-api/ → ORDERS_API, processing-batch/ → PROCESSING_BATCH

# ── AWS (for moto-based tests — use fake values) ──
AWS_DEFAULT_REGION=us-east-1

# ── Handler environment variables (non-secret, per-component) ──
# ORDERS_API_TABLE_NAME=orders-table
# PAYMENTS_TABLE_NAME=payments-table
# UPLOADS_BUCKET_NAME=uploads-bucket
# NOTIFICATIONS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789/notifications-queue

# ── E2E tests (real values, per-component) ──
# ORDERS_API_BASE_URL=https://xxx.execute-api.us-east-1.amazonaws.com/dev
# ORDERS_API_KEY=your-orders-api-key
# PAYMENTS_API_BASE_URL=https://yyy.execute-api.us-east-1.amazonaws.com/dev
# PAYMENTS_API_KEY=your-payments-api-key

# ── Load tests (per-component) ──
# ORDERS_LOAD_TEST_HOST=https://xxx.execute-api.us-east-1.amazonaws.com/dev

# ── Step Function tests (per-component) ──
# ORDER_PROCESSOR_SFN_ARN=arn:aws:states:us-east-1:123456789:stateMachine:order-processor

# ── Batch tests (per-component) ──
# DATA_INGESTION_BATCH_JOB_QUEUE=data-ingestion-queue
# DATA_INGESTION_BATCH_JOB_DEFINITION=data-ingestion-job-def

# ── Database tests (for testcontainers, auto-configured) ──
# DB_HOST=localhost
# DB_PORT=5432
# DB_NAME=testdb
# DB_USER=testuser
# DB_PASSWORD=testpassword
```

### 2. `.gitignore` entry (critical)

```gitignore
# Environment / secrets
.env
.env.local
.env.*.local
*.env
!.env.example
```

### 3. Load `.env` in `conftest.py`

```python
# tests/conftest.py
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv():
    """Load .env file if it exists. No dependency on python-dotenv."""
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
        value = value.strip().strip("'\"")
        # Only set if not already in environment (env vars take precedence)
        if key not in os.environ:
            os.environ[key] = value


# Load .env BEFORE any test collection
_load_dotenv()


@pytest.fixture(autouse=True)
def aws_env_vars(monkeypatch):
    """Set safe AWS credentials for moto (override real creds)."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
```

### 4. Access secrets in tests via component-prefixed fixtures

Each E2E test module sets its `COMPONENT` prefix and reads per-component
env vars. You can also create reusable fixtures in `tests/e2e/conftest.py`.

```python
# tests/e2e/conftest.py
import os
import pytest


def component_env(component: str, var: str) -> str | None:
    """Read a component-prefixed env var: {COMPONENT}_{VAR}."""
    return os.getenv(f"{component}_{var}")


# Example: per-component fixtures for orders-api
# (Repeat or parameterise for each component as needed)

@pytest.fixture(scope="session")
def orders_api_base_url():
    url = component_env("ORDERS", "API_BASE_URL")
    if not url:
        pytest.skip("ORDERS_API_BASE_URL not set")
    return url.rstrip("/")


@pytest.fixture(scope="session")
def orders_api_key():
    key = component_env("ORDERS", "API_KEY")
    if not key:
        pytest.skip("ORDERS_API_KEY not set")
    return key


@pytest.fixture(scope="session")
def orders_api_session(orders_api_base_url, orders_api_key):
    """Pre-configured requests session for orders-api."""
    import requests
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "x-api-key": orders_api_key,
    })
    s.base_url = orders_api_base_url
    return s
```

---

## Strategy B: AWS Secrets Manager / SSM Parameter Store

Recommended for production teams. Follows AWS best practice: store each value
in the right service based on sensitivity and rotation needs. The test code
uses generic helpers — adapt the names and paths to your project structure.

### How It Works

- **AWS authentication**: `boto3` automatically uses the default profile configured
  in `~/.aws/credentials` and `~/.aws/config`. No AWS keys in env vars or `.env`.
- **Sensitive secrets** (API keys, DB passwords, OAuth tokens): stored as individual
  entries in **AWS Secrets Manager** — one secret per value. These are values that
  benefit from rotation, auditing, and fine-grained IAM access control.
- **Configuration parameters** (ARNs, endpoint URLs, table names, queue names):
  stored in **SSM Parameter Store** (`String` for non-sensitive, `SecureString`
  for sensitive). Many teams already populate these from CloudFormation/CDK outputs.
- **Non-sensitive constants** already defined in service code (e.g., default region,
  hard-coded table names) don't need to be duplicated — test code can import or
  read them directly.

### What Belongs Where

Secrets and parameters can be **per-service** or **shared** across services.
A DB password used by three Lambdas is stored once and referenced by all three.

| Value Type | Store | Shared? | Example |
|-----------|-------|---------|--------|
| API key / auth token | Secrets Manager | Per-service or shared | `api-keys/stripe` |
| DB password | Secrets Manager | Usually shared | `rds/mydb/password` |
| OAuth client secret | Secrets Manager | Usually shared | `auth/google/client-secret` |
| API endpoint URL | SSM Parameter Store | Per-service | `/myapp/dev/orders/api-url` |
| Step Function ARN | SSM Parameter Store | Per-service | `/myapp/dev/sfn/order-processor` |
| DynamoDB table name | SSM Parameter Store or code | Shared or per-service | `/myapp/dev/tables/orders` |
| SQS queue URL | SSM Parameter Store or code | Shared or per-service | `/myapp/dev/queues/notifications` |
| Sensitive config param | SSM (`SecureString`) | Varies | `/myapp/dev/payments/webhook-secret` |

### Common Naming Patterns

Teams organise secret/parameter names differently. Here are common patterns
you may encounter — pick one or adapt to your team's existing convention:

| Pattern | Secrets Manager | SSM Parameter Store |
|---------|----------------|--------------------|
| **By environment** | `dev/db-password`, `prod/db-password` | `/dev/orders/api-url`, `/prod/orders/api-url` |
| **By app + env** | `myapp/dev/stripe-key` | `/myapp/dev/orders/api-url` |
| **By service** | `orders-api/api-key` | `/orders-api/base-url` |
| **Flat** | `ORDERS_API_KEY` | `/ORDERS_API_BASE_URL` |
| **CloudFormation outputs** | (rarely used) | `/cfn/MyStack/OrdersApiUrl` |

> **The helpers below accept any name/path.** When generating tests, ask the
> user (or scan IaC templates / existing SSM parameters) for their project's
> naming convention. Don't assume a specific pattern.

### 1. Store Secrets and Parameters in AWS

Examples below use one naming style — substitute your own.
Note that a single secret (like a DB password) can be referenced by
multiple services.

```bash
# ── Secrets Manager: sensitive values ──
# Shared DB password (used by multiple services)
aws secretsmanager create-secret \
  --name myapp/dev/db-password \
  --secret-string "strong-db-password"

# Per-service API key
aws secretsmanager create-secret \
  --name myapp/dev/stripe-key \
  --secret-string "sk-live-..."

# ── SSM Parameter Store: config values ──
# Per-service endpoint (non-sensitive)
aws ssm put-parameter \
  --name /myapp/dev/orders/api-url \
  --type String \
  --value "https://xxx.execute-api.us-east-1.amazonaws.com/dev"

# SFN ARN
aws ssm put-parameter \
  --name /myapp/dev/sfn/order-processor \
  --type String \
  --value "arn:aws:states:us-east-1:123456789:stateMachine:order-processor"

# SecureString (sensitive but doesn't need rotation)
aws ssm put-parameter \
  --name /myapp/dev/payments/webhook-secret \
  --type SecureString \
  --value "whsec_..."
```

### 2. Create `.env.example` for Local Overrides (committed to git)

Some teams skip `.env` entirely with Strategy B — all config comes from AWS.
But you can still use `.env` for local overrides or offline tests.

```env
# .env.example — optional local overrides
# .env is gitignored and NEVER committed
# NOTE: Secrets are in Secrets Manager. Config is in SSM Parameter Store.
#       This file is only needed if you want to override values locally
#       or run tests without AWS access.

AWS_DEFAULT_REGION=us-east-1

# ── Override SSM params locally (optional) ──
# ORDERS_API_BASE_URL=https://xxx.execute-api.us-east-1.amazonaws.com/dev
# ORDER_PROCESSOR_SFN_ARN=arn:aws:states:us-east-1:123456789:stateMachine:order-processor
# DATA_INGESTION_BATCH_JOB_QUEUE=data-ingestion-queue
```

### 3. Generic Helpers in `conftest.py`

```python
# tests/conftest.py
import json
import os
from pathlib import Path

import boto3
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")


def _load_dotenv():
    """Load .env file for local overrides. No dependency on python-dotenv."""
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
        value = value.strip().strip("'\"")
        if key not in os.environ:
            os.environ[key] = value


def _get_secret(secret_name: str) -> str:
    """Retrieve a single secret value from AWS Secrets Manager."""
    client = boto3.client("secretsmanager", region_name=_REGION)
    resp = client.get_secret_value(SecretId=secret_name)
    return resp["SecretString"]


def _get_parameter(param_name: str, decrypt: bool = False) -> str:
    """Retrieve a single value from SSM Parameter Store."""
    client = boto3.client("ssm", region_name=_REGION)
    resp = client.get_parameter(Name=param_name, WithDecryption=decrypt)
    return resp["Parameter"]["Value"]


# Load .env BEFORE any test collection (for local overrides)
_load_dotenv()


@pytest.fixture(autouse=True)
def aws_env_vars(monkeypatch):
    """Set fake AWS credentials for moto-based tests (unit/integration).

    This ensures moto never accidentally hits real AWS.
    E2E/load test fixtures create their own boto3 clients at session/module
    scope before this per-test monkeypatch runs.
    """
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
```

### 4. Access Secrets and Parameters in E2E Tests

Each E2E test module resolves its own values using `_resolve()`. A single
secret (e.g., a shared DB password) can appear in multiple fixtures — the
helper caches nothing, but the session-scoped fixture does.

Provide thin fixtures so tests stay readable and skip gracefully when a
value is unavailable. Adapt the names to your project's convention.

```python
# tests/e2e/conftest.py
import os
import pytest
import boto3

_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")


def _get_secret(secret_name: str) -> str:
    """Retrieve a secret from AWS Secrets Manager."""
    client = boto3.client("secretsmanager", region_name=_REGION)
    resp = client.get_secret_value(SecretId=secret_name)
    return resp["SecretString"]


def _get_parameter(param_name: str, decrypt: bool = False) -> str:
    """Retrieve a parameter from SSM Parameter Store."""
    client = boto3.client("ssm", region_name=_REGION)
    resp = client.get_parameter(Name=param_name, WithDecryption=decrypt)
    return resp["Parameter"]["Value"]


def _resolve(
    env_var: str,
    aws_name: str | None = None,
    *,
    source: str = "ssm",
    decrypt: bool = False,
) -> str | None:
    """Resolve a config value: env var first, then AWS (SSM or Secrets Manager).

    Allows local `.env` overrides while falling back to AWS stores.
    """
    value = os.getenv(env_var)
    if value:
        return value
    if not aws_name:
        return None
    try:
        if source == "secret":
            return _get_secret(aws_name)
        return _get_parameter(aws_name, decrypt=decrypt)
    except Exception:
        return None


# ── Shared secrets (used by multiple services) ──

@pytest.fixture(scope="session")
def db_password():
    """Shared DB password — same secret used by orders, payments, etc."""
    pw = _resolve("DB_PASSWORD", "myapp/dev/db-password", source="secret")
    if not pw:
        pytest.skip("DB password not available")
    return pw


# ── Per-service fixtures ──
# Adapt secret/param names to YOUR naming convention.

@pytest.fixture(scope="session")
def orders_api_base_url():
    url = _resolve("ORDERS_API_BASE_URL", "/myapp/dev/orders/api-url")
    if not url:
        pytest.skip("orders-api base URL not available")
    return url.rstrip("/")


@pytest.fixture(scope="session")
def orders_api_key():
    key = _resolve("ORDERS_API_KEY", "myapp/dev/stripe-key", source="secret")
    if not key:
        pytest.skip("orders-api API key not available")
    return key


@pytest.fixture(scope="session")
def orders_api_session(orders_api_base_url, orders_api_key):
    """Pre-configured requests session for orders-api."""
    import requests
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "x-api-key": orders_api_key,
    })
    s.base_url = orders_api_base_url
    return s


# ── Multiple services sharing the same secret ──
# Both orders and payments need the DB password:
#   def test_orders_db(db_password): ...
#   def test_payments_db(db_password): ...
# The fixture is defined once; any test can request it.
```

### 5. Boto3 Clients for E2E Tests (Default Profile)

E2E and load tests that call AWS services directly create their own boto3
clients **without** fake credentials. These use the default profile.
Resource identifiers (ARNs, queue names) come from SSM Parameter Store,
env vars, or are known constants in the service code.

```python
# tests/e2e/conftest.py — continued

@pytest.fixture(scope="module")
def sfn_client():
    """Step Functions client using default AWS profile."""
    return boto3.client("stepfunctions", region_name=_REGION)


@pytest.fixture(scope="module")
def batch_client():
    """Batch client using default AWS profile."""
    return boto3.client("batch", region_name=_REGION)
```

> **Note:** The `aws_env_vars` autouse fixture in the root conftest.py sets fake
> credentials for moto. E2E fixtures that need real AWS access must create their
> boto3 clients at **session or module scope** (before the per-test monkeypatch
> overrides them), or create clients in a scope that is not affected.

---

## CI/CD Integration

### GitHub Actions — Strategy A (env vars)

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -e ".[all]"

      # Unit + Integration + Contract — no secrets needed
      - name: Run offline tests
        run: |
          pytest tests/unit/ tests/integration/ tests/contract/ \
            -v --tb=short \
            --junitxml=tests/reports/offline_results.xml

      # E2E tests — only on main, using GitHub Secrets
      # Set per-component env vars from GitHub Secrets
      - name: Run E2E tests
        if: github.ref == 'refs/heads/main'
        env:
          ORDERS_API_BASE_URL: ${{ secrets.ORDERS_API_BASE_URL }}
          ORDERS_API_KEY: ${{ secrets.ORDERS_API_KEY }}
          # Add more components as needed:
          # PAYMENTS_API_BASE_URL: ${{ secrets.PAYMENTS_API_BASE_URL }}
        run: |
          pytest tests/e2e/ -v -m e2e --tb=short \
            --junitxml=tests/reports/e2e_results.xml
```

### GitHub Actions — Strategy B (Secrets Manager / SSM)

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -e ".[all]"

      # Unit + Integration + Contract — no secrets needed (moto uses fake creds)
      - name: Run offline tests
        run: |
          pytest tests/unit/ tests/integration/ tests/contract/ \
            -v --tb=short \
            --junitxml=tests/reports/offline_results.xml

      # E2E tests — only on main, using AWS role for Secrets Manager + SSM access
      - name: Configure AWS credentials
        if: github.ref == 'refs/heads/main'
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1

      - name: Run E2E tests
        if: github.ref == 'refs/heads/main'
        run: |
          pytest tests/e2e/ -v -m e2e --tb=short \
            --junitxml=tests/reports/e2e_results.xml
```

> In CI with Strategy B, use IAM role assumption (OIDC) rather than storing AWS
> keys as GitHub Secrets. The role needs `secretsmanager:GetSecretValue` and
> `ssm:GetParameter` / `ssm:GetParametersByPath` permissions.

## What Goes Where

| Value Type | Strategy A (`.env`) | Strategy B (SM + SSM) | Unit Tests | Integration |
|-----------|--------------------|-----------------------------|-----------|------------|
| AWS credentials | Default profile | Default profile | Fake (`testing`) | Fake (`testing`) |
| API keys / tokens | `.env` / CI secret | Secrets Manager (individual) | Not needed | Not needed |
| DB passwords | `.env` / CI secret | Secrets Manager (individual) | Not needed | Testcontainers |
| API endpoint URLs | `.env` / CI secret | SSM Parameter Store (`String`) | Not needed | Not needed |
| Table / bucket names | `.env` or env vars | SSM Parameter Store (`String`) or code | From env | From env |
| SFN / resource ARNs | `.env` / CI secret | SSM Parameter Store (`String`) | Not needed | Not needed |
| Queue URLs | `.env` or env vars | SSM Parameter Store (`String`) or code | From env | From env |
| Webhook secrets | `.env` / CI secret | SSM Parameter Store (`SecureString`) | Not needed | Not needed |

## 1-Click Setup for New Developers

### Strategy A (`.env`)

```bash
# Step 1: Configure AWS default profile (one-time)
aws configure
# This creates ~/.aws/credentials — used by boto3 automatically

# Step 2: Copy the example env file
cp .env.example .env

# Step 3: Edit .env with your values (if running E2E/load tests)
# For unit/integration/contract tests, the defaults work as-is

# Step 4: Run all offline tests
pytest tests/unit/ tests/integration/ tests/contract/ tests/performance/ -v

# Or use the orchestrator
python scripts/run_tests.py all
```

### Strategy B (Secrets Manager + SSM)

```bash
# Step 1: Configure AWS default profile (one-time)
aws configure
# This creates ~/.aws/credentials — used by boto3 automatically

# Step 2 (optional): Copy .env for local overrides
cp .env.example .env
# Most config comes from SSM — .env is only for local overrides

# Step 3: Verify secrets and params exist in AWS (use YOUR naming convention)
aws secretsmanager get-secret-value --secret-id myapp/dev/db-password
aws ssm get-parameter --name /myapp/dev/orders/api-url
# If missing, create them (see "Store Secrets and Parameters" section)

# Step 4: Run all offline tests (no AWS access needed)
pytest tests/unit/ tests/integration/ tests/contract/ tests/performance/ -v

# Step 5: Run E2E tests (requires default profile + SM/SSM access)
pytest tests/e2e/ -v -m e2e

# Or use the orchestrator
python scripts/run_tests.py all    # offline only
python scripts/run_tests.py full   # offline + E2E
```
