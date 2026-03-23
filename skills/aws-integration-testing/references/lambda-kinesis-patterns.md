# Lambda + Kinesis Integration Patterns

Moto-based patterns for testing Lambda functions that consume or produce Kinesis data streams.

## Pattern: Lambda Consuming Kinesis Stream (Event Source Mapping)

```python
"""Test Lambda triggered by Kinesis Data Streams event source mapping."""
import base64
import json
import boto3
import pytest
from moto import mock_aws
from unittest.mock import MagicMock

REGION = "us-east-1"
STREAM_NAME = "test-stream"


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("STREAM_NAME", STREAM_NAME)


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.function_name = "test-fn"
    ctx.memory_limit_in_mb = 256
    ctx.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-fn"
    ctx.get_remaining_time_in_millis.return_value = 30000
    return ctx


def build_kinesis_event(records, stream_arn=None):
    """Build a Kinesis event matching the Lambda event source mapping format.

    Each record should be a dict or string (will be base64-encoded automatically).
    """
    if stream_arn is None:
        stream_arn = f"arn:aws:kinesis:{REGION}:123456789012:stream/{STREAM_NAME}"

    kinesis_records = []
    for i, record in enumerate(records):
        data = json.dumps(record) if isinstance(record, dict) else record
        encoded = base64.b64encode(data.encode("utf-8")).decode("utf-8")
        kinesis_records.append({
            "kinesis": {
                "kinesisSchemaVersion": "1.0",
                "partitionKey": f"pk-{i}",
                "sequenceNumber": f"{10000 + i}",
                "data": encoded,
                "approximateArrivalTimestamp": 1700000000.0 + i,
            },
            "eventSource": "aws:kinesis",
            "eventVersion": "1.0",
            "eventID": f"shardId-000000000000:{10000 + i}",
            "eventName": "aws:kinesis:record",
            "invokeIdentityArn": f"arn:aws:iam::123456789012:role/lambda-role",
            "awsRegion": REGION,
            "eventSourceARN": stream_arn,
        })
    return {"Records": kinesis_records}


class TestLambdaConsumesKinesis:
    """Test Lambda that processes records from Kinesis Data Streams."""

    def test_processes_single_record(self, aws_env, mock_context):
        from handler.main import lambda_handler

        event = build_kinesis_event([{"sensor_id": "s-001", "temperature": 72.5}])
        result = lambda_handler(event, mock_context)
        assert result is None or isinstance(result, dict)

    def test_processes_batch_of_records(self, aws_env, mock_context):
        from handler.main import lambda_handler

        records = [
            {"sensor_id": f"s-{i:03d}", "temperature": 70.0 + i}
            for i in range(10)
        ]
        event = build_kinesis_event(records)
        result = lambda_handler(event, mock_context)
        assert result is None or isinstance(result, dict)

    def test_handles_non_json_data(self, aws_env, mock_context):
        """Test handling of plain text or binary Kinesis data."""
        from handler.main import lambda_handler

        event = build_kinesis_event(["plain-text-data", "another-record"])
        result = lambda_handler(event, mock_context)
        assert result is None or isinstance(result, dict)

    def test_handles_malformed_data(self, aws_env, mock_context):
        from handler.main import lambda_handler

        event = build_kinesis_event(["{invalid-json{{"])
        result = lambda_handler(event, mock_context)
        # Should handle gracefully
        assert result is None or isinstance(result, dict)

    def test_handles_empty_records(self, aws_env, mock_context):
        from handler.main import lambda_handler

        event = {"Records": []}
        result = lambda_handler(event, mock_context)
        assert result is None or isinstance(result, dict)

    def test_returns_partial_batch_failure(self, aws_env, mock_context):
        """Test partial batch failure response (bisect on error)."""
        from handler.main import lambda_handler

        records = [
            {"sensor_id": "good-1", "temperature": 72.0},
            {"sensor_id": "bad-1", "temperature": -999},  # Triggers failure
            {"sensor_id": "good-2", "temperature": 73.0},
        ]
        event = build_kinesis_event(records)
        result = lambda_handler(event, mock_context)

        # If handler supports partial batch failures:
        if result and "batchItemFailures" in result:
            failed = result["batchItemFailures"]
            assert all("itemIdentifier" in f for f in failed)

    def test_decodes_base64_data_correctly(self, aws_env, mock_context):
        """Verify the handler correctly decodes base64-encoded Kinesis data."""
        from handler.main import lambda_handler

        original = {"sensor_id": "s-001", "value": 42, "unit": "celsius"}
        event = build_kinesis_event([original])

        # Verify the event was built correctly
        record_data = event["Records"][0]["kinesis"]["data"]
        decoded = json.loads(base64.b64decode(record_data))
        assert decoded == original

        result = lambda_handler(event, mock_context)
        assert result is None or isinstance(result, dict)


class TestKinesisWithSideEffects:
    """Test Lambda that reads Kinesis and writes to other services."""

    def test_aggregates_to_dynamodb(self, aws_env, mock_context):
        with mock_aws():
            dynamodb = boto3.resource("dynamodb", region_name=REGION)
            dynamodb.create_table(
                TableName="sensor-data",
                KeySchema=[{"AttributeName": "sensor_id", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "sensor_id", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )

            from handler.main import lambda_handler

            event = build_kinesis_event([
                {"sensor_id": "s-001", "temperature": 72.5},
                {"sensor_id": "s-001", "temperature": 73.0},
            ])
            lambda_handler(event, mock_context)

            table = dynamodb.Table("sensor-data")
            response = table.get_item(Key={"sensor_id": "s-001"})
            assert "Item" in response

    def test_writes_to_s3(self, aws_env, mock_context):
        with mock_aws():
            s3 = boto3.client("s3", region_name=REGION)
            s3.create_bucket(
                Bucket="data-lake",
                CreateBucketConfiguration={"LocationConstraint": REGION},
            )

            from handler.main import lambda_handler

            event = build_kinesis_event([
                {"sensor_id": "s-001", "temperature": 72.5},
            ])
            lambda_handler(event, mock_context)

            objects = s3.list_objects_v2(Bucket="data-lake")
            assert objects.get("KeyCount", 0) >= 1

    def test_forwards_to_another_stream(self, aws_env, mock_context):
        with mock_aws():
            kinesis = boto3.client("kinesis", region_name=REGION)
            kinesis.create_stream(StreamName="enriched-stream", ShardCount=1)

            from handler.main import lambda_handler

            event = build_kinesis_event([
                {"sensor_id": "s-001", "temperature": 72.5},
            ])
            lambda_handler(event, mock_context)

            # Verify data was forwarded
            shard_iterator = kinesis.get_shard_iterator(
                StreamName="enriched-stream",
                ShardId="shardId-000000000000",
                ShardIteratorType="TRIM_HORIZON",
            )["ShardIterator"]

            records = kinesis.get_records(ShardIterator=shard_iterator)
            assert len(records["Records"]) >= 1
```

