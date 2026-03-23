# Lambda + SNS Integration Patterns

Moto-based patterns for testing Lambda functions that consume or publish SNS messages.

## Pattern: Lambda Triggered by SNS

```python
"""Test Lambda triggered by SNS notification."""
import json
import boto3
import pytest
from moto import mock_aws
from unittest.mock import MagicMock

REGION = "us-east-1"
TOPIC_NAME = "test-topic"


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.function_name = "test-fn"
    ctx.memory_limit_in_mb = 256
    ctx.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-fn"
    ctx.get_remaining_time_in_millis.return_value = 30000
    return ctx


def build_sns_event(message, subject="Test Subject", topic_arn=None):
    """Build an SNS event matching the Lambda SNS trigger format."""
    if topic_arn is None:
        topic_arn = f"arn:aws:sns:{REGION}:123456789012:{TOPIC_NAME}"

    body = json.dumps(message) if isinstance(message, dict) else message
    return {
        "Records": [{
            "EventVersion": "1.0",
            "EventSubscriptionArn": f"{topic_arn}:sub-1",
            "EventSource": "aws:sns",
            "Sns": {
                "SignatureVersion": "1",
                "Timestamp": "2024-01-01T00:00:00.000Z",
                "Signature": "EXAMPLE",
                "SigningCertUrl": "EXAMPLE",
                "MessageId": "msg-001",
                "Message": body,
                "MessageAttributes": {},
                "Type": "Notification",
                "UnsubscribeUrl": "EXAMPLE",
                "TopicArn": topic_arn,
                "Subject": subject,
            },
        }]
    }


class TestLambdaConsumesSNS:
    """Test Lambda that processes SNS notifications."""

    def test_processes_single_notification(self, aws_env, mock_context):
        from handler.main import lambda_handler

        event = build_sns_event({"action": "user_signup", "user_id": "u-123"})
        result = lambda_handler(event, mock_context)
        assert result is None or isinstance(result, dict)

    def test_processes_notification_with_string_message(self, aws_env, mock_context):
        from handler.main import lambda_handler

        event = build_sns_event("Plain text notification")
        result = lambda_handler(event, mock_context)
        assert result is None or isinstance(result, dict)

    def test_handles_malformed_message(self, aws_env, mock_context):
        from handler.main import lambda_handler

        event = build_sns_event("{invalid-json{{")
        result = lambda_handler(event, mock_context)
        # Should handle gracefully without raising
        assert result is None or isinstance(result, dict)

    def test_processes_multiple_records(self, aws_env, mock_context):
        """SNS can deliver multiple records in a single invocation."""
        from handler.main import lambda_handler

        topic_arn = f"arn:aws:sns:{REGION}:123456789012:{TOPIC_NAME}"
        event = {
            "Records": [
                {
                    "EventVersion": "1.0",
                    "EventSubscriptionArn": f"{topic_arn}:sub-1",
                    "EventSource": "aws:sns",
                    "Sns": {
                        "MessageId": f"msg-{i}",
                        "Message": json.dumps({"id": f"item-{i}"}),
                        "MessageAttributes": {},
                        "Type": "Notification",
                        "TopicArn": topic_arn,
                        "Subject": "Batch",
                        "Timestamp": "2024-01-01T00:00:00.000Z",
                        "SignatureVersion": "1",
                        "Signature": "EXAMPLE",
                        "SigningCertUrl": "EXAMPLE",
                        "UnsubscribeUrl": "EXAMPLE",
                    },
                }
                for i in range(3)
            ]
        }
        result = lambda_handler(event, mock_context)
        assert result is None or isinstance(result, dict)


class TestLambdaSNSWithSideEffects:
    """Test Lambda that reads SNS and writes to other AWS services."""

    def test_stores_notification_in_dynamodb(self, aws_env, mock_context):
        with mock_aws():
            dynamodb = boto3.resource("dynamodb", region_name=REGION)
            dynamodb.create_table(
                TableName="notifications",
                KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )

            from handler.main import lambda_handler

            event = build_sns_event({
                "id": "notif-1",
                "type": "user_signup",
                "user_id": "u-123",
            })
            lambda_handler(event, mock_context)

            table = dynamodb.Table("notifications")
            response = table.get_item(Key={"id": "notif-1"})
            assert "Item" in response

    def test_forwards_to_sqs(self, aws_env, mock_context):
        with mock_aws():
            sqs = boto3.client("sqs", region_name=REGION)
            queue = sqs.create_queue(QueueName="downstream-queue")
            queue_url = queue["QueueUrl"]

            from handler.main import lambda_handler

            event = build_sns_event({"action": "forward", "payload": "data"})
            lambda_handler(event, mock_context)

            messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10)
            assert len(messages.get("Messages", [])) >= 1
```

## Pattern: Lambda Publishing to SNS

