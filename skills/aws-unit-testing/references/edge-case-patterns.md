# Edge Case Testing Patterns for AWS Python Handlers

Comprehensive patterns for edge cases that commonly cause bugs in Lambda
handlers, Batch jobs, and API Gateway integrations.

## Category 1: Malformed & Adversarial Input

### Event Shape Variations

Lambda can receive events in many unexpected forms depending on the trigger.

```python
import json
import pytest
from unittest.mock import MagicMock

pytestmark = pytest.mark.unit


class TestMalformedEvents:
    """Edge cases for unexpected event shapes."""

    # --- Completely wrong event types ---
    @pytest.mark.parametrize("event", [
        None,                           # None event
        "",                             # empty string
        0,                              # zero
        [],                             # empty list
        "raw string body",             # plain string instead of dict
        42,                             # integer
        True,                           # boolean
    ])
    def test_non_dict_event(self, event, handler, ctx):
        """Handler must not crash on non-dict events."""
        result = handler(event, ctx)
        assert result["statusCode"] in (400, 500)

    # --- Missing top-level keys ---
    @pytest.mark.parametrize("event", [
        {},                                          # empty dict
        {"httpMethod": "GET"},                       # no path, no params
        {"pathParameters": None},                    # explicit None
        {"body": None, "httpMethod": "POST"},        # POST with None body
        {"queryStringParameters": None},             # explicit None (API GW does this)
        {"headers": None},                           # null headers
        {"requestContext": {}},                       # empty request context
    ])
    def test_missing_event_keys(self, event, handler, ctx):
        """Handler must gracefully handle missing top-level keys."""
        result = handler(event, ctx)
        assert isinstance(result, dict)
        assert "statusCode" in result

    # --- API Gateway sends null for missing optional fields ---
    def test_api_gw_null_query_params(self, handler, ctx):
        """API Gateway sends queryStringParameters: null when no query string."""
        event = {
            "httpMethod": "GET",
            "path": "/resource/123",
            "pathParameters": {"id": "123"},
            "queryStringParameters": None,  # NOT {} — API GW sends null
            "headers": {"Content-Type": "application/json"},
            "body": None,
        }
        result = handler(event, ctx)
        assert result["statusCode"] != 500  # Must not crash on None

    def test_api_gw_null_path_params(self, handler, ctx):
        """API Gateway sends pathParameters: null for root routes."""
        event = {
            "httpMethod": "GET",
            "path": "/",
            "pathParameters": None,
            "queryStringParameters": None,
            "headers": {},
            "body": None,
        }
        result = handler(event, ctx)
        assert isinstance(result, dict)


class TestMalformedBody:
    """Edge cases for request body parsing."""

    @pytest.mark.parametrize("body,description", [
        ("", "empty string"),
        (" ", "whitespace only"),
        ("{", "unclosed brace"),
        ('{"key": }', "invalid value"),
        ("null", "JSON null literal"),
        ("true", "JSON boolean"),
        ("42", "JSON number"),
        ('"just a string"', "JSON string"),
        ("[1,2,3]", "JSON array instead of object"),
        ('{"key": "val",}', "trailing comma"),
        ("{'key': 'val'}", "single quotes (Python, not JSON)"),
        ("\x00\x01\x02", "binary/control characters"),
        ('{"a": "\ud800"}', "lone surrogate in unicode"),
    ])
    def test_malformed_json_body(self, body, description, handler, ctx):
        """Handler must reject or handle malformed bodies without crashing."""
        event = {"httpMethod": "POST", "body": body, "headers": {}}
        result = handler(event, ctx)
        assert result["statusCode"] in (400, 422)

    def test_nested_json_depth_bomb(self, handler, ctx):
        """Deeply nested JSON should not cause stack overflow."""
        # 100 levels of nesting
        body = '{"a":' * 100 + '1' + '}' * 100
        event = {"httpMethod": "POST", "body": body, "headers": {}}
        result = handler(event, ctx)
        assert "statusCode" in result

    def test_very_large_body(self, handler, ctx):
        """Body at/near API Gateway's 10MB limit."""
        large_data = {"data": "x" * (6 * 1024 * 1024)}  # 6MB string
        event = {
            "httpMethod": "POST",
            "body": json.dumps(large_data),
            "headers": {},
        }
        result = handler(event, ctx)
        assert "statusCode" in result  # Must not OOM or hang

    def test_base64_encoded_body(self, handler, ctx):
        """API Gateway may base64-encode binary bodies."""
        import base64
        event = {
            "httpMethod": "POST",
            "body": base64.b64encode(b'{"key":"value"}').decode(),
            "isBase64Encoded": True,
            "headers": {"Content-Type": "application/json"},
        }
        result = handler(event, ctx)
        assert "statusCode" in result
```

