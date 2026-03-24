---
name: aws-perf-load-testing
description: >
  Generate performance benchmarks and load tests for AWS Python services.
  Performance tests measure Lambda latency, memory usage, cold start time,
  and batch throughput using pytest-benchmark and tracemalloc. Load tests
  use Locust to simulate concurrent users against API Gateway endpoints.
  Reads handler code to build realistic event payloads and endpoint lists.
  Use when asked to write performance tests, benchmark, profile memory,
  measure latency, load test, stress test, soak test, or capacity test
  for any AWS Python project.
---

# AWS Performance & Load Testing Skill

Generate benchmarks and load tests by reading handler code and API specs.

## Performance Tests (pytest-benchmark + tracemalloc)

### Phase 1: Build Realistic Events

Read the handler code to understand:
- What event shape does it expect? (API GW proxy, S3, SQS, direct)
- What are the hot paths? (most common code branches)
- What external calls does it make? (need to mock for benchmarks)

### Phase 2: Generate Benchmark Tests

See [references/benchmark-patterns.md](references/benchmark-patterns.md) for full patterns.

```python
"""Performance benchmarks for {handler_name}."""
import json
import pytest
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.performance


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.function_name = "test-function"
    ctx.memory_limit_in_mb = 256
    ctx.get_remaining_time_in_millis.return_value = 30000
    return ctx


class TestHandlerLatency:
    """Benchmark handler execution time."""

    def test_get_request_latency(self, mock_context, benchmark):
        # Mock external dependencies so we measure handler logic only
        with patch("handler.main.boto3") as mock_boto:
            mock_boto.client.return_value.get_object.return_value = {
                "Body": MagicMock(read=lambda: b'{"data": "value"}')
            }

            from handler.main import lambda_handler
            event = {
                "httpMethod": "GET",
                "pathParameters": {"id": "bench-123"},
                "headers": {"x-api-key": "test"},
            }

            result = benchmark(lambda_handler, event, mock_context)
            assert result["statusCode"] == 200

    def test_post_request_latency(self, mock_context, benchmark):
        with patch("handler.main.boto3") as mock_boto:
            mock_boto.client.return_value.put_item.return_value = {}

            from handler.main import lambda_handler
            event = {
                "httpMethod": "POST",
                "body": json.dumps({"name": "Benchmark"}),
                "headers": {"x-api-key": "test"},
            }

            result = benchmark(lambda_handler, event, mock_context)
            assert result["statusCode"] in (200, 201)


class TestMemoryUsage:
    """Profile handler memory consumption."""

    def test_memory_within_limit(self, mock_context):
        import tracemalloc
        tracemalloc.start()

        with patch("handler.main.boto3"):
            from handler.main import lambda_handler
            event = {"httpMethod": "GET", "pathParameters": {"id": "mem-test"}}
            lambda_handler(event, mock_context)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / 1024 / 1024
        limit_mb = mock_context.memory_limit_in_mb
        assert peak_mb < limit_mb * 0.8, (
            f"Peak {peak_mb:.1f}MB is >80% of {limit_mb}MB limit"
        )
```

### Performance Thresholds

Suggested starting points — adapt to your service's SLAs and requirements:

| Metric | Lambda | Batch | API GW E2E |
|--------|--------|-------|------------|
| p95 latency | < 500ms | N/A | < 3s |
| p99 latency | < 1s | N/A | < 5s |
| Error rate | < 0.1% | 0% | < 1% |
| Memory peak | < 80% of limit | < 2GB | N/A |
| Cold start | < 3s | N/A | N/A |

## Load Tests (Locust)

### Phase 1: Build Endpoint Map

Read the API spec (OpenAPI/Swagger) or discover endpoints from handler routes:

| Method | Path | Weight | Category |
|--------|------|--------|----------|
| GET | /resource/{id} | 5 | read |
| POST | /resource | 1 | write |
| POST | /resource/search | 3 | read |

### Phase 2: Generate Locust Users

See [references/locust-patterns.md](references/locust-patterns.md) for full patterns.

```python
"""Load test for {service_name} API."""
from locust import HttpUser, task, between, tag

class ApiUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.client.headers.update({
            "Content-Type": "application/json",
            # Add auth headers from spec
        })

    @tag("read")
    @task(5)  # weight = 5 (most common)
    def get_resource(self):
        self.client.get(
            "/resource/LOAD-TEST-id",
            name="/resource/{id}",
        )

    @tag("write")
    @task(1)  # weight = 1 (least common)
    def create_resource(self):
        self.client.post(
            "/resource",
            json={"name": "LOAD-TEST-item"},
            name="/resource",
        )
```

### Load Test Commands

```bash
# Quick smoke (10 users, 1 minute)
locust -f tests/load/locustfile.py --host=$API_BASE_URL \
  --users=10 --spawn-rate=2 --run-time=1m --headless --csv=tests/reports/smoke

# Standard load (50 users, 5 minutes)
locust -f tests/load/locustfile.py --host=$API_BASE_URL \
  --users=50 --spawn-rate=5 --run-time=5m --headless \
  --csv=tests/reports/load --html=tests/reports/load.html

# Stress (ramp to 200 users, 10 minutes)
locust -f tests/load/locustfile.py --host=$API_BASE_URL \
  --users=200 --spawn-rate=10 --run-time=10m --headless --csv=tests/reports/stress

# Soak (steady 30 users, 1 hour)
locust -f tests/load/locustfile.py --host=$API_BASE_URL \
  --users=30 --spawn-rate=30 --run-time=1h --headless --csv=tests/reports/soak
```

### Load Test Output

Locust generates:
- `*_stats.csv` — per-endpoint avg/min/max/p50/p95/p99
- `*_failures.csv` — failed request details
- `*_stats_history.csv` — time-series data for graphing
- `*.html` — interactive dashboard

## Safety Constraints

- **Never** run load tests against production without explicit confirmation
- All test data uses `LOAD-TEST-` prefix
- Load tests must have `--run-time` set (no unbounded runs)
- Monitor CloudWatch during load tests for throttling
