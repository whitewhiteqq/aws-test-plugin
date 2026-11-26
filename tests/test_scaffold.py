"""Regression checks for scaffolding an existing AWS project."""

import pytest

from aws_test_plugin.scripts.scaffold import (
    create_test_structure,
    discover_api_specs,
    discover_batch_jobs,
    discover_lambdas,
    discover_step_functions,
)


@pytest.mark.parametrize("ignored", [".venv", "node_modules", ".git", "build", "tests"])
def test_discovery_ignores_generated_and_test_trees(tmp_path, ignored):
    for parent in [tmp_path / "src", tmp_path / ignored / "nested"]:
        component = parent / "batch-worker"
        component.mkdir(parents=True)
        for name in ["handler.py", "Dockerfile", "workflow.asl.json", "openapi.json"]:
            (component / name).touch()

    component = tmp_path / "src" / "batch-worker"
    assert discover_lambdas(tmp_path) == [component]
    assert discover_batch_jobs(tmp_path) == [component]
    assert discover_step_functions(tmp_path) == [component / "workflow.asl.json"]
    assert discover_api_specs(tmp_path) == [component / "openapi.json"]


@pytest.mark.parametrize(
    ("config", "content"),
    [
        ("pyproject.toml", '[tool.pytest.ini_options]\ntestpaths = ["existing"]\n'),
        ("setup.cfg", "[tool:pytest]\ntestpaths = existing\n"),
        ("tox.ini", "[pytest]\ntestpaths = existing\n"),
        ("pytest.toml", '[pytest]\ntestpaths = ["existing"]\n'),
    ],
)
def test_scaffold_preserves_existing_pytest_configuration(tmp_path, config, content):
    (tmp_path / config).write_text(content, encoding="utf-8")
    create_test_structure(tmp_path, [], [])
    assert not (tmp_path / "pytest.ini").exists()
    assert (tmp_path / config).read_text(encoding="utf-8") == content


def test_scaffold_adds_real_secret_ignore_rules_once(tmp_path):
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("# .env documentation\n!.env.example\n", encoding="utf-8")
    create_test_structure(tmp_path, [], [])
    first = gitignore.read_text(encoding="utf-8")
    create_test_structure(tmp_path, [], [])
    assert gitignore.read_text(encoding="utf-8") == first
    assert ".env" in first.splitlines()
    assert ".env.*" in first.splitlines()
    assert first.splitlines()[-1] == "!.env.example"


def test_scaffold_keeps_existing_fixtures(tmp_path):
    conftest = tmp_path / "tests" / "conftest.py"
    conftest.parent.mkdir()
    conftest.write_text("# Project fixtures\n", encoding="utf-8")
    create_test_structure(tmp_path, [], [])
    assert conftest.read_text(encoding="utf-8") == "# Project fixtures\n"


def test_scaffold_rejects_test_directory_link_outside_project(tmp_path):
    root = tmp_path / "project"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    try:
        (root / "tests").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Directory symlinks unavailable: {exc}")
    with pytest.raises(ValueError, match="escapes project directory"):
        create_test_structure(root, [], [])
    assert list(outside.iterdir()) == []