## Category 2: Type Confusion & Coercion

```python
class TestTypeConfusion:
    """Fields arriving as unexpected Python types."""

    @pytest.mark.parametrize("order_id", [
        123,              # int instead of str
        12.5,             # float instead of str
        True,             # bool (truthy but not a string)
        ["ORD-1"],        # list containing the value
        {"id": "ORD-1"}, # nested dict
    ])
    def test_wrong_type_for_string_field(self, order_id, handler, ctx):
        """String fields receiving non-string types."""
        event = make_event(body={"order_id": order_id, "amount": 100})
        result = handler(event, ctx)
        assert result["statusCode"] in (200, 400)  # accept or reject, never crash

    @pytest.mark.parametrize("amount", [
        "100",            # string instead of number
        "100.50",         # string decimal
        "1e5",            # scientific notation string
        "",               # empty string
        "abc",            # non-numeric string
        True,             # bool (True == 1 in Python!)
        False,            # bool (False == 0)
        [100],            # list
        None,             # null
    ])
    def test_wrong_type_for_numeric_field(self, amount, handler, ctx):
        """Numeric fields receiving non-numeric types."""
        event = make_event(body={"order_id": "ORD-1", "amount": amount})
        result = handler(event, ctx)
        assert result["statusCode"] in (200, 400)

    def test_boolean_true_equals_one(self):
        """Python's True == 1 can bypass numeric validation."""
        # If code checks `isinstance(x, int)`, True passes!
        assert isinstance(True, int)  # This is True in Python
        # Handler should check: isinstance(x, bool) first, or use strict validation

    def test_string_number_zero(self, handler, ctx):
        """'0' is falsy-looking but is a valid non-empty string."""
        event = make_event(body={"order_id": "0", "amount": 100})
        result = handler(event, ctx)
        # "0" should be accepted as a valid order_id
        assert result["statusCode"] == 200
```

## Category 3: Encoding & Character Set Issues

```python
class TestEncodingEdgeCases:
    """Unicode, encoding, and special character handling."""

    @pytest.mark.parametrize("value,description", [
        ("café",           "accented characters"),
        ("日本語テスト",      "CJK characters"),
        ("🎉🚀💯",          "emoji"),
        ("مرحبا",          "RTL (Arabic)"),
        ("\t\n\r",         "control characters"),
        ("foo\x00bar",     "null byte in middle"),
        ("a" * 10000,      "very long string"),
        ("<script>alert(1)</script>", "HTML/XSS payload"),
        ("'; DROP TABLE --", "SQL injection payload"),
        ("${jndi:ldap://x}", "JNDI injection payload"),
        ("{{7*7}}",         "template injection"),
        ("../../../etc/passwd", "path traversal"),
        ("%00%0a%0d",      "URL-encoded control chars"),
        ("Robert'); DROP TABLE Students;--", "Bobby Tables"),
    ])
    def test_special_characters_in_input(self, value, description, handler, ctx):
        """Handler must not crash or be exploited by special characters.
        The handler should either accept, sanitize, or reject — never crash or execute."""
        event = make_event(body={"name": value, "order_id": "ORD-1", "amount": 100})
        with patch_aws():
            result = handler(event, ctx)
        # Must return a valid response (not crash, not execute injections)
        assert isinstance(result, dict)
        assert "statusCode" in result

    def test_mixed_encoding_in_headers(self, handler, ctx):
        """Headers with non-ASCII values."""
        event = make_event(
            headers={"X-Custom": "value_with_ñ_and_ü"}
        )
        result = handler(event, ctx)
        assert "statusCode" in result
```

## Category 4: Numeric Edge Cases

