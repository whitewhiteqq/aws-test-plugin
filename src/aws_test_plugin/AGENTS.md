# AWS Test Plugin — Agent Instructions

This project uses `aws-test-plugin` to generate comprehensive tests
for AWS Python projects (Lambda, API Gateway, Step Functions, Batch).

## Available Test Types

| Type | Tool | Local | Deployed |
|------|------|-------|----------|
| Unit | pytest + mocks | Yes | No |
| Integration | moto + pytest | Yes | No |
| Contract | jsonschema + pytest | Yes | No |
| Performance | pytest-benchmark | Yes | No |
| E2E | requests + pytest | No | Yes |
| Load | Locust | No | Yes |

## Testing Workflow

1. **Discover** — scan for Lambda handlers (`main.py`, `handler.py`), Batch jobs
   (`Dockerfile`), Step Functions (`*.asl.json`), API specs (`swagger.yml`)
2. **Read code** — analyze handler source for branches, AWS calls, validation
3. **Generate tests** — create test files covering every code path, branch, and boundary
4. **Run** — `python scripts/run_tests.py all` (1-click for all offline tests)
5. **Fix** — read failures, adjust test logic, re-run

## Secrets Management

- **Never** hardcode API keys, tokens, or passwords in test files
- Two strategies available (see secrets-and-config.md for full details):
  - **Strategy A**: `.env` files (gitignored) — secrets loaded via `os.getenv()` with `pytest.skip()` fallback
  - **Strategy B**: AWS Secrets Manager + SSM Parameter Store — secrets retrieved via `boto3` with `pytest.skip()` fallback
- **AWS credentials**: use the default AWS profile (`~/.aws/credentials`) — boto3 picks it up automatically
- Unit/integration/contract tests work with fake `"testing"` credentials (moto) — no real AWS access needed
- E2E/load tests load real credentials from `.env` or Secrets Manager depending on chosen strategy

## Commands

```bash
# Scaffold test directories + .env.example
aws-test-plugin scaffold .

# 1-click: run ALL offline tests (unit + integration + contract + performance)
python scripts/run_tests.py all

# 1-click: run EVERYTHING (offline + E2E; tests self-skip if env vars missing)
python scripts/run_tests.py full

# Individual categories
pytest tests/unit/ -m unit -v --cov=src/ --cov-branch
pytest tests/integration/ -m integration -v
pytest tests/contract/ -m contract -v
pytest tests/performance/ -m performance --benchmark-enable
pytest tests/e2e/ -m e2e -v  # reads API_BASE_URL from .env

# Load tests (requires deployed API)
locust -f tests/load/locustfile.py --host=$LOAD_TEST_HOST \
  --users=50 --spawn-rate=5 --run-time=5m --headless
```

## Safety

- Never run E2E or load tests against production without confirmation
- All test data uses prefixes: `TEST-`, `E2E-TEST-`, `LOAD-TEST-`
- Integration tests use moto (no real AWS calls)
- Load tests must have `--run-time` set
- No secrets in test files — use `.env` (gitignored) or AWS Secrets Manager / SSM Parameter Store
