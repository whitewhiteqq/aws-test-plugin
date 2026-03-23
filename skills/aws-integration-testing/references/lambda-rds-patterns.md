# Lambda + RDS/PostgreSQL Integration Patterns

Testcontainers-based patterns for testing services that interact with PostgreSQL/RDS.

## Prerequisites

```bash
pip install testcontainers[postgres] psycopg2-binary
# Docker must be running
```

## Pattern: Basic CRUD with Real PostgreSQL

```python
"""Integration tests with real PostgreSQL via testcontainers."""
import json
import pytest
from unittest.mock import MagicMock

try:
    from testcontainers.postgres import PostgresContainer
    HAS_TESTCONTAINERS = True
except ImportError:
    HAS_TESTCONTAINERS = False

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not HAS_TESTCONTAINERS, reason="testcontainers not installed"),
]


@pytest.fixture(scope="module")
def postgres():
    """Start a real PostgreSQL container for the test module."""
    with PostgresContainer("postgres:15") as pg:
        yield pg


@pytest.fixture
def db_connection(postgres):
    """Create a connection and set up schema."""
    import psycopg2
    conn = psycopg2.connect(postgres.get_connection_url())
    conn.autocommit = True
    cur = conn.cursor()

    # Create tables matching your service's schema
    cur.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id VARCHAR(255) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            status VARCHAR(50) DEFAULT 'active',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    yield conn
    conn.close()


class TestDatabaseCRUD:
    def test_insert_record(self, db_connection):
        cur = db_connection.cursor()
        cur.execute(
            "INSERT INTO records (id, name) VALUES (%s, %s) RETURNING id",
            ("test-1", "Test Record"),
        )
        result = cur.fetchone()
        assert result[0] == "test-1"

    def test_query_by_status(self, db_connection):
        cur = db_connection.cursor()
        cur.execute("INSERT INTO records (id, name, status) VALUES (%s, %s, %s)",
                    ("test-q1", "Active", "active"))
        cur.execute("INSERT INTO records (id, name, status) VALUES (%s, %s, %s)",
                    ("test-q2", "Inactive", "inactive"))

        cur.execute("SELECT * FROM records WHERE status = %s", ("active",))
        rows = cur.fetchall()
        assert len(rows) >= 1
        assert all(r[2] == "active" for r in rows)

    def test_update_record(self, db_connection):
        cur = db_connection.cursor()
        cur.execute("INSERT INTO records (id, name) VALUES (%s, %s)", ("test-u1", "Original"))
        cur.execute("UPDATE records SET name = %s WHERE id = %s", ("Updated", "test-u1"))
        cur.execute("SELECT name FROM records WHERE id = %s", ("test-u1",))
        assert cur.fetchone()[0] == "Updated"

    def test_delete_record(self, db_connection):
        cur = db_connection.cursor()
        cur.execute("INSERT INTO records (id, name) VALUES (%s, %s)", ("test-d1", "ToDelete"))
        cur.execute("DELETE FROM records WHERE id = %s", ("test-d1",))
        cur.execute("SELECT COUNT(*) FROM records WHERE id = %s", ("test-d1",))
        assert cur.fetchone()[0] == 0
```

## Pattern: Test Handler with Real DB

```python
class TestHandlerWithRealDB:
    """Wire the Lambda handler to a real PostgreSQL instance."""

    @pytest.fixture
    def handler_env(self, postgres, monkeypatch):
        """Configure handler to use testcontainers PostgreSQL."""
        # Parse the connection URL from testcontainers
        url = postgres.get_connection_url()
        # Typical env vars a Lambda reads for DB connection:
        monkeypatch.setenv("DB_HOST", postgres.get_container_host_ip())
        monkeypatch.setenv("DB_PORT", str(postgres.get_exposed_port(5432)))
        monkeypatch.setenv("DB_NAME", "test")
        monkeypatch.setenv("DB_USER", "test")
        monkeypatch.setenv("DB_PASSWORD", "test")
        # Or a full connection string:
        monkeypatch.setenv("DATABASE_URL", url)

    def test_handler_creates_record(self, handler_env, db_connection):
        mock_ctx = MagicMock()
        mock_ctx.function_name = "test"
        mock_ctx.get_remaining_time_in_millis.return_value = 30000

        # Import handler after env vars are set
        from handler.main import lambda_handler

        event = {
            "httpMethod": "POST",
            "body": json.dumps({"name": "Integration Test Record"}),
        }
        result = lambda_handler(event, mock_ctx)
        assert result["statusCode"] in (200, 201)

        # Verify in DB
        cur = db_connection.cursor()
        cur.execute("SELECT COUNT(*) FROM records WHERE name = %s",
                    ("Integration Test Record",))
        assert cur.fetchone()[0] == 1
```

## Pattern: Transaction Rollback on Error

```python
class TestTransactionHandling:
    def test_partial_failure_rolls_back(self, db_connection):
        cur = db_connection.cursor()

        # Start with known state
        cur.execute("DELETE FROM records")
        cur.execute("INSERT INTO records (id, name) VALUES (%s, %s)", ("txn-1", "Before"))

        # Simulate a transaction that should fail partway
        try:
            db_connection.autocommit = False
            cur.execute("INSERT INTO records (id, name) VALUES (%s, %s)", ("txn-2", "New"))
            # Force an error
            cur.execute("INSERT INTO records (id, name) VALUES (%s, %s)", ("txn-1", "Duplicate"))
        except Exception:
            db_connection.rollback()
        finally:
            db_connection.autocommit = True

        # txn-2 should NOT exist (rolled back)
        cur.execute("SELECT COUNT(*) FROM records WHERE id = %s", ("txn-2",))
        assert cur.fetchone()[0] == 0
```

## Pattern: Connection Pool Behavior

```python
class TestConnectionPool:
    """Test that connection pooling works correctly."""

    def test_multiple_handler_calls_reuse_connections(self, handler_env):
        """Simulate multiple Lambda invocations."""
        mock_ctx = MagicMock()
        mock_ctx.function_name = "test"
        mock_ctx.get_remaining_time_in_millis.return_value = 30000

        from handler.main import lambda_handler

        # Call handler multiple times (simulating warm Lambda invocations)
        for i in range(5):
            event = {
                "httpMethod": "GET",
                "pathParameters": {"id": f"conn-test-{i}"},
            }
            result = lambda_handler(event, mock_ctx)
            assert result["statusCode"] in (200, 404)
```

## Pattern: Batch Job with Database

```python
class TestBatchJobWithDB:
    """Test batch processing that reads/writes to PostgreSQL."""

    @pytest.fixture
    def seeded_db(self, db_connection):
        cur = db_connection.cursor()
        cur.execute("DELETE FROM records")
        for i in range(100):
            cur.execute(
                "INSERT INTO records (id, name, status) VALUES (%s, %s, %s)",
                (f"batch-{i:04d}", f"Record {i}", "pending"),
            )
        return db_connection

    def test_batch_processes_all_pending(self, seeded_db):
        cur = seeded_db.cursor()

        # Simulate batch processing
        cur.execute("SELECT id FROM records WHERE status = %s", ("pending",))
        pending = cur.fetchall()
        assert len(pending) == 100

        # Process them
        for (record_id,) in pending:
            cur.execute(
                "UPDATE records SET status = %s WHERE id = %s",
                ("processed", record_id),
            )

        # Verify
        cur.execute("SELECT COUNT(*) FROM records WHERE status = %s", ("processed",))
        assert cur.fetchone()[0] == 100
```
