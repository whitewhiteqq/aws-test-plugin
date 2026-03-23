# Locust Load Test Patterns for AWS APIs

## Pattern 1: Basic API User

```python
"""Load test for a REST API behind API Gateway."""
import json
import uuid
from locust import HttpUser, task, between, tag, events


class ApiUser(HttpUser):
    """Simulates a typical API consumer."""

    wait_time = between(1, 3)

    def on_start(self):
        """Set up headers; authenticate if needed."""
        self.client.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            # "Authorization": "Bearer <token>"  # Add auth if required
        })
        # Create a test resource to work with
        self.resource_id = None
        resp = self.client.post(
            "/resource",
            json={"name": f"LOAD-TEST-{uuid.uuid4().hex[:8]}"},
            name="/resource [setup]",
        )
        if resp.status_code in (200, 201):
            self.resource_id = resp.json().get("id")

    def on_stop(self):
        """Clean up test data."""
        if self.resource_id:
            self.client.delete(
                f"/resource/{self.resource_id}",
                name="/resource/{id} [cleanup]",
            )

    @tag("read")
    @task(5)
    def get_resource(self):
        if self.resource_id:
            self.client.get(
                f"/resource/{self.resource_id}",
                name="/resource/{id}",
            )

    @tag("read")
    @task(3)
    def list_resources(self):
        self.client.get("/resource?limit=10", name="/resource [list]")

    @tag("write")
    @task(1)
    def update_resource(self):
        if self.resource_id:
            self.client.put(
                f"/resource/{self.resource_id}",
                json={"name": f"LOAD-TEST-updated-{uuid.uuid4().hex[:8]}"},
                name="/resource/{id} [update]",
            )
```

## Pattern 2: Weighted Multi-Endpoint User

```python
"""Load test with endpoint weights derived from production traffic patterns."""
from locust import HttpUser, task, between, tag
import json
import random
import string


def random_string(length=8):
    return "LOAD-TEST-" + "".join(random.choices(string.ascii_lowercase, k=length))


class TrafficPatternUser(HttpUser):
    """Endpoint weights mirror observed production traffic ratios."""

    wait_time = between(0.5, 2)

    @tag("read", "high-traffic")
    @task(40)  # 40% of traffic
    def get_by_id(self):
        self.client.get(
            f"/items/{random.randint(1, 1000)}",
            name="/items/{id}",
        )

    @tag("read", "high-traffic")
    @task(25)  # 25% of traffic
    def search(self):
        self.client.get(
            f"/items/search?q={random_string(4)}&limit=20",
            name="/items/search",
        )

    @tag("read")
    @task(15)  # 15% of traffic
    def list_paginated(self):
        self.client.get("/items?page=1&size=50", name="/items [page]")

    @tag("write")
    @task(10)  # 10% of traffic
    def create_item(self):
        self.client.post(
            "/items",
            json={"name": random_string(), "category": "test"},
            name="/items [create]",
        )

    @tag("write")
    @task(5)  # 5% of traffic
    def update_item(self):
        self.client.put(
            f"/items/{random.randint(1, 1000)}",
            json={"name": random_string()},
            name="/items/{id} [update]",
        )

    @tag("write")
    @task(5)  # 5% of traffic
    def delete_item(self):
        self.client.delete(
            f"/items/{random.randint(1, 1000)}",
            name="/items/{id} [delete]",
        )
```

## Pattern 3: Step Function Load Test

```python
"""Load test for Step Function executions via API Gateway."""
import json
import time
import uuid
from locust import HttpUser, task, between, events


class StepFunctionUser(HttpUser):
    """Triggers Step Function executions and polls for completion."""

    wait_time = between(5, 15)  # Longer wait — SFN executions take time

    @task
    def execute_workflow(self):
        execution_name = f"LOAD-TEST-{uuid.uuid4().hex[:8]}"

        # Start execution
        start_resp = self.client.post(
            "/workflow/execute",
            json={
                "input": {"action": "load-test", "id": execution_name},
            },
            name="/workflow/execute [start]",
        )

        if start_resp.status_code != 200:
            return

        execution_id = start_resp.json().get("executionId")
        if not execution_id:
            return

        # Poll for completion (max 60 seconds)
        for _ in range(12):
            time.sleep(5)
            status_resp = self.client.get(
                f"/workflow/status/{execution_id}",
                name="/workflow/status/{id}",
            )
            if status_resp.status_code == 200:
                status = status_resp.json().get("status")
                if status in ("SUCCEEDED", "FAILED", "TIMED_OUT", "ABORTED"):
                    break
```

## Pattern 4: File Upload Load Test

```python
"""Load test for file upload endpoints."""
import io
import uuid
from locust import HttpUser, task, between


class FileUploadUser(HttpUser):
    """Tests file upload throughput."""

    wait_time = between(2, 5)

    def _generate_csv(self, rows=100):
        """Generate a CSV file in-memory."""
        lines = ["id,name,value"]
        for i in range(rows):
            lines.append(f"LOAD-TEST-{i},item-{i},{i * 1.5}")
        return io.BytesIO("\n".join(lines).encode())

    @task(3)
    def upload_small_file(self):
        """Upload a small CSV (100 rows, ~3KB)."""
        self.client.post(
            "/upload",
            files={"file": (f"LOAD-TEST-{uuid.uuid4().hex[:8]}.csv",
                           self._generate_csv(100), "text/csv")},
            name="/upload [small]",
        )

    @task(1)
    def upload_large_file(self):
        """Upload a larger CSV (5000 rows, ~150KB)."""
        self.client.post(
            "/upload",
            files={"file": (f"LOAD-TEST-{uuid.uuid4().hex[:8]}.csv",
                           self._generate_csv(5000), "text/csv")},
            name="/upload [large]",
        )
```