```python
"""Test Lambda that publishes messages to SNS topics."""
import json
import boto3
import pytest
from moto import mock_aws
from unittest.mock import MagicMock

REGION = "us-east-1"
TOPIC_NAME = "notification-topic"


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


class TestLambdaPublishesToSNS:
    @pytest.fixture
    def sns_topic(self, aws_env):
        with mock_aws():
            sns = boto3.client("sns", region_name=REGION)
            response = sns.create_topic(Name=TOPIC_NAME)
            topic_arn = response["TopicArn"]

            # Subscribe an SQS queue so we can verify published messages
            sqs = boto3.client("sqs", region_name=REGION)
            queue = sqs.create_queue(QueueName="verify-queue")
            queue_url = queue["QueueUrl"]
            queue_arn = sqs.get_queue_attributes(
                QueueUrl=queue_url, AttributeNames=["QueueArn"]
            )["Attributes"]["QueueArn"]

            sns.subscribe(
                TopicArn=topic_arn,
                Protocol="sqs",
                Endpoint=queue_arn,
            )

            yield sns, topic_arn, sqs, queue_url

    def test_publishes_notification(self, sns_topic, mock_context):
        sns, topic_arn, sqs, queue_url = sns_topic

        from handler.main import lambda_handler

        event = {
            "body": json.dumps({
                "user_id": "u-123",
                "event": "order_completed",
            })
        }
        result = lambda_handler(event, mock_context)
        assert result["statusCode"] == 200

        # Verify message was published by checking the subscribed SQS queue
        messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10)
        assert len(messages.get("Messages", [])) >= 1

    def test_publishes_with_message_attributes(self, sns_topic, mock_context):
        sns, topic_arn, sqs, queue_url = sns_topic

        from handler.main import lambda_handler

        event = {
            "body": json.dumps({
                "user_id": "u-456",
                "event": "payment_processed",
                "priority": "high",
            })
        }
        result = lambda_handler(event, mock_context)
        assert result["statusCode"] == 200

    def test_error_returns_failure_response(self, aws_env, mock_context):
        """Test behavior when SNS publish fails."""
        from unittest.mock import patch
        from botocore.exceptions import ClientError

        with patch("handler.main.boto3") as mock_boto:
            error_response = {"Error": {"Code": "InvalidParameter", "Message": "Invalid"}}
            mock_boto.client.return_value.publish.side_effect = ClientError(
                error_response, "Publish"
            )

            from handler.main import lambda_handler

            event = {"body": json.dumps({"user_id": "u-789"})}
            result = lambda_handler(event, mock_context)
            assert result["statusCode"] in (400, 500)
```

## Pattern: SNS with Message Filtering

```python
"""Test Lambda that publishes to SNS with filtering attributes."""
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


class TestSNSMessageFiltering:
    @pytest.fixture
    def filtered_topic(self, aws_env):
        with mock_aws():
            sns = boto3.client("sns", region_name=REGION)
            sqs = boto3.client("sqs", region_name=REGION)

            topic = sns.create_topic(Name="events-topic")
            topic_arn = topic["TopicArn"]

            # Create separate queues for different event types
            high_queue = sqs.create_queue(QueueName="high-priority")
            high_queue_url = high_queue["QueueUrl"]
            high_arn = sqs.get_queue_attributes(
                QueueUrl=high_queue_url, AttributeNames=["QueueArn"]
            )["Attributes"]["QueueArn"]

            low_queue = sqs.create_queue(QueueName="low-priority")
            low_queue_url = low_queue["QueueUrl"]
            low_arn = sqs.get_queue_attributes(
                QueueUrl=low_queue_url, AttributeNames=["QueueArn"]
            )["Attributes"]["QueueArn"]

            # Subscribe with filter policies
            sns.subscribe(
                TopicArn=topic_arn,
                Protocol="sqs",
                Endpoint=high_arn,
                Attributes={
                    "FilterPolicy": json.dumps({"priority": ["high"]}),
                },
            )
            sns.subscribe(
                TopicArn=topic_arn,
                Protocol="sqs",
                Endpoint=low_arn,
                Attributes={
                    "FilterPolicy": json.dumps({"priority": ["low"]}),
                },
            )

            yield sns, topic_arn, sqs, high_queue_url, low_queue_url

    def test_high_priority_message_routed_correctly(self, filtered_topic, mock_context):
        sns, topic_arn, sqs, high_url, low_url = filtered_topic

        sns.publish(
            TopicArn=topic_arn,
            Message=json.dumps({"event": "alert"}),
            MessageAttributes={
                "priority": {"DataType": "String", "StringValue": "high"},
            },
        )

        high_msgs = sqs.receive_message(QueueUrl=high_url, MaxNumberOfMessages=10)
        assert len(high_msgs.get("Messages", [])) >= 1
```
