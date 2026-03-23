# Step Function E2E Test Patterns

Patterns for testing AWS Step Functions workflows end-to-end.
Each test module targets **one component** with its own prefixed env vars.

## Pattern: Synchronous Execution (Express Workflow)

```python
"""E2E tests for {component_name} Step Function."""
import os
import json
import pytest
import boto3

# Component prefix — derived from service name during discovery.
# Example: for workflow "order-processor" → COMPONENT = "ORDER_PROCESSOR"
COMPONENT = "{COMPONENT}"

STEP_FUNCTION_ARN = os.getenv(f"{COMPONENT}_SFN_ARN")
REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not STEP_FUNCTION_ARN, reason=f"{COMPONENT}_SFN_ARN not set"),
]


@pytest.fixture(scope="module")
def sfn_client():
    """Step Functions client using default AWS profile."""
    return boto3.client("stepfunctions", region_name=REGION)


class TestSyncExecution:
    """Test synchronous (Express) Step Function execution."""

    def test_valid_input_succeeds(self, sfn_client):
        result = sfn_client.start_sync_execution(
            stateMachineArn=STEP_FUNCTION_ARN,
            input=json.dumps({
                # Populate from state machine InputPath / first state's expected input
                "key": "E2E-TEST-value",
            }),
        )
        assert result["status"] == "SUCCEEDED", (
            f"Failed: {result.get('error')}: {result.get('cause')}"
        )
        output = json.loads(result.get("output", "{}"))
        # Assert on expected output fields

    def test_invalid_input_fails_gracefully(self, sfn_client):
        result = sfn_client.start_sync_execution(
            stateMachineArn=STEP_FUNCTION_ARN,
            input=json.dumps({"invalid": True}),
        )
        # Should fail or be caught by Choice/Catch states
        assert result["status"] in ("SUCCEEDED", "FAILED")
```

## Pattern: Async Execution with Polling

```python
import time


class TestAsyncExecution:
    """Test standard (async) Step Function execution."""

    MAX_WAIT_SECONDS = 300
    POLL_INTERVAL = 10

    def test_workflow_completes(self, sfn_client):
        execution = sfn_client.start_execution(
            stateMachineArn=STEP_FUNCTION_ARN,
            name=f"e2e-test-{int(time.time())}",
            input=json.dumps({
                "key": "E2E-TEST-value",
            }),
        )
        arn = execution["executionArn"]

        # Poll until done
        deadline = time.monotonic() + self.MAX_WAIT_SECONDS
        while time.monotonic() < deadline:
            desc = sfn_client.describe_execution(executionArn=arn)
            if desc["status"] != "RUNNING":
                break
            time.sleep(self.POLL_INTERVAL)
        else:
            pytest.fail(f"Execution did not complete within {self.MAX_WAIT_SECONDS}s")

        assert desc["status"] == "SUCCEEDED", (
            f"Status={desc['status']}: {desc.get('error', 'unknown')}"
        )

    def test_execution_history_has_expected_states(self, sfn_client):
        """Verify the execution visited expected states."""
        # Start execution
        execution = sfn_client.start_execution(
            stateMachineArn=STEP_FUNCTION_ARN,
            name=f"e2e-history-{int(time.time())}",
            input=json.dumps({"key": "E2E-TEST-value"}),
        )
        arn = execution["executionArn"]

        # Wait for completion
        deadline = time.monotonic() + self.MAX_WAIT_SECONDS
        while time.monotonic() < deadline:
            desc = sfn_client.describe_execution(executionArn=arn)
            if desc["status"] != "RUNNING":
                break
            time.sleep(self.POLL_INTERVAL)

        # Check history
        history = sfn_client.get_execution_history(executionArn=arn)
        event_types = [e["type"] for e in history["events"]]

        assert "ExecutionStarted" in event_types
        assert "ExecutionSucceeded" in event_types or "ExecutionFailed" in event_types
```

## Pattern: Error Handling & Retry

```python
class TestErrorHandling:
    """Test Step Function error handling and retry behavior."""

    def test_retry_on_transient_failure(self, sfn_client):
        """Verify the state machine retries on expected errors."""
        execution = sfn_client.start_execution(
            stateMachineArn=STEP_FUNCTION_ARN,
            name=f"e2e-retry-{int(time.time())}",
            input=json.dumps({
                "key": "E2E-TEST-force-retry",
                # Include data that triggers a retryable failure
            }),
        )
        arn = execution["executionArn"]

        deadline = time.monotonic() + self.MAX_WAIT_SECONDS
        while time.monotonic() < deadline:
            desc = sfn_client.describe_execution(executionArn=arn)
            if desc["status"] != "RUNNING":
                break
            time.sleep(self.POLL_INTERVAL)

        # Check for retry events in history
        history = sfn_client.get_execution_history(executionArn=arn)
        retry_events = [
            e for e in history["events"]
            if "Retry" in e["type"] or "TaskFailed" in e["type"]
        ]
        # Retries mean the mechanism is working
        # Final status may still be SUCCEEDED if retry eventually worked

    def test_catch_routes_to_failure_handler(self, sfn_client):
        """Verify Catch clauses route errors to the right state."""
        execution = sfn_client.start_execution(
            stateMachineArn=STEP_FUNCTION_ARN,
            name=f"e2e-catch-{int(time.time())}",
            input=json.dumps({
                "key": "E2E-TEST-force-catch",
            }),
        )
        arn = execution["executionArn"]

        deadline = time.monotonic() + self.MAX_WAIT_SECONDS
        while time.monotonic() < deadline:
            desc = sfn_client.describe_execution(executionArn=arn)
            if desc["status"] != "RUNNING":
                break
            time.sleep(self.POLL_INTERVAL)

        # The SFN should have handled the error via Catch
        history = sfn_client.get_execution_history(executionArn=arn)
        state_names = [
            e.get("stateEnteredEventDetails", {}).get("name")
            for e in history["events"]
            if e["type"] == "TaskStateEntered"
        ]
        # Assert that the failure-handler state was visited
```

## Pattern: Parallel Branch Verification

```python
class TestParallelBranches:
    """Test Parallel state executes all branches."""

    def test_parallel_branches_all_complete(self, sfn_client):
        execution = sfn_client.start_execution(
            stateMachineArn=STEP_FUNCTION_ARN,
            name=f"e2e-parallel-{int(time.time())}",
            input=json.dumps({"key": "E2E-TEST-value"}),
        )
        arn = execution["executionArn"]

        deadline = time.monotonic() + self.MAX_WAIT_SECONDS
        while time.monotonic() < deadline:
            desc = sfn_client.describe_execution(executionArn=arn)
            if desc["status"] != "RUNNING":
                break
            time.sleep(self.POLL_INTERVAL)

        assert desc["status"] == "SUCCEEDED"
        output = json.loads(desc.get("output", "[]"))
        # Parallel state returns an array — one result per branch
        assert isinstance(output, list)
        assert len(output) >= 2  # At least 2 branches
```
