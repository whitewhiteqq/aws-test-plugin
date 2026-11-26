# Verify the deployed AWS session

Use the project's existing identity checks when available. Otherwise, put these
helpers in `tests/e2e/conftest.py`. Configure the chosen profile or CI role,
`AWS_DEFAULT_REGION`, and `AWS_EXPECTED_ACCOUNT_ID` before running deployed tests.

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
    session = boto3.Session(profile_name=os.getenv("AWS_PROFILE"), region_name=region)
    identity = session.client("sts").get_caller_identity()
    if identity["Account"] != expected_account:
        pytest.fail("AWS identity does not match the expected test account")
    return session


@pytest.fixture(scope="session")
def aws_session():
    return _aws_session()
```

Client fixtures request `aws_session` and call `aws_session.client("service")`.
Secret helpers in the same conftest can call `_aws_session()` directly. Do not
catch authentication errors and convert them to successful skips.

Verify each selected resource ARN against the expected account and region, and
select the permitted stage. Account identity alone does not authorize a resource.
Keep offline fake-credential fixtures out of this deployed suite. HTTP-only tests
can use an explicitly selected non-production URL without AWS credentials.
