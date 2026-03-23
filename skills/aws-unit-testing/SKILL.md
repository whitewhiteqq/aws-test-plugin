---
name: aws-unit-testing
license: Apache-2.0
metadata:
  author: whitewhiteqq
  version: "0.1.0"
description: >
  Generate thorough unit tests for AWS Python business logic with full branch
  coverage, boundary value analysis, and edge case testing. Isolates pure
  logic from AWS dependencies using mocks. Covers every if/elif/else,
  try/except, guard clause, loop variant, and data transformation. Uses
  pytest parametrize for boundary testing and hypothesis for property-based
  testing. Use when asked to write unit tests, test business logic, test
  all branches, test edge cases, improve coverage, or test a specific
  function for any AWS Python project.
---

# AWS Unit Testing Skill

Generate unit tests that cover every branch, boundary, and edge case in
business logic by reading the actual source code.

## Core Principle

Unit tests isolate **business logic** from AWS infrastructure. Mock all
external dependencies (boto3, HTTP calls, database). Test the _logic_ only.

## How to Generate Unit Tests

### Phase 1: Identify Business Logic

Read the handler source and separate concerns:

| Layer | What It Does | Unit Test? |
|-------|-------------|-----------|
| Input parsing / validation | Extracts and validates fields | **Yes** |
| Business rules | Decisions, calculations, transformations | **Yes** |
| Data formatting / mapping | Converts between formats | **Yes** |
| AWS service calls | Reads/writes to S3, DynamoDB, etc. | No (integration test) |
| HTTP response building | Constructs status code + body | **Yes** |
| Error handling logic | Decides which error to return | **Yes** |

### Phase 2: Map Every Branch

Read the code and create a branch map. Every control flow path needs a test:

```
Function: process_order(event)
├── if not event.get("body") → 400 missing body          [test_1]
├── try: json.loads(body)
│   └── except JSONDecodeError → 400 invalid JSON         [test_2]
├── if "order_id" not in data → 400 missing order_id      [test_3]
├── if "amount" not in data → 400 missing amount           [test_4]
├── if amount <= 0 → 400 invalid amount                    [test_5]
├── if amount > 10000 → 400 exceeds limit                  [test_6]
├── if currency not in SUPPORTED → 400 unsupported         [test_7]
├── try: save_to_db(order)
│   ├── except ConditionalCheckFailed → 409 duplicate      [test_8]
│   └── except ClientError → 500 internal error            [test_9]
├── if notify_customer: send_notification()                [test_10]
└── return 200 success                                     [test_11]
```

### Phase 3: Identify Boundaries

For every numeric, string, or collection parameter, test at the boundaries:

| Parameter Type | Boundary Values to Test |
|---------------|------------------------|
| Integer/Float | 0, 1, -1, max-1, max, max+1, MIN_INT, MAX_INT |
| String | `""`, single char, max length, max+1, unicode, whitespace-only |
| List/Array | `[]`, single element, max size, max+1 |
| Optional/None | `None`, missing key, empty string vs None |
| Date/Time | epoch, now, far future, leap day, DST boundary |
| Enum/Choice | each valid value, invalid value, case mismatch |
| Boolean | `True`, `False`, `None`, truthy/falsy values |

### Phase 4: Generate Tests

For each handler, generate tests covering all branches, boundaries, AND edge cases.
See [references/boundary-branch-patterns.md](references/boundary-branch-patterns.md)
for branch/boundary patterns and [references/edge-case-patterns.md](references/edge-case-patterns.md)
for comprehensive edge case patterns.

#### Structure

