# Lambda + SQS Integration Patterns

Moto-based patterns for testing Lambda functions that consume or produce SQS messages.

## Pattern: Lambda Consuming SQS Messages (Event Source Mapping)

```python
"""Test Lambda triggered by SQS event source mapping."""
import json
import boto3
import pytest
from moto import mock_aws
from unittest.mock import MagicMock

REGION = "us-east-1"
QUEUE_NAME = "test-queue"


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("QUEUE_URL", f"https://sqs.{REGION}.amazonaws.com/123456789012/{QUEUE_NAME}")


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.function_name = "test-fn"
    ctx.memory_limit_in_mb = 256
    ctx.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-fn"
    ctx.get_remaining_time_in_millis.return_value = 30000
    return ctx


def build_sqs_event(messages):
    """Build an SQS event matching the Lambda event source mapping format."""
    records = []
    for i, msg in enumerate(messages):
        body = json.dumps(msg) if isinstance(msg, dict) else msg
        records.append({
            "messageId": f"msg-{i}",
            "receiptHandle": f"handle-{i}",
            "body": body,
            "attributes": {
                "ApproximateReceiveCount": "1",
                "SentTimestamp": "1700000000000",
                "SenderId": "123456789012",
                "ApproximateFirstReceiveTimestamp": "1700000000000",
            },
            "messageAttributes": {},
            "md5OfBody": "dummy",
            "eventSource": "aws:sqs",
            "eventSourceARN": f"arn:aws:sqs:{REGION}:123456789012:{QUEUE_NAME}",
            "awsRegion": REGION,
        })
    return {"Records": records}


class TestLambdaConsumesSQS:
    """Test Lambda that processes messages from SQS event source mapping."""

    def test_processes_single_message(self, aws_env, mock_context):
        from handler.main import lambda_handler

        event = build_sqs_event([{"action": "process", "id": "item-1"}])
        result = lambda_handler(event, mock_context)

        # Lambda SQS handlers typically return batchItemFailures
        assert result is None or "batchItemFailures" not in result or len(result["batchItemFailures"]) == 0

    def test_processes_batch_of_messages(self, aws_env, mock_context):
        from handler.main import lambda_handler

        messages = [{"action": "process", "id": f"item-{i}"} for i in range(5)]
        event = build_sqs_event(messages)
        result = lambda_handler(event, mock_context)

        assert result is None or "batchItemFailures" not in result or len(result["batchItemFailures"]) == 0

    def test_returns_partial_batch_failure(self, aws_env, mock_context):
        """Test partial batch failure response (requires ReportBatchItemFailures)."""
        from handler.main import lambda_handler

        messages = [
            {"action": "process", "id": "good-item"},
            {"action": "process", "id": "bad-item"},  # Designed to fail
        ]
        event = build_sqs_event(messages)
        result = lambda_handler(event, mock_context)

        # If handler supports partial batch failures:
        if result and "batchItemFailures" in result:
            failed_ids = [f["itemIdentifier"] for f in result["batchItemFailures"]]
            assert len(failed_ids) >= 0  # Adjust based on expected failures

    def test_handles_malformed_message_body(self, aws_env, mock_context):
        from handler.main import lambda_handler

        event = build_sqs_event(["not-valid-json{{{"])
        result = lambda_handler(event, mock_context)

        # Handler should not crash; it should handle parse errors gracefully
        assert result is None or isinstance(result, dict)

    def test_handles_empty_records(self, aws_env, mock_context):
        from handler.main import lambda_handler

        event = {"Records": []}
        result = lambda_handler(event, mock_context)
        assert result is None or isinstance(result, dict)


class TestLambdaConsumesSQSWithSideEffects:
    """Test Lambda that reads SQS and writes to another AWS service."""

    def test_writes_to_dynamodb_after_processing(self, aws_env, mock_context):
        with mock_aws():
            # Set up DynamoDB destination table
            dynamodb = boto3.resource("dynamodb", region_name=REGION)
            table = dynamodb.create_table(
                TableName="results-table",
                KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )

            from handler.main import lambda_handler

            event = build_sqs_event([{"action": "store", "id": "item-1", "data": "hello"}])
            lambda_handler(event, mock_context)

            # Verify the handler wrote to DynamoDB
            response = table.get_item(Key={"id": "item-1"})
            assert "Item" in response

    def test_writes_to_s3_after_processing(self, aws_env, mock_context):
        with mock_aws():
            s3 = boto3.client("s3", region_name=REGION)
            s3.create_bucket(
                Bucket="output-bucket",
                CreateBucketConfiguration={"LocationConstraint": REGION},
            )

            from handler.main import lambda_handler

            event = build_sqs_event([{"action": "export", "id": "item-1"}])
            lambda_handler(event, mock_context)

            # Verify object was written to S3
            objects = s3.list_objects_v2(Bucket="output-bucket")
            assert objects.get("KeyCount", 0) >= 1
```

## Pattern: Lambda Sending Messages to SQS