```python
import math
from decimal import Decimal, InvalidOperation


class TestNumericEdgeCases:
    """Numbers that commonly break Python code."""

    @pytest.mark.parametrize("value,description", [
        (0, "zero"),
        (-0, "negative zero"),
        (-0.0, "negative zero float"),
        (float("inf"), "positive infinity"),
        (float("-inf"), "negative infinity"),
        (float("nan"), "NaN"),
        (1e308, "near max float"),
        (-1e308, "near min float"),
        (1e-308, "near min positive float"),
        (2**53 + 1, "beyond float precision (int)"),
        (0.1 + 0.2, "floating point imprecision (0.30000000000000004)"),
        (999999999999999999, "large integer"),
        (-999999999999999999, "large negative integer"),
    ])
    def test_numeric_extremes(self, value, description, handler, ctx):
        """Handler must handle numeric edge cases without crashing."""
        event = make_event(body={"order_id": "ORD-1", "amount": value})
        result = handler(event, ctx)
        assert "statusCode" in result

    def test_dynamodb_decimal_vs_float(self):
        """DynamoDB returns Decimal, not float. json.dumps(Decimal) raises TypeError."""
        from decimal import Decimal
        item = {"price": Decimal("19.99"), "quantity": Decimal("3")}
        # This WILL crash: json.dumps(item)
        # Handler must convert Decimals before JSON serialization
        with pytest.raises(TypeError):
            json.dumps(item)
        # Correct approach:
        converted = {k: float(v) if isinstance(v, Decimal) else v for k, v in item.items()}
        assert json.dumps(converted)  # Should not raise

    def test_division_by_zero(self, handler, ctx):
        """If handler computes ratios/averages, zero divisor must be handled."""
        event = make_event(body={"total": 100, "count": 0})
        result = handler(event, ctx)
        assert result["statusCode"] != 500

    def test_floating_point_comparison(self):
        """Floating point equality is unreliable."""
        # 0.1 + 0.2 != 0.3 in floating point
        assert 0.1 + 0.2 != 0.3
        assert math.isclose(0.1 + 0.2, 0.3)
        # Handlers should use math.isclose() or Decimal for money
```

## Category 5: Time & Date Edge Cases

```python
from datetime import datetime, timezone, timedelta


class TestDateTimeEdgeCases:
    """Dates and times that commonly cause bugs."""

    @pytest.mark.parametrize("timestamp,description", [
        ("2024-01-01T00:00:00Z", "midnight UTC"),
        ("2024-02-29T12:00:00Z", "leap day"),
        ("2025-02-29T12:00:00Z", "invalid leap day (2025 is not leap)"),
        ("2024-12-31T23:59:59Z", "last second of year"),
        ("2024-01-01T00:00:00+05:30", "non-UTC timezone"),
        ("2024-03-10T02:30:00-05:00", "during DST spring forward (doesn't exist)"),
        ("2024-11-03T01:30:00-05:00", "during DST fall back (ambiguous)"),
        ("1970-01-01T00:00:00Z", "Unix epoch"),
        ("2038-01-19T03:14:07Z", "Y2K38 boundary"),
        ("9999-12-31T23:59:59Z", "far future"),
        ("2024-01-01", "date without time"),
        ("not-a-date", "invalid string"),
        ("", "empty string"),
        ("2024-13-01T00:00:00Z", "invalid month (13)"),
        ("2024-01-32T00:00:00Z", "invalid day (32)"),
        ("2024-01-01T25:00:00Z", "invalid hour (25)"),
    ])
    def test_timestamp_parsing(self, timestamp, description, handler, ctx):
        """Handler must parse or reject timestamps without crashing."""
        event = make_event(body={"timestamp": timestamp, "order_id": "ORD-1"})
        result = handler(event, ctx)
        assert "statusCode" in result

    def test_timezone_naive_vs_aware(self):
        """Comparing naive and aware datetimes raises TypeError."""
        naive = datetime(2024, 1, 1)
        aware = datetime(2024, 1, 1, tzinfo=timezone.utc)
        with pytest.raises(TypeError):
            _ = naive < aware
        # Handler should always use timezone-aware datetimes

    def test_ttl_expiry_at_boundary(self, handler, ctx):
        """DynamoDB TTL: item at exact expiry time."""
        now = int(datetime.now(timezone.utc).timestamp())
        event = make_event(body={"ttl": now})  # expires RIGHT NOW
        result = handler(event, ctx)
        assert "statusCode" in result
```

## Category 6: Concurrency & State Edge Cases

