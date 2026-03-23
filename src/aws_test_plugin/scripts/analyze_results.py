#!/usr/bin/env python3
"""
Analyze test results from JUnit XML, Locust CSV, and pytest-benchmark JSON.

Usage:
    python analyze_results.py tests/reports/
"""

import csv
import json
import sys
from pathlib import Path

from defusedxml import ElementTree as ET


def analyze_junit(xml_path: Path) -> dict:
    """Parse JUnit XML and return summary."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    if root is None:
        raise ValueError(f"Invalid JUnit XML file: {xml_path}")

    suites = root.findall(".//testsuite") if root.tag != "testsuite" else [root]
    total = errors = failures = skipped = 0
    failed_tests = []

    for suite in suites:
        total += int(suite.get("tests", 0))
        errors += int(suite.get("errors", 0))
        failures += int(suite.get("failures", 0))
        skipped += int(suite.get("skipped", 0))

        for tc in suite.findall("testcase"):
            failure = tc.find("failure")
            error = tc.find("error")
            detail = failure if failure is not None else error
            if detail is not None:
                msg = detail.get("message", "")
                failed_tests.append(
                    {
                        "name": f"{tc.get('classname')}.{tc.get('name')}",
                        "message": msg[:200],
                    }
                )

    return {
        "file": xml_path.name,
        "total": total,
        "passed": total - errors - failures - skipped,
        "failed": errors + failures,
        "skipped": skipped,
        "failed_tests": failed_tests,
    }


def analyze_locust(stats_path: Path) -> dict:
    """Parse Locust stats CSV and return summary."""
    results = []
    aggregated = None

    with open(stats_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            entry = {
                "name": row.get("Name", ""),
                "requests": int(row.get("Request Count", 0)),
                "failures": int(row.get("Failure Count", 0)),
                "avg_ms": float(row.get("Average Response Time", 0)),
                "p50_ms": float(row.get("50%", 0)),
                "p95_ms": float(row.get("95%", 0)),
                "p99_ms": float(row.get("99%", 0)),
                "rps": float(row.get("Requests/s", 0)),
            }
            if entry["name"] == "Aggregated":
                aggregated = entry
            else:
                results.append(entry)

    return {
        "file": stats_path.name,
        "endpoints": results,
        "aggregated": aggregated,
    }


def analyze_benchmark(json_path: Path) -> dict:
    """Parse pytest-benchmark JSON and return summary."""
    with open(json_path) as f:
        data = json.load(f)

    benchmarks = []
    for bm in data.get("benchmarks", []):
        benchmarks.append(
            {
                "name": bm.get("name", ""),
                "min_ms": bm["stats"]["min"] * 1000,
                "max_ms": bm["stats"]["max"] * 1000,
                "mean_ms": bm["stats"]["mean"] * 1000,
                "median_ms": bm["stats"]["median"] * 1000,
                "stddev_ms": bm["stats"]["stddev"] * 1000,
                "rounds": bm["stats"]["rounds"],
            }
        )

    return {
        "file": json_path.name,
        "benchmarks": benchmarks,
    }


def print_junit_report(result: dict):
    """Print JUnit analysis."""
    print(f"\n--- {result['file']} ---")
    status = "PASS" if result["failed"] == 0 else "FAIL"
    print(f"  Status: {status}")
    print(
        f"  Total: {result['total']}  "
        f"Passed: {result['passed']}  "
        f"Failed: {result['failed']}  "
        f"Skipped: {result['skipped']}"
    )

    if result["failed_tests"]:
        print("  Failures:")
        for ft in result["failed_tests"]:
            print(f"    - {ft['name']}: {ft['message']}")


def print_locust_report(result: dict):
    """Print Locust analysis."""
    print(f"\n--- {result['file']} ---")
    agg = result.get("aggregated")
    if agg:
        error_pct = agg["failures"] / agg["requests"] * 100 if agg["requests"] > 0 else 0
        print(f"  Total Requests: {agg['requests']}")
        print(f"  Error Rate: {error_pct:.1f}%")
        print(
            f"  Avg: {agg['avg_ms']:.0f}ms  "
            f"p50: {agg['p50_ms']:.0f}ms  "
            f"p95: {agg['p95_ms']:.0f}ms  "
            f"p99: {agg['p99_ms']:.0f}ms"
        )
        print(f"  Throughput: {agg['rps']:.1f} req/s")

    if result["endpoints"]:
        print("\n  Per-endpoint:")
        for ep in result["endpoints"]:
            print(
                f"    {ep['name']}: avg={ep['avg_ms']:.0f}ms "
                f"p95={ep['p95_ms']:.0f}ms "
                f"({ep['requests']} reqs, {ep['failures']} fails)"
            )


def print_benchmark_report(result: dict):
    """Print benchmark analysis."""
    print(f"\n--- {result['file']} ---")
    for bm in result["benchmarks"]:
        print(f"  {bm['name']}:")
        print(
            f"    mean={bm['mean_ms']:.2f}ms  "
            f"median={bm['median_ms']:.2f}ms  "
            f"min={bm['min_ms']:.2f}ms  "
            f"max={bm['max_ms']:.2f}ms  "
            f"({bm['rounds']} rounds)"
        )


def main():
    reports_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "tests/reports")

    if not reports_dir.exists():
        print(f"Reports directory not found: {reports_dir}")
        sys.exit(1)

    print(f"Analyzing results in {reports_dir}/\n")
    print("=" * 60)

    has_failures = False

    # JUnit XML files
    for xml_file in sorted(reports_dir.glob("*_results.xml")):
        result = analyze_junit(xml_file)
        print_junit_report(result)
        if result["failed"] > 0:
            has_failures = True

    # Locust CSV files
    for csv_file in sorted(reports_dir.glob("*_stats.csv")):
        result = analyze_locust(csv_file)
        print_locust_report(result)

    # Benchmark JSON files
    for json_file in sorted(reports_dir.glob("*benchmark*.json")):
        result = analyze_benchmark(json_file)
        print_benchmark_report(result)

    print(f"\n{'=' * 60}")
    if has_failures:
        print("RESULT: Some tests failed. See details above.")
        sys.exit(1)
    else:
        print("RESULT: All analyzed results look good.")


if __name__ == "__main__":
    main()
