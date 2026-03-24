---
name: aws-integration-testing
description: >
  Generate comprehensive integration tests for AWS Python Lambda functions,
  Batch jobs, and services that interact with S3, DynamoDB, RDS/PostgreSQL,
  SQS, SNS, EventBridge, Kinesis, and other AWS services. Uses moto for
  in-process AWS mocking and testcontainers for real database testing. Reads
  the handler source code to discover every AWS interaction and generates
  tests covering all code paths. Use when asked to write integration tests,
  test with mocked AWS, test Lambda + S3, test Lambda + DynamoDB, test
  Lambda + SQS, test Lambda + SNS, test Lambda + EventBridge, test Lambda
  + Kinesis, test with moto, or test with testcontainers for any AWS
  Python project.
---

# AWS Integration Testing Skill

Generate integration tests by reading handler code, identifying every AWS service interaction,
and producing tests with correct moto mocks for each one.

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
2. **Real moto mocks, not unittest.mock** — use `mock_aws()` for AWS services so real API semantics are tested
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
