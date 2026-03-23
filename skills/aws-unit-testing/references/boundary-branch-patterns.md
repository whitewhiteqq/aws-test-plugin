# Boundary & Branch Testing Patterns

Reusable patterns for achieving full branch coverage and boundary value testing
in AWS Python handler unit tests.

## Pattern 1: Parametrized Validation Boundaries

Use when a handler validates input fields with min/max/required constraints.

```python
import pytest
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.unit


class TestFieldValidation:
    """Boundary tests for every validated field in the handler."""

    # --- Required string field ---
    @pytest.mark.parametrize("value,should_pass", [
        (None, False),           # null
        ("", False),             # empty
        ("   ", False),          # whitespace-only
        ("a", True),             # min valid
        ("valid-name", True),    # normal
        ("a" * 255, True),      # at max
        ("a" * 256, False),     # over max
    ])
    def test_name_field(self, value, should_pass, handler, mock_deps):
        event = make_event(name=value)
        result = handler(event, MagicMock())
        if should_pass:
            assert result["statusCode"] != 400
        else:
            assert result["statusCode"] == 400

    # --- Numeric range field ---
    @pytest.mark.parametrize("value,should_pass", [
        (None, False),
        (-1, False),             # below zero
        (0, False),              # zero (if min=1)
        (1, True),               # exactly min
        (50, True),              # mid-range
        (100, True),             # exactly max
        (101, False),            # over max
        (1.5, True),             # decimal
        (float("inf"), False),   # infinity
        (float("nan"), False),   # NaN
    ])
    def test_quantity_field(self, value, should_pass, handler, mock_deps):
        event = make_event(quantity=value)
        result = handler(event, MagicMock())
        if should_pass:
            assert result["statusCode"] != 400
        else:
            assert result["statusCode"] == 400

    # --- Enum / choice field ---
    @pytest.mark.parametrize("value,should_pass", [
        ("active", True),
        ("inactive", True),
        ("ACTIVE", False),       # case sensitivity
        ("unknown", False),
        ("", False),
        (None, False),
    ])
    def test_status_field(self, value, should_pass, handler, mock_deps):
        event = make_event(status=value)
        result = handler(event, MagicMock())
        if should_pass:
            assert result["statusCode"] != 400
        else:
            assert result["statusCode"] == 400

    # --- Optional field (can be missing) ---
    @pytest.mark.parametrize("include_field,value,should_pass", [
        (False, None, True),     # key absent — OK
        (True, None, True),      # key present, value null — depends on logic
        (True, "", True),        # empty string — depends on logic
        (True, "value", True),   # normal value
    ])
    def test_optional_description(self, include_field, value, should_pass):
        data = {"required_field": "valid"}
        if include_field:
            data["description"] = value
        ...
```

## Pattern 2: Complete Branch Map

Use when a handler has complex if/elif/else chains.

```python
class TestProcessRequest:
    """One test per branch in process_request()."""

    # Branch: httpMethod == "GET"
    def test_get_request(self, handler, ctx, mock_deps):
        event = make_event(method="GET", path_params={"id": "123"})
        result = handler(event, ctx)
        assert result["statusCode"] == 200

    # Branch: httpMethod == "POST" + valid body
    def test_post_valid_body(self, handler, ctx, mock_deps):
        event = make_event(method="POST", body={"name": "test"})
        result = handler(event, ctx)
        assert result["statusCode"] == 201

    # Branch: httpMethod == "POST" + invalid body
    def test_post_invalid_body(self, handler, ctx, mock_deps):
        event = make_event(method="POST", body={})
        result = handler(event, ctx)
        assert result["statusCode"] == 400

    # Branch: httpMethod == "PUT" + item exists
    def test_put_existing_item(self, handler, ctx, mock_deps):
        mock_deps["db"].get_item.return_value = {"Item": {"id": "123"}}
        event = make_event(method="PUT", path_params={"id": "123"}, body={"name": "updated"})
        result = handler(event, ctx)
        assert result["statusCode"] == 200

    # Branch: httpMethod == "PUT" + item does not exist
    def test_put_nonexistent_item(self, handler, ctx, mock_deps):
        mock_deps["db"].get_item.return_value = {}
        event = make_event(method="PUT", path_params={"id": "999"}, body={"name": "x"})
        result = handler(event, ctx)
        assert result["statusCode"] == 404

    # Branch: httpMethod == "DELETE"
    def test_delete_item(self, handler, ctx, mock_deps):
        event = make_event(method="DELETE", path_params={"id": "123"})
        result = handler(event, ctx)
        assert result["statusCode"] in (200, 204)

    # Branch: unsupported method
    def test_unsupported_method(self, handler, ctx, mock_deps):
        event = make_event(method="PATCH")
        result = handler(event, ctx)
        assert result["statusCode"] == 405
```

## Pattern 3: Exception Path Testing

Use when the handler has try/except blocks.