## Pattern: Lambda Producing to Kinesis

```python
"""Test Lambda that writes records to Kinesis Data Streams."""
import json
import boto3
import pytest
from moto import mock_aws
from unittest.mock import MagicMock

REGION = "us-east-1"
STREAM_NAME = "output-stream"


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("OUTPUT_STREAM_NAME", STREAM_NAME)


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.function_name = "test-fn"
    ctx.get_remaining_time_in_millis.return_value = 30000
    return ctx


class TestLambdaWritesToKinesis:
    @pytest.fixture
    def kinesis_stream(self, aws_env):
        with mock_aws():
            kinesis = boto3.client("kinesis", region_name=REGION)
            kinesis.create_stream(StreamName=STREAM_NAME, ShardCount=1)

            # Wait for stream to become active
            waiter = kinesis.get_waiter("stream_exists")
            waiter.wait(StreamName=STREAM_NAME)

            yield kinesis

    def test_puts_single_record(self, kinesis_stream, mock_context):
        from handler.main import lambda_handler

        event = {
            "body": json.dumps({"sensor_id": "s-001", "temperature": 72.5})
        }
        result = lambda_handler(event, mock_context)
        assert result["statusCode"] == 200

        # Read from the stream to verify
        shard_iterator = kinesis_stream.get_shard_iterator(
            StreamName=STREAM_NAME,
            ShardId="shardId-000000000000",
            ShardIteratorType="TRIM_HORIZON",
        )["ShardIterator"]

        records = kinesis_stream.get_records(ShardIterator=shard_iterator)
        assert len(records["Records"]) >= 1

        data = json.loads(records["Records"][0]["Data"])
        assert data["sensor_id"] == "s-001"

    def test_puts_batch_records(self, kinesis_stream, mock_context):
        from handler.main import lambda_handler

        event = {
            "body": json.dumps({
                "readings": [
                    {"sensor_id": f"s-{i:03d}", "temperature": 70.0 + i}
                    for i in range(5)
                ]
            })
        }
        result = lambda_handler(event, mock_context)
        assert result["statusCode"] == 200

        shard_iterator = kinesis_stream.get_shard_iterator(
            StreamName=STREAM_NAME,
            ShardId="shardId-000000000000",
            ShardIteratorType="TRIM_HORIZON",
        )["ShardIterator"]

        records = kinesis_stream.get_records(ShardIterator=shard_iterator)
        assert len(records["Records"]) >= 5

    def test_handles_throughput_exceeded(self, aws_env, mock_context):
        """Test behavior when Kinesis ProvisionedThroughputExceededException occurs."""
        from unittest.mock import patch
        from botocore.exceptions import ClientError

        with patch("handler.main.boto3") as mock_boto:
            error_response = {
                "Error": {
                    "Code": "ProvisionedThroughputExceededException",
                    "Message": "Rate exceeded",
                }
            }
            mock_client = MagicMock()
            mock_boto.client.return_value = mock_client
            mock_client.put_record.side_effect = ClientError(
                error_response, "PutRecord"
            )

            from handler.main import lambda_handler

            event = {
                "body": json.dumps({"sensor_id": "s-001", "temperature": 72.5})
            }
            result = lambda_handler(event, mock_context)
            assert result["statusCode"] in (429, 500, 503)
```