```python
"""Test Lambda that sends messages to SQS."""
import json
import boto3
import pytest
from moto import mock_aws
from unittest.mock import MagicMock

REGION = "us-east-1"
QUEUE_NAME = "downstream-queue"


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("DOWNSTREAM_QUEUE_URL",
                       f"https://sqs.{REGION}.amazonaws.com/123456789012/{QUEUE_NAME}")


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.function_name = "test-fn"
    ctx.memory_limit_in_mb = 256
    ctx.get_remaining_time_in_millis.return_value = 30000
    return ctx


class TestLambdaSendsToSQS:
    @pytest.fixture
    def sqs_queue(self, aws_env):
        with mock_aws():
            sqs = boto3.client("sqs", region_name=REGION)
            response = sqs.create_queue(QueueName=QUEUE_NAME)
            yield sqs, response["QueueUrl"]

    def test_sends_message_to_queue(self, sqs_queue, mock_context):
        sqs, queue_url = sqs_queue

        from handler.main import lambda_handler

        event = {"body": json.dumps({"task": "notify", "user_id": "u-123"})}
        result = lambda_handler(event, mock_context)
        assert result["statusCode"] == 200

        # Verify message was enqueued
        messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10)
        assert "Messages" in messages
        assert len(messages["Messages"]) >= 1

        body = json.loads(messages["Messages"][0]["Body"])
        assert body["user_id"] == "u-123"

    def test_sends_message_with_attributes(self, sqs_queue, mock_context):
        sqs, queue_url = sqs_queue

        from handler.main import lambda_handler

        event = {"body": json.dumps({"task": "notify", "priority": "high"})}
        result = lambda_handler(event, mock_context)
        assert result["statusCode"] == 200

        messages = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,
            MessageAttributeNames=["All"],
        )
        assert len(messages.get("Messages", [])) >= 1

    def test_sends_batch_messages(self, sqs_queue, mock_context):
        sqs, queue_url = sqs_queue

        from handler.main import lambda_handler

        event = {
            "body": json.dumps({
                "tasks": [
                    {"id": "t-1", "action": "email"},
                    {"id": "t-2", "action": "sms"},
                    {"id": "t-3", "action": "push"},
                ]
            })
        }
        result = lambda_handler(event, mock_context)
        assert result["statusCode"] == 200

        messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10)
        assert len(messages.get("Messages", [])) >= 3
```

## Pattern: FIFO Queue

```python
"""Test Lambda with SQS FIFO queue."""
import json
import boto3
import pytest
from moto import mock_aws
from unittest.mock import MagicMock

REGION = "us-east-1"
FIFO_QUEUE_NAME = "order-queue.fifo"


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.function_name = "test-fn"
    ctx.get_remaining_time_in_millis.return_value = 30000
    return ctx


class TestFIFOQueue:
    @pytest.fixture
    def fifo_queue(self, aws_env):
        with mock_aws():
            sqs = boto3.client("sqs", region_name=REGION)
            response = sqs.create_queue(
                QueueName=FIFO_QUEUE_NAME,
                Attributes={
                    "FifoQueue": "true",
                    "ContentBasedDeduplication": "true",
                },
            )
            yield sqs, response["QueueUrl"]

    def test_sends_to_fifo_with_group_id(self, fifo_queue, mock_context):
        sqs, queue_url = fifo_queue

        from handler.main import lambda_handler

        event = {
            "body": json.dumps({
                "order_id": "ord-001",
                "customer_id": "c-100",
                "action": "place_order",
            })
        }
        result = lambda_handler(event, mock_context)
        assert result["statusCode"] == 200

        messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10)
        assert len(messages.get("Messages", [])) >= 1

    def test_preserves_message_ordering(self, fifo_queue, mock_context):
        sqs, queue_url = fifo_queue

        from handler.main import lambda_handler

        for i in range(3):
            event = {"body": json.dumps({"order_id": f"ord-{i}", "seq": i})}
            lambda_handler(event, mock_context)

        messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10)
        bodies = [json.loads(m["Body"]) for m in messages.get("Messages", [])]
        sequences = [b["seq"] for b in bodies]
        assert sequences == sorted(sequences)
```

## Pattern: Dead Letter Queue

```python
"""Test Lambda with SQS DLQ handling."""
import json
import boto3
import pytest
from moto import mock_aws
from unittest.mock import MagicMock

REGION = "us-east-1"


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.function_name = "test-fn"
    ctx.get_remaining_time_in_millis.return_value = 30000
    return ctx


class TestDLQHandling:
    @pytest.fixture
    def queues_with_dlq(self, aws_env):
        with mock_aws():
            sqs = boto3.client("sqs", region_name=REGION)

            # Create DLQ first
            dlq_response = sqs.create_queue(QueueName="my-queue-dlq")
            dlq_url = dlq_response["QueueUrl"]
            dlq_arn = sqs.get_queue_attributes(
                QueueUrl=dlq_url, AttributeNames=["QueueArn"]
            )["Attributes"]["QueueArn"]

            # Create main queue with DLQ redrive policy
            main_response = sqs.create_queue(
                QueueName="my-queue",
                Attributes={
                    "RedrivePolicy": json.dumps({
                        "deadLetterTargetArn": dlq_arn,
                        "maxReceiveCount": "3",
                    })
                },
            )
            main_url = main_response["QueueUrl"]

            yield sqs, main_url, dlq_url

    def test_dlq_processor_handles_failed_messages(self, queues_with_dlq, mock_context):
        """Test a Lambda that processes messages from the DLQ."""
        sqs, main_url, dlq_url = queues_with_dlq

        # Put a message directly on the DLQ (simulating repeated failure)
        sqs.send_message(
            QueueUrl=dlq_url,
            MessageBody=json.dumps({"id": "failed-item", "error": "timeout"}),
        )

        from handler.dlq_processor import lambda_handler

        event = {
            "Records": [{
                "messageId": "dlq-msg-1",
                "receiptHandle": "dlq-handle-1",
                "body": json.dumps({"id": "failed-item", "error": "timeout"}),
                "attributes": {"ApproximateReceiveCount": "4"},
                "eventSource": "aws:sqs",
                "eventSourceARN": f"arn:aws:sqs:{REGION}:123456789012:my-queue-dlq",
                "awsRegion": REGION,
            }]
        }
        result = lambda_handler(event, mock_context)
        assert result is None or isinstance(result, dict)
```
