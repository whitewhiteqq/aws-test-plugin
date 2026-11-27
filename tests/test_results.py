"""Reports need executed tests before they can show a pass."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _analyze(reports_dir):
    script = Path(__file__).resolve().parents[1] / "src/aws_test_plugin/scripts/analyze_results.py"
    return subprocess.run([sys.executable, str(script), str(reports_dir)], capture_output=True, text=True, check=False)


LOCUST_HEADER = "Type,Name,Request Count,Failure Count,Average Response Time,50%,95%,99%,Requests/s\n"


@pytest.mark.parametrize(
    "xml",
    [None, '<testsuite tests="0"/>', '<testsuite tests="2" skipped="2"/>'],
)
def test_empty_or_all_skipped_reports_are_incomplete(tmp_path, xml):
    if xml is not None:
        (tmp_path / "unit_results.xml").write_text(xml, encoding="utf-8")
    result = _analyze(tmp_path)
    assert result.returncode == 1
    assert "INCOMPLETE" in result.stdout
    assert "All analyzed results look good" not in result.stdout


@pytest.mark.parametrize(
    ("rows", "expected_exit", "expected_message"),
    [
        (",Aggregated,12,0,1,1,1,1,1\n", 0, "All analyzed results look good"),
        (",Aggregated,10,1,1,1,1,1,1\n", 1, "Some tests failed"),
        (",Aggregated,0,0,0,0,0,0,0\n", 1, "INCOMPLETE"),
        ("GET,owned-health,12,0,1,1,1,1,1\n", 1, "INCOMPLETE"),
        ("", 1, "INCOMPLETE"),
    ],
)
def test_locust_reports_require_successful_executed_requests(tmp_path, rows, expected_exit, expected_message):
    (tmp_path / "load_stats.csv").write_text(LOCUST_HEADER + rows, encoding="utf-8")

    result = _analyze(tmp_path)

    assert result.returncode == expected_exit, result.stdout
    assert expected_message in result.stdout


@pytest.mark.parametrize(
    ("rounds", "expected_exit", "expected_message"),
    [(2, 0, "All analyzed results look good"), (0, 1, "INCOMPLETE"), (None, 1, "INCOMPLETE")],
)
def test_benchmark_reports_require_executed_rounds(tmp_path, rounds, expected_exit, expected_message):
    benchmarks = []
    if rounds is not None:
        benchmarks.append(
            {
                "name": "owned-benchmark",
                "stats": {
                    "min": 0.001,
                    "max": 0.002,
                    "mean": 0.0015,
                    "median": 0.0015,
                    "stddev": 0.0005,
                    "rounds": rounds,
                },
            }
        )
    (tmp_path / "benchmark_results.json").write_text(json.dumps({"benchmarks": benchmarks}), encoding="utf-8")

    result = _analyze(tmp_path)

    assert result.returncode == expected_exit, result.stdout
    assert expected_message in result.stdout


@pytest.mark.parametrize("other_report", ["failed-load", "empty-benchmark"])
def test_passing_junit_does_not_hide_invalid_other_reports(tmp_path, other_report):
    (tmp_path / "unit_results.xml").write_text(
        '<testsuite tests="1"><testcase name="owned"/></testsuite>', encoding="utf-8"
    )
    if other_report == "failed-load":
        (tmp_path / "load_stats.csv").write_text(LOCUST_HEADER + ",Aggregated,10,1,1,1,1,1,1\n", encoding="utf-8")
    else:
        (tmp_path / "benchmark_results.json").write_text('{"benchmarks":[]}', encoding="utf-8")

    result = _analyze(tmp_path)

    assert result.returncode == 1, result.stdout
    assert "All analyzed results look good" not in result.stdout
