# Secrets and configuration for AWS tests

Keep credentials and secrets out of source, reports, logs, and command history.
Use the project's existing configuration names and secret storage. The component
prefix examples below are a fallback when no convention exists.

## Separate offline and deployed runs

Unit, integration, contract, and local performance tests use fake credentials
with moto or service stubs. Set credentials before importing handlers that create
AWS clients. Fake credentials alone do not prevent HTTP or AWS requests.

The packaged runner supplies fake credentials in each offline subprocess before
pytest collection. It does not load `.env` for offline categories. When using
pytest directly, configure the same boundary in the project's offline harness.
Request the scaffold's `aws_env_vars` fixture before constructing mocked clients.
Do not make this fixture autouse across a mixed offline and E2E suite.

Run deployed tests separately. Select the endpoint, resource ARNs, account,
region, and profile or CI role before execution. Review the selected tests for
writes, cleanup, and cost. Restrict the role to the test resources it needs.
Resource prefixes identify test data; they do not establish ownership or grant
permission to delete existing resources.

## Strategy A: environment variables and local `.env`

Commit a placeholder `.env.example` and ignore local secret files:

```gitignore
.env
.env.*
!.env.example
```

```env
# .env.example: placeholders only
# ORDERS_API_BASE_URL=https://example.execute-api.us-east-1.amazonaws.com/test
# ORDERS_API_KEY=replace-locally
# ORDER_PROCESSOR_SFN_ARN=arn:aws:states:us-east-1:123456789012:stateMachine:test-workflow
# AWS_PROFILE=selected-test-profile
# AWS_DEFAULT_REGION=us-east-1
# AWS_EXPECTED_ACCOUNT_ID=123456789012
```

The runner loads `.env` for `e2e`, `load`, and the E2E phase of `full`.
Existing environment values take precedence. Its loader supports literal
`KEY=value` pairs and surrounding quotes. It does not expand variables or run
shell expressions. Use the project's existing loader if richer syntax is needed.

Keep `.env` loading in deployed test configuration, outside shared offline
`conftest.py`. Avoid printing config dictionaries or secret values in assertions.

## Strategy B: Secrets Manager and SSM Parameter Store

Use Secrets Manager for rotated secrets and SSM for configuration. Reuse existing
parameter names and project helpers. Do not create secrets or scan an account
merely to discover naming conventions. Read IaC and project documentation first.

Use an explicitly selected profile for local work or the configured CI role.
Verify the account and region before reading secrets or running deployed tests.
This example belongs in `tests/e2e/conftest.py`:

```python
import os
from functools import lru_cache

import boto3
import pytest


@lru_cache(maxsize=1)
def _aws_session():
    region = os.getenv("AWS_DEFAULT_REGION")
    expected_account = os.getenv("AWS_EXPECTED_ACCOUNT_ID")
    if not region or not expected_account:
        pytest.fail("Set the deployed test region and expected AWS account")
    session = boto3.Session(
        profile_name=os.getenv("AWS_PROFILE"),
        region_name=region,
    )
    identity = session.client("sts").get_caller_identity()
    if identity["Account"] != expected_account:
        pytest.fail("AWS identity does not match the expected test account")
    return session


def _get_secret(name: str) -> str:
    client = _aws_session().client("secretsmanager")
    return client.get_secret_value(SecretId=name)["SecretString"]


def _get_parameter(name: str, decrypt: bool = False) -> str:
    client = _aws_session().client("ssm")
    return client.get_parameter(Name=name, WithDecryption=decrypt)["Parameter"]["Value"]


def _resolve(env_var: str, aws_name: str | None = None, *, source: str = "ssm") -> str | None:
    value = os.getenv(env_var)
    if value:
        return value
    if not aws_name:
        return None
    if source == "secret":
        return _get_secret(aws_name)
    if source == "ssm":
        return _get_parameter(aws_name)
    raise ValueError("Expected source 'secret' or 'ssm'")


@pytest.fixture(scope="session")
def orders_api_base_url():
    value = _resolve("ORDERS_API_BASE_URL", "/myapp/test/orders/api-url")
    if not value:
        pytest.fail("Required orders API target is unavailable")
    return value.rstrip("/")


@pytest.fixture(scope="session")
def aws_session():
    return _aws_session()


@pytest.fixture(scope="session")
def sfn_client(aws_session):
    return aws_session.client("stepfunctions")
```

Verify selected ARNs against the expected account and region as well. Account
identity alone does not identify a permitted stage or resource. HTTP-only tests
can use a selected non-production URL without AWS credentials.

Do not catch every AWS exception and convert it to a skip. Access denial,
incorrect identity, and broken secret retrieval must fail required tests.
Skip only explicitly optional scenarios. Report skipped and executed counts
separately, including any required scenarios that could not run.

## CI and dependency setup

Keep offline jobs free of deployed secrets and AWS roles. Use a separate job for
deployed tests, the project's existing approval rules, and a role scoped to the
selected environment. Prefer short-lived OIDC credentials over stored AWS keys.
Pin workflow actions to reviewed commit SHAs.

Install only the dependency extras the selected tests require. Resolve and audit
them through the project's lockfile. Review code and dependencies before running
a fetched skill, plugin hook, test, or build backend. Never lower TLS verification
to make a test pass.
