# Lambda + EventBridge Integration Patterns

Moto-based patterns for testing Lambda functions that consume or publish EventBridge events.

## Pattern: Lambda Triggered by EventBridge Rule

```python
"""Test Lambda triggered by EventBridge (CloudWatch Events) rule."""
import json
import boto3
import pytest
from moto import mock_aws
from unittest.mock import MagicMock

REGION = "us-east-1"
EVENT_BUS_NAME = "custom-bus"


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


def build_eventbridge_event(source, detail_type, detail, bus_name=None):
    """Build an EventBridge event matching the Lambda trigger format."""
    return {
        "version": "0",
        "id": "event-001",
        "source": source,
        "account": "123456789012",
        "time": "2024-01-01T00:00:00Z",
        "region": REGION,
        "resources": [],
        "detail-type": detail_type,
        "detail": detail,
    }


class TestLambdaConsumesEventBridge:
    """Test Lambda that processes EventBridge events."""

    def test_handles_custom_event(self, aws_env, mock_context):
        from handler.main import lambda_handler

        event = build_eventbridge_event(
            source="myapp.orders",
            detail_type="OrderCreated",
            detail={"order_id": "ord-001", "amount": 99.99, "customer_id": "c-100"},
        )
        result = lambda_handler(event, mock_context)
        assert result is None or isinstance(result, dict)

    def test_handles_different_detail_types(self, aws_env, mock_context):
        from handler.main import lambda_handler

        for detail_type in ["OrderCreated", "OrderUpdated", "OrderCancelled"]:
            event = build_eventbridge_event(
                source="myapp.orders",
                detail_type=detail_type,
                detail={"order_id": "ord-001", "status": detail_type.lower()},
            )
            result = lambda_handler(event, mock_context)
            assert result is None or isinstance(result, dict)

    def test_handles_scheduled_event(self, aws_env, mock_context):
        """Test Lambda triggered by EventBridge Scheduler (cron/rate)."""
        from handler.main import lambda_handler

        event = {
            "version": "0",
            "id": "scheduled-001",
            "source": "aws.events",
            "account": "123456789012",
            "time": "2024-01-01T00:00:00Z",
            "region": REGION,
            "resources": [
                f"arn:aws:events:{REGION}:123456789012:rule/my-schedule"
            ],
            "detail-type": "Scheduled Event",
            "detail": {},
        }
        result = lambda_handler(event, mock_context)
        assert result is None or isinstance(result, dict)

    def test_handles_aws_service_event(self, aws_env, mock_context):
        """Test Lambda processing AWS service events (e.g., EC2 state change)."""
        from handler.main import lambda_handler

        event = build_eventbridge_event(
            source="aws.ec2",
            detail_type="EC2 Instance State-change Notification",
            detail={
                "instance-id": "i-0123456789abcdef0",
                "state": "stopped",
            },
        )
        result = lambda_handler(event, mock_context)
        assert result is None or isinstance(result, dict)

    def test_handles_empty_detail(self, aws_env, mock_context):
        from handler.main import lambda_handler

        event = build_eventbridge_event(
            source="myapp.heartbeat",
            detail_type="Heartbeat",
            detail={},
        )
        result = lambda_handler(event, mock_context)
        assert result is None or isinstance(result, dict)


class TestEventBridgeWithSideEffects:
    """Test Lambda that processes events and writes to other services."""

    def test_stores_event_in_dynamodb(self, aws_env, mock_context):
        with mock_aws():
            dynamodb = boto3.resource("dynamodb", region_name=REGION)
            dynamodb.create_table(
                TableName="events-log",
                KeySchema=[{"AttributeName": "event_id", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "event_id", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )

            from handler.main import lambda_handler

            event = build_eventbridge_event(
                source="myapp.orders",
                detail_type="OrderCreated",
                detail={"order_id": "ord-001", "event_id": "evt-001"},
            )
            lambda_handler(event, mock_context)

            table = dynamodb.Table("events-log")
            response = table.get_item(Key={"event_id": "evt-001"})
            assert "Item" in response

    def test_sends_notification_to_sns(self, aws_env, mock_context):
        with mock_aws():
            sns = boto3.client("sns", region_name=REGION)
            topic = sns.create_topic(Name="alerts-topic")
            topic_arn = topic["TopicArn"]

            # Subscribe SQS to verify
            sqs = boto3.client("sqs", region_name=REGION)
            queue = sqs.create_queue(QueueName="verify-queue")
            queue_url = queue["QueueUrl"]
            queue_arn = sqs.get_queue_attributes(
                QueueUrl=queue_url, AttributeNames=["QueueArn"]
            )["Attributes"]["QueueArn"]
            sns.subscribe(TopicArn=topic_arn, Protocol="sqs", Endpoint=queue_arn)

            from handler.main import lambda_handler

            event = build_eventbridge_event(
                source="myapp.alerts",
                detail_type="HighPriorityAlert",
                detail={"alert_id": "a-001", "severity": "critical"},
            )
            lambda_handler(event, mock_context)

            messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10)
            assert len(messages.get("Messages", [])) >= 1
```

