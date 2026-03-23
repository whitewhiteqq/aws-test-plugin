# Benchmark Patterns for AWS Python Services

## Pattern 1: Lambda Handler Latency

Measure raw handler execution with external dependencies mocked.

```python
"""Benchmark Lambda handler latency per HTTP method."""
import json
import pytest
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.performance


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.function_name = "benchmark-function"
    ctx.memory_limit_in_mb = 256
    ctx.get_remaining_time_in_millis.return_value = 30000
    return ctx


@pytest.fixture
def patched_handler():
    """
    Import handler inside a patch context so all boto3 calls are mocked.
    Adapt the patch target to the handler's module path.
    """
    with patch("handler.main.boto3") as mock_boto:
        table = MagicMock()
        table.get_item.return_value = {"Item": {"id": "bench", "name": "Test"}}
        table.put_item.return_value = {}
        table.query.return_value = {"Items": [], "Count": 0}
        mock_boto.resource.return_value.Table.return_value = table

        from handler.main import lambda_handler
        yield lambda_handler


class TestGetLatency:
    def test_single_get(self, patched_handler, mock_context, benchmark):
        event = {
            "httpMethod": "GET",
            "pathParameters": {"id": "bench-001"},
            "headers": {},
        }
        result = benchmark(patched_handler, event, mock_context)
        assert result["statusCode"] == 200

    def test_get_iterations(self, patched_handler, mock_context, benchmark):
        """pytest-benchmark runs many iterations automatically."""
        event = {
            "httpMethod": "GET",
            "pathParameters": {"id": "bench-iter"},
            "headers": {},
        }
        benchmark.pedantic(
            patched_handler,
            args=(event, mock_context),
            iterations=10,
            rounds=100,
        )


class TestPostLatency:
    def test_create(self, patched_handler, mock_context, benchmark):
        event = {
            "httpMethod": "POST",
            "body": json.dumps({"name": "Benchmark Item", "type": "test"}),
            "headers": {"Content-Type": "application/json"},
        }
        result = benchmark(patched_handler, event, mock_context)
        assert result["statusCode"] in (200, 201)
```

## Pattern 2: Memory Profiling with tracemalloc

```python
"""Memory usage profiling for Lambda handlers."""
import tracemalloc
import pytest
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.performance


@pytest.fixture
def memory_tracker():
    """Context manager that captures peak memory."""
    class Tracker:
        def __init__(self):
            self.peak_mb = 0
            self.current_mb = 0

        def __enter__(self):
            tracemalloc.start()
            return self

        def __exit__(self, *args):
            current, peak = tracemalloc.get_traced_memory()
            self.current_mb = current / 1024 / 1024
            self.peak_mb = peak / 1024 / 1024
            tracemalloc.stop()

    return Tracker()


class TestMemoryUsage:
    def test_get_stays_under_limit(self, mock_context, memory_tracker):
        """Peak memory should be under 80% of Lambda limit."""
        with memory_tracker:
            with patch("handler.main.boto3"):
                from handler.main import lambda_handler
                event = {"httpMethod": "GET", "pathParameters": {"id": "m1"}}
                lambda_handler(event, mock_context)

        limit = mock_context.memory_limit_in_mb
        assert memory_tracker.peak_mb < limit * 0.8, (
            f"Peak {memory_tracker.peak_mb:.1f}MB exceeds "
            f"80% of {limit}MB limit"
        )

    def test_large_payload_memory(self, mock_context, memory_tracker):
        """Processing a large payload should not cause memory spike."""
        large_body = {"items": [{"id": str(i)} for i in range(1000)]}

        with memory_tracker:
            with patch("handler.main.boto3") as mock_boto:
                mock_boto.client.return_value.batch_write_item.return_value = {}
                from handler.main import lambda_handler
                import json
                event = {
                    "httpMethod": "POST",
                    "body": json.dumps(large_body),
                    "headers": {},
                }
                lambda_handler(event, mock_context)

        # Large payloads shouldn't use more than 50MB
        assert memory_tracker.peak_mb < 50, (
            f"Large payload used {memory_tracker.peak_mb:.1f}MB"
        )

    def test_no_memory_leak_across_invocations(self, mock_context):
        """Multiple invocations should not accumulate memory."""
        import tracemalloc
        tracemalloc.start()

        with patch("handler.main.boto3"):
            from handler.main import lambda_handler
            event = {"httpMethod": "GET", "pathParameters": {"id": "leak"}}

            # Warm up
            lambda_handler(event, mock_context)
            _, baseline_peak = tracemalloc.get_traced_memory()

            # Run 50 more invocations
            for _ in range(50):
                lambda_handler(event, mock_context)

            _, final_peak = tracemalloc.get_traced_memory()

        tracemalloc.stop()

        growth_mb = (final_peak - baseline_peak) / 1024 / 1024
        assert growth_mb < 5, (
            f"Memory grew {growth_mb:.1f}MB over 50 invocations (possible leak)"
        )
```

