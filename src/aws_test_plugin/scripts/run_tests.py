#!/usr/bin/env python3
"""
Run tests by category with proper configuration.

Secrets/URLs are loaded from .env (never hardcoded). Copy .env.example to .env
and fill in real values for E2E/load tests. Unit/integration/contract tests
work with the defaults.

Usage:
    python run_tests.py unit                 # Unit tests only
    python run_tests.py integration          # Integration tests
    python run_tests.py all                  # All offline (unit+contract+integration+performance)
    python run_tests.py e2e                  # E2E (reads component-specific config from .env)
    python run_tests.py load --users 50      # Load test (reads host from .env)
    python run_tests.py full                 # Offline + deployed E2E; configure the target first
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from defusedxml import ElementTree as ET


def _load_dotenv(root: str = ".") -> None:
    """Load .env file into os.environ (no dependency on python-dotenv)."""
    env_file = Path(root).resolve() / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key not in os.environ:
            os.environ[key] = value


OFFLINE_CATEGORIES = ("unit", "integration", "contract", "performance")


def run_pytest(category: str, extra_args: list[str] | None = None, root: str = ".") -> int | None:
    """Run pytest for a specific test category."""
    test_dir = Path(root) / "tests" / category
    if not test_dir.exists():
        print(f"  SKIP  {category} (directory tests/{category}/ not found)")
        return None

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        f"tests/{category}/",
        "-m",
        category,
        "-v",
        "--tb=short",
    ]
    if category == "unit":
        cmd.extend(["--cov=src/", "--cov-branch", "--cov-report=term-missing"])
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(f"--junitxml=tests/reports/{category}_results.xml")

    print(f"\n{'=' * 60}")
    print(f"Running {category} tests")
    print(f"{'=' * 60}\n")

    env = os.environ.copy()
    if category in OFFLINE_CATEGORIES:
        env.update(
            AWS_ACCESS_KEY_ID="testing",
            AWS_SECRET_ACCESS_KEY="testing",
            AWS_SECURITY_TOKEN="testing",
            AWS_SESSION_TOKEN="testing",
            AWS_DEFAULT_REGION="us-east-1",
            AWS_REGION="us-east-1",
            AWS_EC2_METADATA_DISABLED="true",
        )
        env.pop("AWS_PROFILE", None)
        env.pop("AWS_DEFAULT_PROFILE", None)
    result = subprocess.run(cmd, cwd=root, env=env, check=False)
    if result.returncode == 0:
        report = ET.parse(Path(root) / "tests/reports" / f"{category}_results.xml").getroot()
        if report is None:
            raise ValueError("Empty JUnit report")
        suites = [report] if report.tag == "testsuite" else report.findall(".//testsuite")
        executed = sum(int(suite.get("tests", 0)) - int(suite.get("skipped", 0)) for suite in suites)
        if executed == 0:
            print(f"INCOMPLETE: {category} has no executed tests (empty or entirely skipped)")
            return 5
    return result.returncode


def run_locust(base_url: str, users: int, duration: str, root: str = ".") -> int:
    """Run Locust load tests."""
    locustfile = Path(root) / "tests" / "load" / "locustfile.py"
    if not locustfile.exists():
        print(f"Error: {locustfile} not found")
        return 1

    cmd = [
        sys.executable,
        "-m",
        "locust",
        "-f",
        "tests/load/locustfile.py",
        f"--host={base_url}",
        f"--users={users}",
        f"--spawn-rate={max(1, users // 10)}",
        f"--run-time={duration}",
        "--headless",
        "--csv=tests/reports/load",
        "--html=tests/reports/load.html",
    ]

    print(f"\n{'=' * 60}")
    print(f"Running load test: {users} users, {duration}")
    print(f"Target: {base_url}")
    print(f"{'=' * 60}\n")

    result = subprocess.run(cmd, cwd=root, check=False)
    return result.returncode


def _run_categories(categories: list[str], extra: list[str], root: str) -> dict[str, int | None]:
    """Run multiple pytest categories and return results."""
    results = {}
    for cat in categories:
        results[cat] = run_pytest(cat, extra, root)
    return results


def _print_summary(results: dict[str, int | None]) -> bool:
    """Print results table. Returns True if all passed."""
    print(f"\n{'=' * 60}")
    print("Results Summary")
    print(f"{'=' * 60}")
    for cat, rc in results.items():
        status = "SKIP" if rc is None else "PASS" if rc == 0 else "EMPTY" if rc == 5 else "FAIL"
        print(f"  {cat}: {status}")
    all_pass = all(rc == 0 for rc in results.values())
    if all_pass:
        print("\nAll tests passed.")
    else:
        print("\nTesting incomplete or failed. Missing suites are not passes.")
    return all_pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AWS project tests")
    parser.add_argument(
        "category",
        choices=["unit", "integration", "contract", "e2e", "performance", "load", "all", "full"],
        help="Test category to run. 'all' = offline tests. 'full' = offline + E2E (1-click).",
    )
    parser.add_argument("--base-url", help="Base URL for load tests only (overrides LOAD_TEST_HOST)")
    parser.add_argument("--users", type=int, default=50, help="Locust user count")
    parser.add_argument("--duration", default="5m", help="Locust run duration")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--extra", nargs="*", default=[], help="Extra pytest args")

    args = parser.parse_args()
    if args.base_url and args.category != "load":
        parser.error("--base-url is supported only for load tests; E2E uses per-component configuration")
    if args.users <= 0:
        parser.error("--users must be positive")
    if args.category == "load":
        import re

        if not re.fullmatch(r"(?:\d+h)?(?:\d+m)?(?:\d+s)?|\d+", args.duration) or not any(
            digit in args.duration for digit in "123456789"
        ):
            parser.error("--duration must be a positive, bounded duration such as 30s or 5m")
    args.project_root = str(Path(args.project_root).resolve())
    if args.category in ("e2e", "load"):
        _load_dotenv(args.project_root)

    reports_dir = Path(args.project_root) / "tests" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    if args.category == "all":
        # All offline tests (no deployed environment needed)
        categories = list(OFFLINE_CATEGORIES)
        results = _run_categories(categories, args.extra, args.project_root)
        if not _print_summary(results):
            sys.exit(1)

    elif args.category == "full":
        # 1-click: run everything possible
        # Phase 1: offline tests (always run)
        categories = list(OFFLINE_CATEGORIES)
        results = _run_categories(categories, args.extra, args.project_root)

        # Phase 2: E2E tests (always attempt — tests self-skip if
        # per-component env vars are not set)
        _load_dotenv(args.project_root)
        results["e2e"] = run_pytest("e2e", args.extra, args.project_root)

        if not _print_summary(results):
            sys.exit(1)

    elif args.category == "load":
        base_url = args.base_url or os.getenv("LOAD_TEST_HOST")
        if not base_url:
            print("Error: --base-url required, or set LOAD_TEST_HOST in .env")
            sys.exit(1)
        sys.exit(run_locust(base_url, args.users, args.duration, args.project_root))

    elif args.category == "e2e":
        # E2E tests self-skip via pytest.skip() when their per-component
        # env vars (e.g. ORDERS_API_BASE_URL) are not set, so we just run them.
        rc = run_pytest("e2e", args.extra, args.project_root)
        sys.exit(5 if rc is None else rc)

    else:
        rc = run_pytest(args.category, args.extra, args.project_root)
        sys.exit(5 if rc is None else rc)


if __name__ == "__main__":
    main()