## Pattern: Lambda Publishing Events to EventBridge

```python
"""Test Lambda that publishes events to EventBridge."""
import json
import boto3
import pytest
from moto import mock_aws
from unittest.mock import MagicMock, patch

REGION = "us-east-1"
EVENT_BUS_NAME = "custom-bus"


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("EVENT_BUS_NAME", EVENT_BUS_NAME)


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.function_name = "test-fn"
    ctx.get_remaining_time_in_millis.return_value = 30000
    return ctx


class TestLambdaPublishesEventBridge:
    @pytest.fixture
    def event_bus(self, aws_env):
        with mock_aws():
            events = boto3.client("events", region_name=REGION)
            events.create_event_bus(Name=EVENT_BUS_NAME)
            yield events

    def test_publishes_event_to_custom_bus(self, event_bus, mock_context):
        """Verify Lambda calls put_events with correct parameters."""
        with patch("handler.main.boto3") as mock_boto:
            mock_client = MagicMock()
            mock_boto.client.return_value = mock_client
            mock_client.put_events.return_value = {
                "FailedEntryCount": 0, "Entries": [{"EventId": "e-001"}]
            }

            from handler.main import lambda_handler

            event = {
                "body": json.dumps({
                    "order_id": "ord-001",
                    "status": "completed",
                })
            }
            result = lambda_handler(event, mock_context)
            assert result["statusCode"] == 200

            # Verify put_events was called
            mock_client.put_events.assert_called_once()
            call_args = mock_client.put_events.call_args
            entries = call_args[1]["Entries"] if "Entries" in call_args[1] else call_args[0][0]
            assert len(entries) >= 1

    def test_handles_put_events_failure(self, event_bus, mock_context):
        """Test behavior when EventBridge rejects the event."""
        with patch("handler.main.boto3") as mock_boto:
            mock_client = MagicMock()
            mock_boto.client.return_value = mock_client
            mock_client.put_events.return_value = {
                "FailedEntryCount": 1,
                "Entries": [{"ErrorCode": "InternalFailure", "ErrorMessage": "Service error"}],
            }

            from handler.main import lambda_handler

            event = {"body": json.dumps({"order_id": "ord-002"})}
            result = lambda_handler(event, mock_context)
            # Handler should detect and handle the failure
            assert result["statusCode"] in (200, 500, 502)

    def test_publishes_batch_events(self, event_bus, mock_context):
        """Test Lambda that sends multiple events in one put_events call."""
        with patch("handler.main.boto3") as mock_boto:
            mock_client = MagicMock()
            mock_boto.client.return_value = mock_client
            mock_client.put_events.return_value = {
                "FailedEntryCount": 0,
                "Entries": [{"EventId": f"e-{i}"} for i in range(3)],
            }

            from handler.main import lambda_handler

            event = {
                "body": json.dumps({
                    "orders": [
                        {"order_id": f"ord-{i}", "status": "shipped"}
                        for i in range(3)
                    ]
                })
            }
            result = lambda_handler(event, mock_context)
            assert result["statusCode"] == 200
```

## Pattern: EventBridge with Event Bus and Rules (Full Setup)

```python
"""Test EventBridge rules and targets with moto."""
import json
import boto3
import pytest
from moto import mock_aws

REGION = "us-east-1"


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


class TestEventBridgeRulesSetup:
    """Verify EventBridge rules and targets are configured correctly."""

    def test_creates_rule_with_event_pattern(self, aws_env):
        with mock_aws():
            events = boto3.client("events", region_name=REGION)
            events.create_event_bus(Name="my-bus")

            events.put_rule(
                Name="order-events-rule",
                EventBusName="my-bus",
                EventPattern=json.dumps({
                    "source": ["myapp.orders"],
                    "detail-type": ["OrderCreated", "OrderUpdated"],
                }),
                State="ENABLED",
            )

            rules = events.list_rules(EventBusName="my-bus")
            assert len(rules["Rules"]) == 1
            assert rules["Rules"][0]["Name"] == "order-events-rule"

    def test_creates_scheduled_rule(self, aws_env):
        with mock_aws():
            events = boto3.client("events", region_name=REGION)

            events.put_rule(
                Name="daily-cleanup",
                ScheduleExpression="rate(1 day)",
                State="ENABLED",
            )

            rules = events.list_rules()
            matching = [r for r in rules["Rules"] if r["Name"] == "daily-cleanup"]
            assert len(matching) == 1
```