```python
"""Unit tests for {module_name}.{function_name}.

Tests cover all branches, boundary values, and edge cases.
Business logic is tested in isolation — all AWS calls are mocked.
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

pytestmark = pytest.mark.unit


class TestInputValidation:
    """Tests for input parsing and validation logic."""

    def test_missing_body_returns_400(self):
        from mymodule.handler import process_order
        result = process_order({"body": None}, MagicMock())
        assert result["statusCode"] == 400
        assert "missing" in json.loads(result["body"])["error"].lower()

    def test_invalid_json_body_returns_400(self):
        from mymodule.handler import process_order
        result = process_order({"body": "not-json{"}, MagicMock())
        assert result["statusCode"] == 400

    def test_missing_required_field_returns_400(self):
        from mymodule.handler import process_order
        result = process_order(
            {"body": json.dumps({"amount": 100})},  # missing order_id
            MagicMock(),
        )
        assert result["statusCode"] == 400


class TestBusinessRules:
    """Tests for core business logic and decision paths."""

    @pytest.mark.parametrize("amount,expected_status", [
        (0, 400),       # boundary: zero
        (-1, 400),      # boundary: negative
        (0.01, 200),    # boundary: minimum valid
        (1, 200),       # small valid
        (9999.99, 200), # just under limit
        (10000, 200),   # boundary: at limit
        (10000.01, 400),# boundary: over limit
    ])
    def test_amount_boundaries(self, amount, expected_status):
        from mymodule.handler import process_order
        event = {"body": json.dumps({"order_id": "ORD-1", "amount": amount})}
        with patch("mymodule.handler.save_to_db"):
            result = process_order(event, MagicMock())
        assert result["statusCode"] == expected_status

    @pytest.mark.parametrize("currency", ["USD", "EUR", "GBP", "JPY"])
    def test_supported_currencies_accepted(self, currency):
        from mymodule.handler import process_order
        event = {"body": json.dumps({
            "order_id": "ORD-1", "amount": 100, "currency": currency,
        })}
        with patch("mymodule.handler.save_to_db"):
            result = process_order(event, MagicMock())
        assert result["statusCode"] == 200

    def test_unsupported_currency_rejected(self):
        from mymodule.handler import process_order
        event = {"body": json.dumps({
            "order_id": "ORD-1", "amount": 100, "currency": "INVALID",
        })}
        result = process_order(event, MagicMock())
        assert result["statusCode"] == 400


class TestEdgeCases:
    """Tests for edge cases and unusual inputs."""

    # --- Null / missing / empty distinction ---
    @pytest.mark.parametrize("value,description", [
        (None,  "explicit null"),
        ("",    "empty string"),
        (" ",   "whitespace only"),
    ])
    def test_null_vs_missing_vs_empty(self, value, description):
        """Distinguish between key=None, key missing, and key=''."""
        event = {"body": json.dumps({"order_id": value})}
        result = process_order(event, MagicMock())
        assert result["statusCode"] == 400

    def test_missing_key_entirely(self):
        """Key not present in dict at all."""
        event = {"body": json.dumps({"amount": 100})}  # no order_id key
        result = process_order(event, MagicMock())
        assert result["statusCode"] == 400

    # --- Type confusion ---
    @pytest.mark.parametrize("amount", [
        "100",       # string instead of number
        True,        # bool (True == 1 in Python!)
        [100],       # list
        {"v": 100},  # dict
    ])
    def test_wrong_type_for_numeric_field(self, amount):
        """Numeric fields receiving non-numeric types must not crash."""
        event = {"body": json.dumps({"order_id": "ORD-1", "amount": amount})}
        result = process_order(event, MagicMock())
        assert result["statusCode"] in (200, 400)

    # --- Malformed events (API Gateway quirks) ---
    @pytest.mark.parametrize("event", [
        None,                                    # None event
        {},                                      # empty dict
        {"httpMethod": "GET"},                   # no path, no params
        {"pathParameters": None},                # API GW sends null
        {"queryStringParameters": None},         # API GW sends null
        {"body": None, "httpMethod": "POST"},    # POST with null body
    ])
    def test_malformed_event_shapes(self, event):
        """Handler must not crash on unexpected event shapes."""
        result = process_order(event, MagicMock())
        assert isinstance(result, dict)
        assert "statusCode" in result

    # --- Special characters & injection ---
    @pytest.mark.parametrize("value", [
        "café",                          # accented
        "🎉🚀",                          # emoji
        "日本語",                          # CJK
        "<script>alert(1)</script>",     # XSS
        "'; DROP TABLE --",              # SQL injection
        "../../../etc/passwd",           # path traversal
    ])
    def test_special_characters_dont_crash(self, value):
        """Unusual characters must be handled safely."""
        event = {"body": json.dumps({"order_id": value, "amount": 100})}
        with patch("mymodule.handler.save_to_db"):
            result = process_order(event, MagicMock())
        assert isinstance(result, dict)

    # --- Numeric extremes ---
    @pytest.mark.parametrize("amount", [
        float("inf"),    # infinity
        float("-inf"),   # negative infinity
        float("nan"),    # NaN
        1e308,           # near max float
        2**53 + 1,       # beyond float precision
    ])
    def test_numeric_extremes(self, amount):
        """Extreme numeric values must not crash."""
        event = {"body": json.dumps({"order_id": "ORD-1", "amount": amount})}
        result = process_order(event, MagicMock())
        assert result["statusCode"] in (400, 500)

    # --- Large payloads ---
    def test_very_large_payload(self):
        """Payloads near API Gateway's 10MB limit."""
        large = {"order_id": "ORD-1", "amount": 100, "data": "x" * 1_000_000}
        event = {"body": json.dumps(large)}
        with patch("mymodule.handler.save_to_db"):
            result = process_order(event, MagicMock())
        assert "statusCode" in result

    # --- JSON edge cases ---
    @pytest.mark.parametrize("body", [
        "",              # empty string
        "{",             # unclosed brace
        "null",          # JSON null
        "[1,2,3]",       # array instead of object
        "{'key': 'v'}", # Python dict syntax (single quotes)
    ])
    def test_malformed_json_body(self, body):
        """Malformed bodies must return 400, not crash."""
        event = {"httpMethod": "POST", "body": body}
        result = process_order(event, MagicMock())
        assert result["statusCode"] == 400

    # --- DynamoDB Decimal serialization ---
    def test_dynamodb_decimal_in_response(self):
        """DynamoDB returns Decimal — json.dumps(Decimal) raises TypeError."""
        from decimal import Decimal
        # This is what DynamoDB returns:
        item = {"price": Decimal("19.99")}
        with pytest.raises(TypeError):
            json.dumps(item)
        # Handler must convert before building response

    # --- Idempotency ---
    def test_same_request_twice_is_safe(self):
        """Same request repeated must not create inconsistent state."""
        event = {"body": json.dumps({"order_id": "ORD-1", "amount": 100})}
        with patch("mymodule.handler.save_to_db"):
            result1 = process_order(event, MagicMock())
            result2 = process_order(event, MagicMock())
        assert result1["statusCode"] == result2["statusCode"]

    # --- Extra unknown fields ---
    def test_extra_fields_ignored(self):
        """Unknown fields should not cause errors."""
        event = {"body": json.dumps({
            "order_id": "ORD-1", "amount": 100,
            "unknown": "value", "__proto__": {"admin": True},
        })}
        with patch("mymodule.handler.save_to_db"):
            result = process_order(event, MagicMock())
        assert result["statusCode"] in (200, 400)


class TestDataTransformations:
    """Tests for output formatting and data mapping."""

    def test_response_body_structure(self):
        """Verify response body contains all expected fields."""
        ...

    def test_decimal_serialization(self):
        """DynamoDB Decimals must be converted to float/int for JSON."""
        ...

    def test_date_format_in_response(self):
        """Dates should be ISO 8601 format."""
        ...
```

