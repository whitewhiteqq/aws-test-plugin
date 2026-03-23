# Batch Job E2E Test Patterns

Patterns for testing AWS Batch jobs end-to-end.
Each test module targets **one component** with its own prefixed env vars.

## Pattern: Submit and Monitor

```python
"""E2E tests for {component_name} Batch job."""
import os
import time
import pytest
import boto3

# Component prefix — derived from service name during discovery.
# Example: for job "data-ingestion" → COMPONENT = "DATA_INGESTION"
COMPONENT = "{COMPONENT}"

BATCH_JOB_QUEUE = os.getenv(f"{COMPONENT}_BATCH_JOB_QUEUE")
BATCH_JOB_DEFINITION = os.getenv(f"{COMPONENT}_BATCH_JOB_DEFINITION")
REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not BATCH_JOB_QUEUE or not BATCH_JOB_DEFINITION,
        reason=f"{COMPONENT}_BATCH_JOB_QUEUE or {COMPONENT}_BATCH_JOB_DEFINITION not set",
    ),
]


@pytest.fixture(scope="module")
def batch_client():
    """Batch client using default AWS profile."""
    return boto3.client("batch", region_name=REGION)


class TestBatchJobExecution:
    MAX_WAIT_SECONDS = 600
    POLL_INTERVAL = 15

    def test_job_succeeds(self, batch_client):
        resp = batch_client.submit_job(
            jobName=f"e2e-test-{int(time.time())}",
            jobQueue=BATCH_JOB_QUEUE,
            jobDefinition=BATCH_JOB_DEFINITION,
        )
        job_id = resp["jobId"]

        deadline = time.monotonic() + self.MAX_WAIT_SECONDS
        while time.monotonic() < deadline:
            desc = batch_client.describe_jobs(jobs=[job_id])
            status = desc["jobs"][0]["status"]
            if status in ("SUCCEEDED", "FAILED"):
                break
            time.sleep(self.POLL_INTERVAL)
        else:
            pytest.fail(f"Job {job_id} did not complete in {self.MAX_WAIT_SECONDS}s")

        assert status == "SUCCEEDED", f"Job {job_id} status: {status}"

    def test_job_with_parameters(self, batch_client):
        resp = batch_client.submit_job(
            jobName=f"e2e-test-params-{int(time.time())}",
            jobQueue=BATCH_JOB_QUEUE,
            jobDefinition=BATCH_JOB_DEFINITION,
            parameters={
                "input_key": "E2E-TEST-input",
                "mode": "test",
            },
        )
        job_id = resp["jobId"]

        deadline = time.monotonic() + self.MAX_WAIT_SECONDS
        while time.monotonic() < deadline:
            desc = batch_client.describe_jobs(jobs=[job_id])
            status = desc["jobs"][0]["status"]
            if status in ("SUCCEEDED", "FAILED"):
                break
            time.sleep(self.POLL_INTERVAL)

        assert status == "SUCCEEDED"

    def test_job_with_environment_overrides(self, batch_client):
        resp = batch_client.submit_job(
            jobName=f"e2e-test-env-{int(time.time())}",
            jobQueue=BATCH_JOB_QUEUE,
            jobDefinition=BATCH_JOB_DEFINITION,
            containerOverrides={
                "environment": [
                    {"name": "MODE", "value": "test"},
                    {"name": "DRY_RUN", "value": "true"},
                ],
            },
        )
        job_id = resp["jobId"]

        deadline = time.monotonic() + self.MAX_WAIT_SECONDS
        while time.monotonic() < deadline:
            desc = batch_client.describe_jobs(jobs=[job_id])
            status = desc["jobs"][0]["status"]
            if status in ("SUCCEEDED", "FAILED"):
                break
            time.sleep(self.POLL_INTERVAL)

        assert status == "SUCCEEDED"
```

## Pattern: Verify Output

```python
class TestBatchJobOutput:
    """Verify batch job produces expected output in S3/DB."""

    MAX_WAIT_SECONDS = 600
    POLL_INTERVAL = 15

    def test_job_writes_output_to_s3(self, batch_client):
        s3 = boto3.client("s3", region_name=REGION)
        output_bucket = os.getenv("OUTPUT_BUCKET")
        output_prefix = f"e2e-test/{int(time.time())}/"

        resp = batch_client.submit_job(
            jobName=f"e2e-test-output-{int(time.time())}",
            jobQueue=BATCH_JOB_QUEUE,
            jobDefinition=BATCH_JOB_DEFINITION,
            containerOverrides={
                "environment": [
                    {"name": "OUTPUT_PREFIX", "value": output_prefix},
                ],
            },
        )
        job_id = resp["jobId"]

        # Wait for completion
        deadline = time.monotonic() + self.MAX_WAIT_SECONDS
        while time.monotonic() < deadline:
            desc = batch_client.describe_jobs(jobs=[job_id])
            if desc["jobs"][0]["status"] in ("SUCCEEDED", "FAILED"):
                break
            time.sleep(self.POLL_INTERVAL)

        assert desc["jobs"][0]["status"] == "SUCCEEDED"

        # Verify output exists
        if output_bucket:
            objects = s3.list_objects_v2(Bucket=output_bucket, Prefix=output_prefix)
            assert objects.get("KeyCount", 0) > 0, "No output files found"
```

## Pattern: Batch Array Jobs

```python
class TestBatchArrayJob:
    """Test array job fan-out execution."""

    MAX_WAIT_SECONDS = 900
    POLL_INTERVAL = 15

    def test_array_job_all_children_succeed(self, batch_client):
        array_size = 3
        resp = batch_client.submit_job(
            jobName=f"e2e-test-array-{int(time.time())}",
            jobQueue=BATCH_JOB_QUEUE,
            jobDefinition=BATCH_JOB_DEFINITION,
            arrayProperties={"size": array_size},
        )
        job_id = resp["jobId"]

        deadline = time.monotonic() + self.MAX_WAIT_SECONDS
        while time.monotonic() < deadline:
            desc = batch_client.describe_jobs(jobs=[job_id])
            status = desc["jobs"][0]["status"]
            if status in ("SUCCEEDED", "FAILED"):
                break
            time.sleep(self.POLL_INTERVAL)

        assert status == "SUCCEEDED"

        # Verify array properties
        array_props = desc["jobs"][0].get("arrayProperties", {})
        status_summary = array_props.get("statusSummary", {})
        assert status_summary.get("SUCCEEDED", 0) == array_size
```