## Pattern 5: Custom Load Shape (Ramp-Up/Plateau/Ramp-Down)

```python
"""Custom load shape for controlled ramp testing."""
import math
from locust import LoadTestShape


class StagesShape(LoadTestShape):
    """
    Ramp up → hold → ramp down → hold → spike → cool down.

    Customize stages for your SLA requirements.
    """

    stages = [
        {"duration": 60,  "users": 10,  "spawn_rate": 2},   # Warm up
        {"duration": 180, "users": 50,  "spawn_rate": 5},   # Normal load
        {"duration": 300, "users": 50,  "spawn_rate": 50},  # Hold steady
        {"duration": 360, "users": 100, "spawn_rate": 10},  # Ramp to peak
        {"duration": 420, "users": 100, "spawn_rate": 100}, # Hold peak
        {"duration": 480, "users": 10,  "spawn_rate": 10},  # Cool down
    ]

    def tick(self):
        run_time = self.get_run_time()
        for stage in self.stages:
            if run_time < stage["duration"]:
                return (stage["users"], stage["spawn_rate"])
        return None  # Stop test


class SpikeShape(LoadTestShape):
    """
    Sudden spike to test auto-scaling and error handling.
    """

    def tick(self):
        run_time = self.get_run_time()
        if run_time < 30:       # 30s warm up with 5 users
            return (5, 5)
        elif run_time < 60:     # Sudden spike to 200
            return (200, 200)
        elif run_time < 180:    # Hold spike for 2 minutes
            return (200, 200)
        elif run_time < 240:    # Drop back to 5
            return (5, 200)
        elif run_time < 360:    # Hold low for 2 minutes (recovery check)
            return (5, 5)
        return None
```

## Pattern 6: Threshold Validation Script

```python
"""Validate load test results against SLA thresholds."""
import csv
import sys
from pathlib import Path


def validate_results(stats_file: str, thresholds: dict) -> list[str]:
    """
    Read Locust CSV stats and check against thresholds.

    thresholds = {
        "p95_ms": 3000,      # p95 response time < 3s
        "p99_ms": 5000,      # p99 response time < 5s
        "error_pct": 1.0,    # Error rate < 1%
        "min_rps": 10,       # At least 10 requests/sec
    }
    """
    violations = []

    with open(stats_file) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["Name"] == "Aggregated":
                p95 = float(row.get("95%", 0))
                p99 = float(row.get("99%", 0))
                total = int(row.get("Request Count", 0))
                failures = int(row.get("Failure Count", 0))
                error_pct = (failures / total * 100) if total > 0 else 0
                avg_rps = float(row.get("Requests/s", 0))

                if p95 > thresholds.get("p95_ms", float("inf")):
                    violations.append(
                        f"p95 latency {p95:.0f}ms exceeds "
                        f"{thresholds['p95_ms']}ms threshold"
                    )
                if p99 > thresholds.get("p99_ms", float("inf")):
                    violations.append(
                        f"p99 latency {p99:.0f}ms exceeds "
                        f"{thresholds['p99_ms']}ms threshold"
                    )
                if error_pct > thresholds.get("error_pct", 100):
                    violations.append(
                        f"Error rate {error_pct:.1f}% exceeds "
                        f"{thresholds['error_pct']}% threshold"
                    )
                if avg_rps < thresholds.get("min_rps", 0):
                    violations.append(
                        f"Throughput {avg_rps:.1f} RPS below "
                        f"{thresholds['min_rps']} RPS minimum"
                    )

    return violations


if __name__ == "__main__":
    stats = sys.argv[1] if len(sys.argv) > 1 else "tests/reports/load_stats.csv"
    thresholds = {
        "p95_ms": 3000,
        "p99_ms": 5000,
        "error_pct": 1.0,
        "min_rps": 10,
    }
    violations = validate_results(stats, thresholds)
    if violations:
        print("SLA VIOLATIONS:")
        for v in violations:
            print(f"  ✗ {v}")
        sys.exit(1)
    else:
        print("All SLA thresholds met ✓")
```

## Running Load Tests

```bash
# Quick smoke test (sanity check)
locust -f tests/load/locustfile.py --host=$API_BASE_URL \
  --users=10 --spawn-rate=2 --run-time=1m --headless \
  --csv=tests/reports/smoke

# Standard load test
locust -f tests/load/locustfile.py --host=$API_BASE_URL \
  --users=50 --spawn-rate=5 --run-time=5m --headless \
  --csv=tests/reports/load --html=tests/reports/load.html

# With custom shape (ignores --users/--spawn-rate)
locust -f tests/load/locustfile_shaped.py --host=$API_BASE_URL \
  --headless --csv=tests/reports/shaped

# Validate results against SLA
python tests/load/validate_thresholds.py tests/reports/load_stats.csv
```