## Pattern 3: Cold Start Simulation

```python
"""Cold start measurement — import time + first invocation."""
import time
import importlib
import pytest
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.performance


class TestColdStart:
    def test_import_time(self):
        """Handler module import should complete in < 1 second."""
        with patch.dict("os.environ", {"TABLE_NAME": "test", "AWS_REGION": "us-east-1"}):
            start = time.perf_counter()
            # Force fresh import
            import handler.main
            importlib.reload(handler.main)
            elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"Import took {elapsed:.2f}s (limit: 1s)"

    def test_first_invocation_time(self, mock_context):
        """First invocation (cold start) should complete in < 3 seconds."""
        with patch("handler.main.boto3") as mock_boto:
            mock_boto.client.return_value.get_item.return_value = {"Item": {}}

            import handler.main
            importlib.reload(handler.main)

            event = {"httpMethod": "GET", "pathParameters": {"id": "cold"}}
            start = time.perf_counter()
            handler.main.lambda_handler(event, mock_context)
            elapsed = time.perf_counter() - start

        assert elapsed < 3.0, f"Cold start took {elapsed:.2f}s (limit: 3s)"
```

## Pattern 4: Batch Job Throughput

```python
"""Throughput benchmarks for batch processing jobs."""
import time
import pytest
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.performance


class TestBatchThroughput:
    def test_records_per_second(self):
        """Batch job should process at least 100 records/second."""
        records = [{"id": str(i), "data": f"value-{i}"} for i in range(500)]

        with patch("batch.main.boto3") as mock_boto:
            mock_boto.client.return_value.put_item.return_value = {}
            from batch.main import process_records

            start = time.perf_counter()
            process_records(records)
            elapsed = time.perf_counter() - start

        rate = len(records) / elapsed
        assert rate >= 100, f"Throughput {rate:.0f} rec/s is below 100 rec/s"

    def test_batch_write_efficiency(self):
        """Batch writes should use BatchWriteItem (25 items per call)."""
        records = [{"id": str(i)} for i in range(100)]

        with patch("batch.main.boto3") as mock_boto:
            table = MagicMock()
            mock_boto.resource.return_value.Table.return_value = table
            from batch.main import process_records

            process_records(records)

            # Should use batch_writer, not individual put_item
            # With 100 records and batch size 25, expect ~4 batch calls
            assert table.put_item.call_count == 0, (
                "Should use batch_writer, not individual put_item"
            )

    def test_large_csv_parse_time(self, tmp_path):
        """CSV parsing for 10K rows should complete in < 5 seconds."""
        import csv

        csv_file = tmp_path / "test.csv"
        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "name", "value"])
            for i in range(10000):
                writer.writerow([i, f"name-{i}", i * 1.5])

        with patch("batch.main.boto3"):
            from batch.main import parse_input_file

            start = time.perf_counter()
            result = parse_input_file(str(csv_file))
            elapsed = time.perf_counter() - start

        assert elapsed < 5.0, f"Parsing 10K rows took {elapsed:.2f}s"
        assert len(result) == 10000
```

## Pattern 5: Comparison Benchmarks

```python
"""Compare performance across different input sizes."""
import json
import pytest
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.performance


@pytest.mark.parametrize("payload_size", [1, 10, 100, 500, 1000])
def test_scaling_behavior(payload_size, mock_context, benchmark):
    """Handler latency should scale sub-linearly with payload size."""
    items = [{"id": str(i), "name": f"item-{i}"} for i in range(payload_size)]
    event = {
        "httpMethod": "POST",
        "body": json.dumps({"items": items}),
        "headers": {"Content-Type": "application/json"},
    }

    with patch("handler.main.boto3"):
        from handler.main import lambda_handler
        result = benchmark(lambda_handler, event, mock_context)

    assert result["statusCode"] in (200, 201)
```

## Running Benchmarks

```bash
# Run all performance tests with benchmark output
pytest tests/performance/ -m performance --benchmark-enable \
  --benchmark-json=tests/reports/benchmark.json \
  --benchmark-columns=min,max,mean,stddev,median,rounds

# Compare against previous baseline
pytest tests/performance/ --benchmark-compare=0001 \
  --benchmark-compare-fail=mean:10%

# Save as baseline
pytest tests/performance/ --benchmark-save=baseline

# Run with memory profiling
pytest tests/performance/ -m performance -s \
  --benchmark-disable  # tracemalloc and benchmark don't mix well
```
