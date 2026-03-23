---
name: aws-contract-testing
license: Apache-2.0
metadata:
  author: whitewhiteqq
  version: "0.1.0"
description: >
  Generate contract tests that validate API schemas, request/response shapes,
  required fields, security definitions, and step function input/output
  contracts. Works with OpenAPI/Swagger specs, SAM templates, and CloudFormation.
  Uses jsonschema and pydantic for validation. All tests run offline with zero
  network calls. Use when asked to write contract tests, schema tests, API
  contract validation, validate OpenAPI spec, or verify request/response shapes
  for any AWS Python project.
---

# AWS Contract Testing Skill

Generate offline contract tests by reading OpenAPI specs, SAM templates, and
CloudFormation definitions. No network calls needed.

## How to Generate Contract Tests

### Phase 1: Find the API Specification

Search the project for:
- `swagger.yml`, `swagger.yaml`, `openapi.yml`, `openapi.yaml`, `openapi.json`
- SAM `template.yaml` with `AWS::Serverless::Api` + inline swagger
- CloudFormation with `AWS::ApiGateway::RestApi` + `Body` property
- `api.json` or any file containing `"openapi"` or `"swagger"` keys

### Phase 2: Extract Schemas and Endpoints

From the spec, extract:
1. **All schemas** under `components.schemas` (or `definitions` in Swagger 2)
2. **All endpoints** — method + path + request body schema + response schema
3. **Required fields** for each schema
4. **Enum values** for constrained fields
5. **Security schemes** — API key, OAuth, IAM
6. **Global security** requirements

### Phase 3: Generate Contract Tests

See [references/openapi-patterns.md](references/openapi-patterns.md) for full patterns.

#### Schema Completeness Tests

```python
"""Verify all expected schemas exist in the spec."""
import yaml
import pytest
from pathlib import Path

SPEC_PATH = Path("path/to/swagger.yml")  # Discovered in Phase 1

@pytest.fixture(scope="module")
def spec():
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))

@pytest.fixture(scope="module")
def schemas(spec):
    return spec.get("components", spec.get("definitions", {})).get("schemas", {})

class TestSchemaCompleteness:
    # Auto-populated from spec analysis:
    EXPECTED_SCHEMAS = [
        # List every schema name found in the spec
    ]

    @pytest.mark.parametrize("schema_name", EXPECTED_SCHEMAS)
    def test_schema_exists(self, schemas, schema_name):
        assert schema_name in schemas, f"Missing schema: {schema_name}"
```

#### Request Validation Tests

For each endpoint with a request body:

```python
from jsonschema import validate, ValidationError

class TestCreateResourceContract:
    def test_valid_request_passes(self, schemas):
        schema = schemas["createResourceRequest"]
        payload = {
            # All required fields with valid values
        }
        validate(instance=payload, schema=schema)  # No error = pass

    def test_missing_required_field_fails(self, schemas):
        schema = schemas["createResourceRequest"]
        with pytest.raises(ValidationError):
            validate(instance={}, schema=schema)

    def test_extra_field_accepted_or_rejected(self, schemas):
        schema = schemas["createResourceRequest"]
        payload = {
            # Required fields + an extra unknown field
            "unknownField": "value",
        }
        if schema.get("additionalProperties") is False:
            with pytest.raises(ValidationError):
                validate(instance=payload, schema=payload)
        else:
            validate(instance=payload, schema=schema)  # Should pass
```

#### Security Contract Tests

```python
class TestSecurityContracts:
    def test_security_scheme_defined(self, spec):
        security_schemes = (
            spec.get("components", {}).get("securitySchemes", {})
            or spec.get("securityDefinitions", {})
        )
        assert len(security_schemes) > 0, "No security schemes defined"

    def test_all_endpoints_have_security(self, spec):
        global_security = spec.get("security", [])
        paths = spec.get("paths", {})
        for path, methods in paths.items():
            for method, details in methods.items():
                if method in ("get", "post", "put", "delete", "patch"):
                    endpoint_security = details.get("security", global_security)
                    assert endpoint_security, (
                        f"{method.upper()} {path} has no security"
                    )
```

### Phase 4: Step Function Contracts

If a step function definition is found, generate input/output contract tests:

```python
from pydantic import BaseModel
from typing import Optional

class StepFunctionInput(BaseModel):
    """Model derived from the first state's expected input."""
    # Populate fields from state machine definition
    pass

class StepFunctionOutput(BaseModel):
    """Model derived from the last state's output."""
    pass

def test_valid_input():
    data = {/* valid fields */}
    model = StepFunctionInput(**data)
    assert model  # Pydantic validates on construction

def test_missing_required_field():
    with pytest.raises(Exception):
        StepFunctionInput()  # Missing required fields
```

## Commands

```bash
pytest tests/contract/ -v -m contract --tb=short
```

## Key Principles

1. **Zero network calls** — contract tests validate structure, not behavior
2. **One test per schema** — verify existence + required fields + types
3. **One test per endpoint** — verify request/response schema references
4. **Security is not optional** — every endpoint must have a security definition
5. **Enum values** — test that constrained fields reject invalid values
