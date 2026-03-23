# OpenAPI Contract Test Patterns

Ready-to-use patterns for validating OpenAPI/Swagger specifications offline.

## Pattern: Full Spec Validation Suite

```python
"""Contract tests for OpenAPI specification."""
import yaml
import pytest
from pathlib import Path
from jsonschema import validate, ValidationError

# Adjust path to your project's spec file
SPEC_PATH = Path(__file__).resolve().parents[2] / "swagger.yml"


@pytest.fixture(scope="module")
def spec():
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schemas(spec):
    components = spec.get("components", spec.get("definitions", {}))
    if isinstance(components, dict) and "schemas" in components:
        return components["schemas"]
    return components


@pytest.fixture(scope="module")
def paths(spec):
    return spec.get("paths", {})


# --- Schema existence ---

class TestSchemaCompleteness:
    """Verify all schemas referenced in endpoints actually exist."""

    def test_all_referenced_schemas_exist(self, spec, schemas):
        """Walk all $ref in the spec and verify targets exist."""
        refs = set()
        _collect_refs(spec, refs)
        for ref in refs:
            if ref.startswith("#/components/schemas/") or ref.startswith("#/definitions/"):
                name = ref.split("/")[-1]
                assert name in schemas, f"Referenced schema missing: {ref}"


def _collect_refs(obj, refs):
    """Recursively find all $ref values in the spec."""
    if isinstance(obj, dict):
        if "$ref" in obj:
            refs.add(obj["$ref"])
        for v in obj.values():
            _collect_refs(v, refs)
    elif isinstance(obj, list):
        for item in obj:
            _collect_refs(item, refs)


# --- Required fields ---

class TestRequiredFields:
    """Verify required fields are enforced."""

    def _get_schemas_with_required(self, schemas):
        return [
            (name, schema)
            for name, schema in schemas.items()
            if schema.get("required")
        ]

    def test_empty_payload_rejected(self, schemas):
        """An empty dict should fail validation for schemas with required fields."""
        for name, schema in self._get_schemas_with_required(schemas):
            with pytest.raises(ValidationError):
                validate(instance={}, schema=schema)

    def test_minimal_valid_payload(self, schemas):
        """A payload with only required fields should pass."""
        for name, schema in self._get_schemas_with_required(schemas):
            minimal = {}
            for field in schema["required"]:
                field_def = schema.get("properties", {}).get(field, {})
                minimal[field] = _make_sample_value(field_def)
            validate(instance=minimal, schema=schema)


def _make_sample_value(field_def):
    """Generate a minimal valid value for a schema field."""
    t = field_def.get("type", "string")
    if "enum" in field_def:
        return field_def["enum"][0]
    if t == "string":
        fmt = field_def.get("format", "")
        if fmt == "date":
            return "2025-01-01"
        if fmt == "date-time":
            return "2025-01-01T00:00:00Z"
        if fmt == "email":
            return "test@example.com"
        return "test-value"
    if t == "integer":
        return field_def.get("minimum", 0)
    if t == "number":
        return field_def.get("minimum", 0.0)
    if t == "boolean":
        return True
    if t == "array":
        return []
    if t == "object":
        return {}
    return "test"


# --- Enum validation ---

class TestEnumConstraints:
    """Verify enum fields reject invalid values."""

    def test_invalid_enum_value_rejected(self, schemas):
        for name, schema in schemas.items():
            for field, field_def in schema.get("properties", {}).items():
                if "enum" in field_def:
                    # Build a payload with an invalid enum value
                    payload = {field: "DEFINITELY-NOT-A-VALID-ENUM-VALUE"}
                    # Add required fields
                    for req in schema.get("required", []):
                        if req != field:
                            payload[req] = _make_sample_value(
                                schema.get("properties", {}).get(req, {})
                            )
                    with pytest.raises(ValidationError):
                        validate(instance=payload, schema=schema)


# --- Endpoint coverage ---

class TestEndpointCompleteness:
    """Verify endpoint paths and methods exist."""

    def test_spec_has_paths(self, paths):
        assert len(paths) > 0, "No paths defined in spec"

    def test_every_endpoint_has_response(self, paths):
        for path, methods in paths.items():
            for method, details in methods.items():
                if method not in ("get", "post", "put", "delete", "patch", "options", "head"):
                    continue
                responses = details.get("responses", {})
                assert responses, f"{method.upper()} {path} has no responses defined"

    def test_post_put_endpoints_have_request_body(self, paths):
        for path, methods in paths.items():
            for method in ("post", "put"):
                if method not in methods:
                    continue
                details = methods[method]
                has_body = (
                    details.get("requestBody")
                    or any(
                        p.get("in") == "body"
                        for p in details.get("parameters", [])
                    )
                )
                assert has_body, f"{method.upper()} {path} has no request body"


# --- Security ---

class TestSecurityDefinitions:
    """Verify security is properly defined."""

    def test_security_schemes_exist(self, spec):
        schemes = (
            spec.get("components", {}).get("securitySchemes", {})
            or spec.get("securityDefinitions", {})
        )
        assert schemes, "No security schemes defined"

    def test_all_write_endpoints_have_security(self, spec, paths):
        global_security = spec.get("security", [])
        for path, methods in paths.items():
            for method in ("post", "put", "delete", "patch"):
                if method not in methods:
                    continue
                details = methods[method]
                security = details.get("security", global_security)
                assert security, (
                    f"{method.upper()} {path} has no security"
                )
```

## Pattern: additionalProperties Enforcement

```python
class TestAdditionalProperties:
    """Verify schemas that disallow extra fields."""

    def test_extra_fields_rejected(self, schemas):
        for name, schema in schemas.items():
            if schema.get("additionalProperties") is False:
                required = schema.get("required", [])
                payload = {}
                for field in required:
                    field_def = schema.get("properties", {}).get(field, {})
                    payload[field] = _make_sample_value(field_def)
                payload["__unexpected_extra_field__"] = "should fail"
                with pytest.raises(ValidationError):
                    validate(instance=payload, schema=schema)
```

## Pattern: Response Schema Validation

```python
class TestResponseSchemas:
    """Verify response schemas have expected structure."""

    def test_success_responses_have_schema(self, paths, schemas):
        for path, methods in paths.items():
            for method, details in methods.items():
                if method not in ("get", "post", "put", "delete", "patch"):
                    continue
                for status, resp in details.get("responses", {}).items():
                    if status.startswith("2"):
                        # 2xx responses should reference a schema
                        content = resp.get("content", {})
                        if content:
                            json_content = content.get("application/json", {})
                            assert json_content.get("schema"), (
                                f"{method.upper()} {path} {status} has no schema"
                            )

    def test_error_responses_have_message(self, paths, schemas):
        for path, methods in paths.items():
            for method, details in methods.items():
                if method not in ("get", "post", "put", "delete", "patch"):
                    continue
                for status, resp in details.get("responses", {}).items():
                    if status.startswith(("4", "5")):
                        # Error responses should have a schema with message
                        content = resp.get("content", {})
                        if content:
                            json_content = content.get("application/json", {})
                            schema_ref = json_content.get("schema", {})
                            # Resolve $ref if needed
```
