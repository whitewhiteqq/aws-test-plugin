# Lambda + DynamoDB Integration Patterns

Moto-based patterns for testing Lambda functions that interact with DynamoDB.

## Pattern: CRUD Operations

```python
"""Test Lambda that performs DynamoDB CRUD operations."""
import json
import boto3
import pytest
from moto import mock_aws
from unittest.mock import MagicMock

REGION = "us-east-1"
TABLE_NAME = "test-table"


@pytest.fixture
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("TABLE_NAME", TABLE_NAME)


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.function_name = "test-fn"
    ctx.memory_limit_in_mb = 256
    ctx.get_remaining_time_in_millis.return_value = 30000
    return ctx


class TestDynamoDBGetItem:
    @pytest.fixture
    def table_with_item(self, aws_env):
        with mock_aws():
            dynamodb = boto3.resource("dynamodb", region_name=REGION)
            table = dynamodb.create_table(
                TableName=TABLE_NAME,
                KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
            table.put_item(Item={
                "id": "test-123",
                "name": "Test Record",
                "status": "active",
            })
            yield table

    def test_get_existing_item(self, table_with_item, mock_context):
        from handler.main import lambda_handler

        event = {"pathParameters": {"id": "test-123"}}
        result = lambda_handler(event, mock_context)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["name"] == "Test Record"

    def test_get_nonexistent_item(self, table_with_item, mock_context):
        from handler.main import lambda_handler

        event = {"pathParameters": {"id": "nonexistent"}}
        result = lambda_handler(event, mock_context)
        assert result["statusCode"] in (404, 200)


class TestDynamoDBPutItem:
    @pytest.fixture
    def empty_table(self, aws_env):
        with mock_aws():
            dynamodb = boto3.resource("dynamodb", region_name=REGION)
            table = dynamodb.create_table(
                TableName=TABLE_NAME,
                KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
            yield table

    def test_creates_new_item(self, empty_table, mock_context):
        from handler.main import lambda_handler

        event = {
            "body": json.dumps({
                "id": "new-item-1",
                "name": "New Record",
                "status": "active",
            })
        }
        result = lambda_handler(event, mock_context)
        assert result["statusCode"] in (200, 201)

        # Verify it was written
        item = empty_table.get_item(Key={"id": "new-item-1"})
        assert "Item" in item
        assert item["Item"]["name"] == "New Record"

    def test_create_with_missing_required_field(self, empty_table, mock_context):
        from handler.main import lambda_handler

        event = {"body": json.dumps({})}
        result = lambda_handler(event, mock_context)
        assert result["statusCode"] == 400
```

## Pattern: Query with GSI

```python
class TestDynamoDBQuery:
    @pytest.fixture
    def table_with_gsi(self, aws_env):
        with mock_aws():
            dynamodb = boto3.resource("dynamodb", region_name=REGION)
            table = dynamodb.create_table(
                TableName=TABLE_NAME,
                KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                AttributeDefinitions=[
                    {"AttributeName": "id", "AttributeType": "S"},
                    {"AttributeName": "status", "AttributeType": "S"},
                ],
                GlobalSecondaryIndexes=[{
                    "IndexName": "status-index",
                    "KeySchema": [{"AttributeName": "status", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                }],
                BillingMode="PAY_PER_REQUEST",
            )
            # Seed test data
            for i in range(5):
                table.put_item(Item={
                    "id": f"item-{i}",
                    "name": f"Record {i}",
                    "status": "active" if i < 3 else "inactive",
                })
            yield table

    def test_query_by_status(self, table_with_gsi, mock_context):
        from handler.main import lambda_handler

        event = {
            "body": json.dumps({"status": "active"}),
            "httpMethod": "POST",
        }
        result = lambda_handler(event, mock_context)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        items = body.get("items", body.get("results", body))
        assert len(items) >= 3

    def test_query_with_no_results(self, table_with_gsi, mock_context):
        from handler.main import lambda_handler

        event = {
            "body": json.dumps({"status": "deleted"}),
            "httpMethod": "POST",
        }
        result = lambda_handler(event, mock_context)
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        items = body.get("items", body.get("results", body))
        assert len(items) == 0
```

## Pattern: Conditional Updates

```python
class TestConditionalWrite:
    @pytest.fixture
    def table_with_item(self, aws_env):
        with mock_aws():
            dynamodb = boto3.resource("dynamodb", region_name=REGION)
            table = dynamodb.create_table(
                TableName=TABLE_NAME,
                KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
            table.put_item(Item={"id": "item-1", "version": 1, "name": "Original"})
            yield table

    def test_update_with_correct_version(self, table_with_item, mock_context):
        from handler.main import lambda_handler

        event = {
            "body": json.dumps({
                "id": "item-1",
                "name": "Updated",
                "expected_version": 1,
            })
        }
        result = lambda_handler(event, mock_context)
        assert result["statusCode"] == 200

    def test_update_with_stale_version(self, table_with_item, mock_context):
        from handler.main import lambda_handler

        event = {
            "body": json.dumps({
                "id": "item-1",
                "name": "Stale Update",
                "expected_version": 99,
            })
        }
        result = lambda_handler(event, mock_context)
        # Should fail with conflict or condition check error
        assert result["statusCode"] in (409, 400, 500)
```

## Pattern: Batch Write

```python
class TestBatchWrite:
    @pytest.fixture
    def empty_table(self, aws_env):
        with mock_aws():
            dynamodb = boto3.resource("dynamodb", region_name=REGION)
            table = dynamodb.create_table(
                TableName=TABLE_NAME,
                KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
            yield table

    def test_batch_write_multiple_items(self, empty_table, mock_context):
        from handler.main import lambda_handler

        items = [{"id": f"batch-{i}", "name": f"Item {i}"} for i in range(25)]
        event = {"body": json.dumps({"items": items})}
        result = lambda_handler(event, mock_context)
        assert result["statusCode"] == 200

        # Verify all items written
        scan = empty_table.scan()
        assert scan["Count"] == 25
```