```python
class TestConcurrencyEdgeCases:
    """Edge cases from Lambda's concurrent execution model."""

    def test_handler_with_module_level_state(self, handler, ctx):
        """Module-level variables persist across warm invocations.
        Each test call simulates a warm invoke."""
        event1 = make_event(body={"order_id": "ORD-1", "amount": 100})
        event2 = make_event(body={"order_id": "ORD-2", "amount": 200})
        with patch_aws():
            result1 = handler(event1, ctx)
            result2 = handler(event2, ctx)
        # Results must be independent — no state leaking between invocations
        body1 = json.loads(result1["body"])
        body2 = json.loads(result2["body"])
        assert body1.get("order_id") != body2.get("order_id")

    def test_handler_clears_temp_files(self, handler, ctx, tmp_path):
        """Lambda's /tmp is shared across warm invocations (512MB limit)."""
        # Simulate handler writing to /tmp
        with patch("tempfile.gettempdir", return_value=str(tmp_path)):
            event = make_event(body={"order_id": "ORD-1"})
            with patch_aws():
                handler(event, ctx)
            # Verify handler cleaned up or uses unique filenames
            remaining = list(tmp_path.iterdir())
            assert len(remaining) == 0, f"Handler left temp files: {remaining}"

    def test_context_time_remaining(self, handler):
        """Handler should check remaining time before long operations."""
        ctx = MagicMock()
        ctx.get_remaining_time_in_millis.return_value = 100  # Only 100ms left!
        event = make_event(body={"order_id": "ORD-1", "amount": 100})
        with patch_aws():
            result = handler(event, ctx)
        # Handler should return early or handle timeout gracefully
        assert "statusCode" in result
```

## Category 7: AWS-Specific Edge Cases

```python
class TestAWSEdgeCases:
    """Edge cases specific to AWS service behavior."""

    def test_dynamodb_empty_string_attribute(self):
        """DynamoDB does not allow empty string attributes (pre-2020 tables)."""
        # Handler must filter out empty strings before put_item
        pass

    def test_dynamodb_reserved_word_as_key(self):
        """DynamoDB query fails if attribute name is a reserved word."""
        # 'name', 'status', 'data', 'date' are all reserved
        # Handler must use ExpressionAttributeNames: {"#n": "name"}
        pass

    def test_s3_key_with_special_chars(self, handler, ctx):
        """S3 keys can contain spaces, unicode, and special characters."""
        event = make_event(body={"key": "path/to/file with spaces (1).json"})
        with patch_aws():
            result = handler(event, ctx)
        assert "statusCode" in result

    def test_s3_key_url_encoding(self, handler, ctx):
        """S3 event notifications URL-encode the key. Handler must decode."""
        # S3 event sends: "object": {"key": "path/to/my+file.json"}
        # The + represents a space. Handler must urllib.parse.unquote_plus()
        event = {
            "Records": [{
                "s3": {
                    "bucket": {"name": "my-bucket"},
                    "object": {"key": "dir/my+file+name.json"},
                }
            }]
        }
        with patch_aws():
            result = handler(event, ctx)
        # Verify handler decoded the key correctly

    def test_sqs_duplicate_message(self, handler, ctx):
        """SQS can deliver the same message more than once.
        Handler must be idempotent."""
        message = {"messageId": "msg-1", "body": '{"order_id": "ORD-1"}'}
        event = {"Records": [message, message]}  # Duplicate!
        with patch_aws():
            result = handler(event, ctx)
        # Second processing should not create duplicates or crash

    def test_sqs_batch_partial_failure(self, handler, ctx):
        """Handler should report partial batch failures, not fail the whole batch."""
        records = [
            {"messageId": "1", "body": '{"order_id": "good"}'},
            {"messageId": "2", "body": "invalid-json"},  # Bad record
            {"messageId": "3", "body": '{"order_id": "also-good"}'},
        ]
        event = {"Records": records}
        with patch_aws():
            result = handler(event, ctx)
        # Should return batchItemFailures for partial failure reporting
        if "batchItemFailures" in result:
            failed_ids = [f["itemIdentifier"] for f in result["batchItemFailures"]]
            assert "2" in failed_ids
            assert "1" not in failed_ids

    def test_lambda_response_size_limit(self, handler, ctx):
        """Lambda sync invoke response max is 6MB. Handler must not exceed."""
        event = make_event(body={"query": "return_everything"})
        with patch_aws():
            result = handler(event, ctx)
        response_size = len(json.dumps(result).encode("utf-8"))
        assert response_size < 6 * 1024 * 1024, (
            f"Response is {response_size / 1024 / 1024:.1f}MB — exceeds 6MB Lambda limit"
        )

    def test_api_gateway_response_format(self, handler, ctx):
        """API Gateway proxy requires exact response shape."""
        event = make_event(method="GET", path_params={"id": "123"})
        with patch_aws():
            result = handler(event, ctx)
        # Must have these exact keys for API GW proxy integration
        assert "statusCode" in result
        assert isinstance(result["statusCode"], int)
        # body must be a string (not dict)
        if "body" in result:
            assert isinstance(result["body"], str)
        # headers must be a dict of str->str
        if "headers" in result:
            assert isinstance(result["headers"], dict)
```