```python
from botocore.exceptions import ClientError

class TestExceptionHandling:
    """One test per except clause."""

    def _make_client_error(self, code: str, message: str = "error") -> ClientError:
        return ClientError(
            {"Error": {"Code": code, "Message": message}},
            "operation_name",
        )

    # except ClientError where Code == "ConditionalCheckFailedException"
    def test_conditional_check_failed_returns_409(self, handler, ctx):
        with patch("module.handler.table") as mock_table:
            mock_table.put_item.side_effect = self._make_client_error(
                "ConditionalCheckFailedException"
            )
            result = handler(valid_event, ctx)
        assert result["statusCode"] == 409

    # except ClientError where Code == "ResourceNotFoundException"
    def test_resource_not_found_returns_404(self, handler, ctx):
        with patch("module.handler.table") as mock_table:
            mock_table.get_item.side_effect = self._make_client_error(
                "ResourceNotFoundException"
            )
            result = handler(get_event, ctx)
        assert result["statusCode"] == 404

    # except ClientError where Code == "ValidationException"
    def test_validation_exception_returns_400(self, handler, ctx):
        with patch("module.handler.table") as mock_table:
            mock_table.query.side_effect = self._make_client_error(
                "ValidationException"
            )
            result = handler(query_event, ctx)
        assert result["statusCode"] == 400

    # except ClientError (catch-all for unhandled codes)
    def test_unknown_client_error_returns_500(self, handler, ctx):
        with patch("module.handler.table") as mock_table:
            mock_table.put_item.side_effect = self._make_client_error(
                "InternalServerError"
            )
            result = handler(valid_event, ctx)
        assert result["statusCode"] == 500

    # except json.JSONDecodeError
    def test_malformed_json_returns_400(self, handler, ctx):
        result = handler({"body": "{invalid"}, ctx)
        assert result["statusCode"] == 400

    # except Exception (generic catch-all)
    def test_unexpected_error_returns_500(self, handler, ctx):
        with patch("module.handler.process") as mock_proc:
            mock_proc.side_effect = RuntimeError("boom")
            result = handler(valid_event, ctx)
        assert result["statusCode"] == 500
```

## Pattern 4: Loop and Collection Testing

```python
class TestBatchProcessing:
    """Tests for loops that process collections."""

    def test_empty_list(self, handler, ctx):
        """Loop body never executes."""
        event = make_event(body={"items": []})
        result = handler(event, ctx)
        assert result["statusCode"] == 200
        assert json.loads(result["body"])["processed"] == 0

    def test_single_item(self, handler, ctx):
        """Loop executes exactly once."""
        event = make_event(body={"items": [{"id": "1"}]})
        result = handler(event, ctx)
        assert json.loads(result["body"])["processed"] == 1

    def test_multiple_items(self, handler, ctx):
        """Normal batch."""
        items = [{"id": str(i)} for i in range(10)]
        event = make_event(body={"items": items})
        result = handler(event, ctx)
        assert json.loads(result["body"])["processed"] == 10

    def test_partial_failure_in_batch(self, handler, ctx):
        """Some items fail — handler should report partial success."""
        items = [{"id": "good"}, {"id": "bad"}, {"id": "good2"}]
        with patch("module.handler.process_item") as mock:
            mock.side_effect = [None, ValueError("bad item"), None]
            event = make_event(body={"items": items})
            result = handler(event, ctx)
        body = json.loads(result["body"])
        assert body["processed"] == 2
        assert body["failed"] == 1

    def test_max_batch_size(self, handler, ctx):
        """At the maximum allowed batch size."""
        items = [{"id": str(i)} for i in range(100)]  # max = 100
        event = make_event(body={"items": items})
        result = handler(event, ctx)
        assert result["statusCode"] == 200

    def test_over_max_batch_size(self, handler, ctx):
        """Exceeding batch size limit."""
        items = [{"id": str(i)} for i in range(101)]
        event = make_event(body={"items": items})
        result = handler(event, ctx)
        assert result["statusCode"] == 400
```

## Pattern 5: Pydantic Model Validation

Use when the handler uses pydantic for input validation.

```python
from pydantic import ValidationError

class TestPydanticValidation:
    """Test pydantic model validation covers all field constraints."""

    def test_valid_payload(self):
        model = OrderRequest(order_id="ORD-1", amount=100.0, currency="USD")
        assert model.order_id == "ORD-1"

    def test_missing_required_field(self):
        with pytest.raises(ValidationError) as exc_info:
            OrderRequest(amount=100.0)
        assert "order_id" in str(exc_info.value)

    @pytest.mark.parametrize("field,value,error_type", [
        ("amount", -1, "greater_than"),
        ("amount", 0, "greater_than"),
        ("amount", "abc", "float_parsing"),
        ("currency", "INVALID", "literal_error"),
        ("order_id", "", "string_too_short"),
    ])
    def test_field_constraint_violations(self, field, value, error_type):
        data = {"order_id": "ORD-1", "amount": 100.0, "currency": "USD"}
        data[field] = value
        with pytest.raises(ValidationError) as exc_info:
            OrderRequest(**data)
        errors = exc_info.value.errors()
        assert any(e["type"] == error_type for e in errors)
```

## Coverage Verification

After generating tests, verify branch coverage:

```bash
pytest tests/unit/ -v -m unit \
  --cov=src/ \
  --cov-report=term-missing \
  --cov-branch \
  --cov-fail-under=90
```

The `--cov-branch` flag measures **branch coverage** (not just line coverage),
ensuring every if/else path is exercised.
