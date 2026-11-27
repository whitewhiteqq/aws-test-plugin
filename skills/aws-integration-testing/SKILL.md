---
name: aws-integration-testing
license: Apache-2.0
description: >
  Generate integration tests for AWS Python handlers and service workflows.
  Use moto for in-process AWS mocks, testcontainers for databases, or optional
  AWS Emulator for local AWS API tests. Read handler code to identify AWS
  interactions and cover success and error paths. Use when asked for
  integration tests, mocked AWS, moto, testcontainers, or AWS Emulator tests.
---

# AWS Integration Testing Skill

Generate integration tests by reading handler code, identifying AWS service
interactions, and testing them with the selected local backend.

## Choose the local backend

Reuse the project's existing tests and fixtures. Keep moto as the default for
in-process mocks. Use testcontainers when the test needs a real local database.
Choose AWS Emulator when requested or when the project needs local AWS API
workflows across processes. Check the selected release's fidelity for the actual
operations before choosing it.

For AWS Emulator, follow [references/aws-emulator.md](references/aws-emulator.md).
That reference covers setup, signed requests, HTTPS, and a separately selected
test suite. The examples below cover moto and testcontainers. Local emulation
does not establish deployed AWS behavior or policy enforcement.

## How to Generate Integration Tests

### Phase 1: Analyze AWS Interactions

Read the handler source code and find every AWS interaction:

```python
# Look for these patterns in the handler:

# Direct client creation
client = boto3.client("s3")
resource = boto3.resource("dynamodb")
sqs = boto3.client("sqs")
sns = boto3.client("sns")
events = boto3.client("events")
kinesis = boto3.client("kinesis")

# Method calls on clients
client.get_object(Bucket=..., Key=...)
client.put_object(Bucket=..., Key=..., Body=...)
table.get_item(Key=...)
table.put_item(Item=...)
table.query(KeyConditionExpression=...)
sqs.send_message(QueueUrl=..., MessageBody=...)
sqs.send_message_batch(QueueUrl=..., Entries=...)
sns.publish(TopicArn=..., Message=...)
events.put_events(Entries=[...])
kinesis.put_record(StreamName=..., Data=..., PartitionKey=...)

# Error handling around AWS calls
try:
    client.get_object(...)
except ClientError as e:
    if e.response["Error"]["Code"] == "NoSuchKey":
        ...
```

Build a table of interactions:

| Service | Method | Parameters | Success Path | Error Path |
|---------|--------|-----------|-------------|-----------|
| s3 | get_object | Bucket, Key | Returns Body | NoSuchKey → 404 |
| s3 | put_object | Bucket, Key, Body | Returns None | AccessDenied → 403 |
| dynamodb | get_item | Key | Returns Item | Item not found → None || sqs | send_message | QueueUrl, MessageBody | Returns MessageId | NonExistentQueue → error |
| sqs | receive_message | QueueUrl | Returns Messages | Timeout → empty |
| sns | publish | TopicArn, Message | Returns MessageId | InvalidParameter → 400 |
| events | put_events | Entries | FailedEntryCount=0 | InternalFailure → retry |
| kinesis | put_record | StreamName, Data, PartitionKey | Returns ShardId | ProvisionedThroughputExceeded → 429 |
### Phase 2: Generate moto-based Tests

For each AWS service interaction, generate test(s). Use the patterns in:
- [references/lambda-s3-patterns.md](references/lambda-s3-patterns.md)
- [references/lambda-dynamodb-patterns.md](references/lambda-dynamodb-patterns.md)
- [references/lambda-rds-patterns.md](references/lambda-rds-patterns.md)
- [references/lambda-sqs-patterns.md](references/lambda-sqs-patterns.md)
- [references/lambda-sns-patterns.md](references/lambda-sns-patterns.md)
- [references/lambda-eventbridge-patterns.md](references/lambda-eventbridge-patterns.md)
- [references/lambda-kinesis-patterns.md](references/lambda-kinesis-patterns.md)

### General Structure

```python
"""Integration tests for {handler_name}. Auto-generated from code analysis."""
import json
import boto3
import pytest
from moto import mock_aws
from unittest.mock import patch, MagicMock

# Discovered from handler's os.environ/os.getenv calls:
ENV_VARS = {
    "BUCKET_NAME": "test-bucket",
    "TABLE_NAME": "test-table",
    "AWS_DEFAULT_REGION": "us-east-1",
}

REGION = "us-east-1"


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    for k, v in ENV_VARS.items():
        monkeypatch.setenv(k, v)


@pytest.fixture
def aws_credentials(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.function_name = "test-function"
    ctx.memory_limit_in_mb = 256
    ctx.get_remaining_time_in_millis.return_value = 30000
    return ctx
```

### Phase 3: Test Every Code Path

For each code path discovered in Phase 1, generate one test:

```python
# Happy path — AWS call succeeds
def test_handler_reads_s3_and_returns_data(aws_credentials, mock_context):
    with mock_aws():
        # ARRANGE: Create the AWS resource with test data
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(
            Bucket="test-bucket",
            CreateBucketConfiguration={"LocationConstraint": REGION},
        )
        s3.put_object(Bucket="test-bucket", Key="data.json", Body=b'{"key": "value"}')

        # ACT: Call the handler
        from handler_module.main import lambda_handler
        event = {"pathParameters": {"key": "data.json"}}
        result = lambda_handler(event, mock_context)

        # ASSERT: Verify handler used S3 data correctly
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["key"] == "value"

# Error path — S3 object not found
def test_handler_missing_s3_key_returns_404(aws_credentials, mock_context):
    with mock_aws():
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(
            Bucket="test-bucket",
            CreateBucketConfiguration={"LocationConstraint": REGION},
        )
        # Don't create the object — it's missing

        from handler_module.main import lambda_handler
        event = {"pathParameters": {"key": "missing.json"}}
        result = lambda_handler(event, mock_context)

        assert result["statusCode"] == 404

# Error path — unexpected exception
def test_handler_unexpected_error_returns_500(mock_context):
    with patch("handler_module.main.boto3") as mock_boto:
        mock_boto.client.return_value.get_object.side_effect = Exception("boom")

        from handler_module.main import lambda_handler
        result = lambda_handler({"pathParameters": {"key": "x"}}, mock_context)

        assert result["statusCode"] == 500
```

## Key Principles

1. **One test per code path** — if the handler has 5 branches, write 5+ tests
2. **Stateful moto mocks** — use `mock_aws()` for AWS services; mocks do not establish deployed AWS semantics
3. **Set up real state** — if the handler reads from S3, put an actual object in moto S3
4. **Test error paths explicitly** — NoSuchKey, ConditionalCheckFailed, throttling
5. **Import the handler inside the test** — avoid module-level import caching issues with moto
6. **Monkeypatch env vars** — match exactly what the handler reads with `os.getenv()`

## Markers

```python
pytestmark = pytest.mark.integration
```

## Commands

```bash
# All integration tests
pytest tests/integration/ -v -m integration

# Moto-only (no Docker needed)
pytest tests/integration/ -v -m integration -k "not testcontainers"

# With testcontainers (needs Docker)
pytest tests/integration/ -v -m integration
```