## Category 8: Empty / Missing / Default Value Matrix

Use this pattern to systematically test every field:

```python
class TestFieldPresenceMatrix:
    """Systematic test of every combination of present/missing/null/empty."""

    FIELDS = ["order_id", "amount", "currency", "description"]

    @pytest.mark.parametrize("missing_field", FIELDS)
    def test_one_required_field_missing(self, missing_field, handler, ctx):
        """Remove one required field at a time."""
        data = {"order_id": "ORD-1", "amount": 100, "currency": "USD"}
        data.pop(missing_field, None)
        event = make_event(body=data)
        result = handler(event, ctx)
        # Required fields → 400; optional fields → 200
        assert result["statusCode"] in (200, 400)

    @pytest.mark.parametrize("null_field", FIELDS)
    def test_one_field_null(self, null_field, handler, ctx):
        """Set one field to None (JSON null)."""
        data = {"order_id": "ORD-1", "amount": 100, "currency": "USD"}
        data[null_field] = None
        event = make_event(body=data)
        result = handler(event, ctx)
        assert result["statusCode"] in (200, 400)

    @pytest.mark.parametrize("empty_field", ["order_id", "currency", "description"])
    def test_one_string_field_empty(self, empty_field, handler, ctx):
        """Set one string field to empty string."""
        data = {"order_id": "ORD-1", "amount": 100, "currency": "USD"}
        data[empty_field] = ""
        event = make_event(body=data)
        result = handler(event, ctx)
        assert result["statusCode"] in (200, 400)

    def test_all_optional_fields_missing(self, handler, ctx):
        """Only required fields present."""
        event = make_event(body={"order_id": "ORD-1", "amount": 100})
        with patch_aws():
            result = handler(event, ctx)
        assert result["statusCode"] == 200

    def test_extra_unknown_fields_ignored(self, handler, ctx):
        """Unknown fields should be ignored, not cause errors."""
        data = {
            "order_id": "ORD-1", "amount": 100,
            "unknown_field": "value",
            "__proto__": {"admin": True},  # Prototype pollution attempt
            "constructor": "evil",
        }
        event = make_event(body=data)
        with patch_aws():
            result = handler(event, ctx)
        assert result["statusCode"] in (200, 400)  # Accept or reject, never crash
```

## Edge Case Checklist

When generating tests, verify coverage for ALL of these edge case categories:

- [ ] **Null/None**: field explicitly `null` vs missing vs empty string
- [ ] **Empty collections**: `[]`, `{}`, `""`, `set()`
- [ ] **Type confusion**: string-where-int-expected, bool-as-int, list-as-scalar
- [ ] **Large inputs**: near memory limits, near API Gateway size limits
- [ ] **Special characters**: unicode, emoji, control chars, null bytes
- [ ] **Injection payloads**: SQL, XSS, path traversal, template injection
- [ ] **Numeric extremes**: infinity, NaN, negative zero, float precision
- [ ] **Date/time**: leap days, DST, timezones, epoch, far future, invalid dates
- [ ] **AWS quirks**: null queryStringParameters, S3 key encoding, SQS duplicates
- [ ] **Concurrency**: module-level state, /tmp persistence, timeout
- [ ] **Response format**: API GW body must be string, size limit, headers dict
- [ ] **DynamoDB**: Decimal type, reserved words, empty strings, large items (400KB)
- [ ] **Duplicate/idempotent**: same request twice returns same result
- [ ] **Encoding**: UTF-8, base64-encoded body, mixed encodings
