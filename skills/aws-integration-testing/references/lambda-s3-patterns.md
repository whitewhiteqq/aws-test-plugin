# Lambda + S3 Integration Patterns

Moto-based patterns for testing Lambda functions that interact with S3.

## Pattern: Read from S3

```python
"""Test Lambda that reads objects from S3."""
import json
import boto3
import pytest
from moto import mock_aws
from unittest.mock import MagicMock

REGION = "us-east-1"
BUCKET = "test-bucket"


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("BUCKET_NAME", BUCKET)


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.function_name = "test-fn"
    ctx.memory_limit_in_mb = 256
    ctx.get_remaining_time_in_millis.return_value = 30000
    return ctx


class TestLambdaReadsS3:
    @pytest.fixture
    def s3_with_data(self, aws_env):
        with mock_aws():
            s3 = boto3.client("s3", region_name=REGION)
            s3.create_bucket(
                Bucket=BUCKET,
                CreateBucketConfiguration={"LocationConstraint": REGION},
            )
            s3.put_object(
                Bucket=BUCKET,
                Key="data/record.json",
                Body=json.dumps({"id": "123", "status": "active"}).encode(),
            )
            yield s3

    def test_reads_existing_object(self, s3_with_data, mock_context):
        # Import handler INSIDE mock context
        from handler.main import lambda_handler

        event = {"pathParameters": {"key": "data/record.json"}}
        result = lambda_handler(event, mock_context)
        assert result["statusCode"] == 200

    def test_handles_missing_key(self, s3_with_data, mock_context):
        from handler.main import lambda_handler

        event = {"pathParameters": {"key": "missing/file.json"}}
        result = lambda_handler(event, mock_context)
        assert result["statusCode"] in (404, 500)
```

## Pattern: Write to S3

```python
class TestLambdaWritesS3:
    @pytest.fixture
    def s3_bucket(self, aws_env):
        with mock_aws():
            s3 = boto3.client("s3", region_name=REGION)
            s3.create_bucket(
                Bucket=BUCKET,
                CreateBucketConfiguration={"LocationConstraint": REGION},
            )
            yield s3

    def test_writes_object_to_s3(self, s3_bucket, mock_context):
        from handler.main import lambda_handler

        event = {
            "body": json.dumps({"data": "test-content"}),
        }
        result = lambda_handler(event, mock_context)
        assert result["statusCode"] == 200

        # Verify the object was written
        objects = s3_bucket.list_objects_v2(Bucket=BUCKET)
        assert objects["KeyCount"] >= 1

    def test_writes_correct_content(self, s3_bucket, mock_context):
        from handler.main import lambda_handler

        event = {"body": json.dumps({"id": "test-123", "data": "content"})}
        lambda_handler(event, mock_context)

        # Read back and verify
        obj = s3_bucket.get_object(Bucket=BUCKET, Key="expected/key/path.json")
        body = json.loads(obj["Body"].read())
        assert body["id"] == "test-123"
```

## Pattern: S3 Event Trigger

```python
class TestS3EventTrigger:
    """Test Lambda triggered by S3 event notifications."""

    @pytest.fixture
    def s3_bucket(self, aws_env):
        with mock_aws():
            s3 = boto3.client("s3", region_name=REGION)
            s3.create_bucket(
                Bucket=BUCKET,
                CreateBucketConfiguration={"LocationConstraint": REGION},
            )
            s3.put_object(Bucket=BUCKET, Key="uploads/file.pdf", Body=b"pdf-content")
            yield s3

    def _make_s3_event(self, key="uploads/file.pdf"):
        return {
            "Records": [{
                "eventSource": "aws:s3",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": BUCKET},
                    "object": {"key": key, "size": 1024},
                },
            }]
        }

    def test_processes_uploaded_file(self, s3_bucket, mock_context):
        from handler.main import lambda_handler

        event = self._make_s3_event("uploads/file.pdf")
        result = lambda_handler(event, mock_context)
        # Assert handler processed the file

    def test_ignores_non_matching_prefix(self, s3_bucket, mock_context):
        from handler.main import lambda_handler

        event = self._make_s3_event("other/file.txt")
        result = lambda_handler(event, mock_context)
        # Assert handler skipped non-matching file
```

## Pattern: Presigned URLs

```python
class TestPresignedUrlGeneration:
    @pytest.fixture
    def s3_bucket(self, aws_env):
        with mock_aws():
            s3 = boto3.client("s3", region_name=REGION)
            s3.create_bucket(
                Bucket=BUCKET,
                CreateBucketConfiguration={"LocationConstraint": REGION},
            )
            yield s3

    def test_generates_presigned_url(self, s3_bucket, mock_context):
        from handler.main import lambda_handler

        event = {"pathParameters": {"key": "files/doc.pdf"}}
        result = lambda_handler(event, mock_context)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert "url" in body
        assert "s3.amazonaws.com" in body["url"] or "s3" in body["url"]
```