#### Parametrized Boundary Tests

Use `@pytest.mark.parametrize` extensively:

```python
class TestStringBoundaries:
    """Boundary tests for string fields."""

    @pytest.mark.parametrize("name,expected_valid", [
        ("", False),              # empty
        (" ", False),             # whitespace only
        ("a", True),             # minimum valid
        ("a" * 255, True),       # at max length
        ("a" * 256, False),      # over max length
        ("O'Brien", True),       # special chars
        ("名前", True),           # unicode
        ("  trimmed  ", True),   # leading/trailing spaces
    ])
    def test_name_validation(self, name, expected_valid):
        result = validate_name(name)
        assert result.is_valid == expected_valid


class TestNumericBoundaries:
    """Boundary tests for numeric fields."""

    @pytest.mark.parametrize("value,expected_valid", [
        (None, False),
        (0, False),              # zero not allowed
        (-1, False),             # negative
        (1, True),               # minimum valid
        (999999, True),          # large but valid
        (1e10, False),           # too large
        (0.001, True),           # small decimal
        (float("inf"), False),   # infinity
        (float("nan"), False),   # NaN
    ])
    def test_quantity_validation(self, value, expected_valid):
        result = validate_quantity(value)
        assert result.is_valid == expected_valid


class TestCollectionBoundaries:
    """Boundary tests for lists, dicts, sets."""

    @pytest.mark.parametrize("items,expected_valid", [
        ([], False),             # empty list
        ([1], True),             # single item
        (list(range(100)), True),# at limit
        (list(range(101)), False),# over limit
        (None, False),           # None instead of list
    ])
    def test_items_list_validation(self, items, expected_valid):
        result = validate_items(items)
        assert result.is_valid == expected_valid
```

#### Testing Every Error Handler

```python
class TestErrorHandling:
    """Every except block must have a corresponding test."""

    def test_json_decode_error(self):
        """Covers: except json.JSONDecodeError"""
        result = handler({"body": "{"}, ctx)
        assert result["statusCode"] == 400
        assert "JSON" in json.loads(result["body"])["error"]

    def test_key_error_missing_field(self):
        """Covers: except KeyError"""
        result = handler({"body": "{}"}, ctx)
        assert result["statusCode"] == 400

    def test_value_error_invalid_type(self):
        """Covers: except ValueError"""
        result = handler({"body": '{"amount": "not-a-number"}'}, ctx)
        assert result["statusCode"] == 400

    def test_unexpected_exception_returns_500(self):
        """Covers: except Exception (catch-all)"""
        with patch("module.handler.process") as mock_proc:
            mock_proc.side_effect = RuntimeError("unexpected")
            result = handler(valid_event, ctx)
        assert result["statusCode"] == 500
        # Verify error details are NOT leaked to caller
        body = json.loads(result["body"])
        assert "RuntimeError" not in body.get("error", "")
```

