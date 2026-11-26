"""Reports need executed tests before they can show a pass."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "xml",
    [None, '<testsuite tests="0"/>', '<testsuite tests="2" skipped="2"/>'],
)
def test_empty_or_all_skipped_reports_are_incomplete(tmp_path, xml):
    if xml is not None:
        (tmp_path / "unit_results.xml").write_text(xml, encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "src/aws_test_plugin/scripts/analyze_results.py"
    result = subprocess.run([sys.executable, str(script), str(tmp_path)], capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert "INCOMPLETE" in result.stdout
    assert "All analyzed results look good" not in result.stdout