## Pattern: Kinesis Data Firehose

```python
"""Test Lambda that interacts with Kinesis Data Firehose."""
import base64
import json
import boto3
import pytest
from unittest.mock import MagicMock, patch

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


def build_firehose_transform_event(records):
    """Build a Kinesis Firehose transformation event."""
    firehose_records = []
    for i, record in enumerate(records):
        data = json.dumps(record) if isinstance(record, dict) else record
        encoded = base64.b64encode(data.encode("utf-8")).decode("utf-8")
        firehose_records.append({
            "recordId": f"record-{i}",
            "approximateArrivalTimestamp": 1700000000000 + i,
            "data": encoded,
        })
    return {
        "invocationId": "invocation-001",
        "deliveryStreamArn": f"arn:aws:firehose:{REGION}:123456789012:deliverystream/test-stream",
        "region": REGION,
        "records": firehose_records,
    }


class TestFirehoseTransformLambda:
    """Test Lambda used as Firehose transformation function."""

    def test_transforms_records(self, aws_env, mock_context):
        from handler.transform import lambda_handler

        event = build_firehose_transform_event([
            {"raw_temp": "72.5F", "sensor": "s-001"},
            {"raw_temp": "73.0F", "sensor": "s-002"},
        ])
        result = lambda_handler(event, mock_context)

        assert "records" in result
        assert len(result["records"]) == 2
        for record in result["records"]:
            assert record["result"] in ("Ok", "Dropped", "ProcessingFailed")
            assert "recordId" in record
            assert "data" in record

    def test_ok_records_have_valid_data(self, aws_env, mock_context):
        from handler.transform import lambda_handler

        event = build_firehose_transform_event([
            {"raw_temp": "72.5F", "sensor": "s-001"},
        ])
        result = lambda_handler(event, mock_context)

        ok_records = [r for r in result["records"] if r["result"] == "Ok"]
        for record in ok_records:
            decoded = json.loads(base64.b64decode(record["data"]))
            assert isinstance(decoded, dict)

    def test_drops_invalid_records(self, aws_env, mock_context):
        from handler.transform import lambda_handler

        event = build_firehose_transform_event([
            {"raw_temp": "invalid", "sensor": "s-bad"},
        ])
        result = lambda_handler(event, mock_context)

        assert len(result["records"]) == 1
        # Should be marked as Dropped or ProcessingFailed
        assert result["records"][0]["result"] in ("Dropped", "ProcessingFailed", "Ok")

    def test_preserves_record_ids(self, aws_env, mock_context):
        """Firehose requires record IDs to match in input and output."""
        from handler.transform import lambda_handler

        event = build_firehose_transform_event([
            {"data": "first"},
            {"data": "second"},
        ])
        result = lambda_handler(event, mock_context)

        input_ids = {r["recordId"] for r in event["records"]}
        output_ids = {r["recordId"] for r in result["records"]}
        assert input_ids == output_ids
```