#### Testing Pure Functions Separately

Extract and test pure functions independently:

```python
# If the handler has helper functions, test them directly:

class TestCalculateDiscount:
    """Unit tests for calculate_discount() helper."""

    def test_no_discount_below_threshold(self):
        assert calculate_discount(amount=50, tier="basic") == 0

    def test_standard_discount(self):
        assert calculate_discount(amount=200, tier="premium") == 20.0

    def test_max_discount_cap(self):
        assert calculate_discount(amount=99999, tier="premium") == 500.0

    @pytest.mark.parametrize("tier", ["basic", "premium", "enterprise"])
    def test_all_tiers_return_non_negative(self, tier):
        result = calculate_discount(amount=100, tier=tier)
        assert result >= 0


class TestFormatResponse:
    """Unit tests for format_response() helper."""

    def test_success_response_structure(self):
        resp = format_response(200, {"id": "123"})
        assert resp["statusCode"] == 200
        assert resp["headers"]["Content-Type"] == "application/json"
        body = json.loads(resp["body"])
        assert body["id"] == "123"

    def test_error_response_no_stack_trace(self):
        resp = format_response(500, {"error": "internal"})
        body = json.loads(resp["body"])
        assert "traceback" not in body
        assert "stack" not in body
```

## Branch Coverage Checklist

When generating tests, verify coverage for ALL of these:

- [ ] Every `if` has a `True` test AND a `False` test
- [ ] Every `elif` has its own test
- [ ] Every `else` has its own test
- [ ] Every `try` block has a success test
- [ ] Every `except` block has its own test (with specific exception)
- [ ] Every `except` with `if e.response["Error"]["Code"]` has per-code tests
- [ ] Every early `return` has a test that triggers it
- [ ] Every `for` loop: test with 0 items, 1 item, many items
- [ ] Every `while` loop: test termination condition
- [ ] Every ternary expression: test both outcomes
- [ ] Every `assert` statement: test the assertion failure path
- [ ] Every default parameter: test with and without providing it
- [ ] Every `Optional` field: test with `None` and with a value
- [ ] Every dict `.get(key, default)`: test when key exists and when missing

## Edge Case Checklist

When generating tests, also verify coverage for ALL of these:

- [ ] **Null/None**: field explicitly `null` vs key missing vs empty string `""`
- [ ] **Empty collections**: `[]`, `{}`, `""`, `set()`
- [ ] **Type confusion**: string-where-int-expected, `bool`-as-`int`, list-as-scalar
- [ ] **Large inputs**: near Lambda's 6MB response limit, near API GW 10MB body limit
- [ ] **Special characters**: unicode (CJK, emoji, RTL), control chars, null bytes
- [ ] **Injection payloads**: SQL injection, XSS, path traversal, template injection
- [ ] **Numeric extremes**: `inf`, `-inf`, `NaN`, negative zero, `2**53+1`, `0.1+0.2`
- [ ] **Date/time**: leap days, DST, timezone-naive vs aware, epoch, far future, invalid
- [ ] **AWS quirks**: API GW null `queryStringParameters`, S3 key URL-encoding, SQS duplicates
- [ ] **Concurrency**: module-level state bleed between warm invocations, `/tmp` persistence
- [ ] **Response format**: API GW `body` must be `str`, `statusCode` must be `int`
- [ ] **DynamoDB**: `Decimal` serialization, reserved words, empty strings, 400KB item limit
- [ ] **Idempotency**: same request twice produces same result (no duplicates)
- [ ] **Encoding**: UTF-8, base64 `isBase64Encoded`, mixed encodings in headers
- [ ] **Extra fields**: unknown keys in request don't crash or get executed

## Mock Strategy for Unit Tests

```python
# GOOD: Mock at the boundary (AWS calls)
with patch("mymodule.handler.boto3.client") as mock_client:
    mock_client.return_value.get_item.return_value = {"Item": {"id": "123"}}
    result = handler(event, ctx)

# GOOD: Mock a specific helper that makes external calls
with patch("mymodule.handler.fetch_from_s3") as mock_fetch:
    mock_fetch.return_value = {"data": "value"}
    result = handler(event, ctx)

# BAD: Don't mock the function under test
# BAD: Don't mock internal pure functions
# BAD: Don't mock Python builtins (json.loads, etc.)
```

## Commands

```bash
# Run all unit tests
pytest tests/unit/ -v -m unit

# Run with coverage
pytest tests/unit/ -v -m unit --cov=src/ --cov-report=term-missing --cov-branch

# Run a specific test class
pytest tests/unit/test_handler.py::TestBusinessRules -v

# Run with verbose failure output
pytest tests/unit/ -v -m unit --tb=long
```

## Markers

```python
pytestmark = pytest.mark.unit
```
