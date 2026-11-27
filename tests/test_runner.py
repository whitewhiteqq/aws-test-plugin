"""Check the runner's observable results without contacting AWS."""

import os
import subprocess
import sys
from pathlib import Path


def run_runner(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    script = Path(__file__).resolve().parents[1] / "src/aws_test_plugin/scripts/run_tests.py"
    return subprocess.run(
        [sys.executable, str(script), *args, "--project-root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_no_suites_cannot_report_success(tmp_path):
    result = run_runner(tmp_path, "all")
    assert result.returncode != 0
    assert "unit: SKIP" in result.stdout
    assert "All tests passed" not in result.stdout


def test_e2e_rejects_ignored_url_override(tmp_path):
    result = run_runner(tmp_path, "e2e", "--base-url", "https://staging.example")
    assert result.returncode == 2
    assert "--base-url is supported only for load tests" in result.stderr
    assert not (tmp_path / "tests/reports").exists()


def test_all_skipped_suite_is_incomplete(tmp_path):
    e2e = tmp_path / "tests/e2e"
    e2e.mkdir(parents=True)
    (e2e / "test_optional.py").write_text(
        'import pytest\n@pytest.mark.e2e\n@pytest.mark.skip(reason="Optional config absent")\n'
        "def test_optional():\n    pass\n",
        encoding="utf-8",
    )
    result = run_runner(tmp_path, "e2e")
    assert result.returncode == 5, result.stdout + result.stderr
    assert "INCOMPLETE" in result.stdout


def test_runner_owns_report_path_when_extra_args_override_junit(tmp_path):
    e2e = tmp_path / "tests/e2e"
    e2e.mkdir(parents=True)
    (e2e / "test_local.py").write_text(
        "import pytest\n@pytest.mark.e2e\ndef test_local():\n    pass\n", encoding="utf-8"
    )
    result = run_runner(tmp_path, "e2e", "--extra=--junitxml=custom.xml")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "tests/reports/e2e_results.xml").is_file()


def test_offline_runner_uses_fake_credentials_before_collection(tmp_path, monkeypatch):
    unit = tmp_path / "tests/unit"
    unit.mkdir(parents=True)
    (unit / "test_env.py").write_text(
        "import os\nimport pytest\n"
        "assert os.environ['AWS_ACCESS_KEY_ID'] == 'testing'\n"
        "assert os.environ['AWS_EC2_METADATA_DISABLED'] == 'true'\n"
        "assert 'PLUGIN_SENTINEL' not in os.environ\n"
        "@pytest.mark.unit\ndef test_offline():\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text("PLUGIN_SENTINEL=secret\n", encoding="utf-8")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ambient-key")
    monkeypatch.delenv("PLUGIN_SENTINEL", raising=False)
    result = run_runner(tmp_path, "unit")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
    assert os.environ["AWS_ACCESS_KEY_ID"] == "ambient-key"
