"""Tests for the CLI entry point."""

import json
import re
from pathlib import Path

from aws_test_plugin.cli import _get_data_dir, _get_pkg_dir, cmd_init


def _repo_root() -> Path:
    """Return the repo root (contains .claude-plugin/, skills/, agents/)."""
    return Path(__file__).resolve().parent.parent


def test_data_dir_exists():
    """Package data directory should exist and contain skills."""
    data = _get_data_dir()
    assert data.exists()
    assert (data / "skills").is_dir()
    assert (data / "agents").is_dir()


def test_pkg_dir_has_agents_md():
    """Package dir should contain AGENTS.md for Codex install."""
    pkg = _get_pkg_dir()
    assert (pkg / "AGENTS.md").exists(), "AGENTS.md missing from package"


def test_pkg_dir_has_scripts():
    """Package dir should contain scaffold script."""
    pkg = _get_pkg_dir()
    assert (pkg / "scripts" / "scaffold.py").exists(), "scaffold.py missing"


def test_skills_have_skill_md():
    """Every skill directory should have a SKILL.md file."""
    skills_dir = _get_data_dir() / "skills"
    for skill in skills_dir.iterdir():
        if skill.is_dir():
            assert (skill / "SKILL.md").exists(), f"{skill.name} missing SKILL.md"


def test_skill_frontmatter_has_name_and_description():
    """Every SKILL.md should have name and description in frontmatter."""
    skills_dir = _get_data_dir() / "skills"
    for skill in skills_dir.iterdir():
        if not skill.is_dir():
            continue
        skill_md = skill / "SKILL.md"
        if not skill_md.exists():
            continue

        content = skill_md.read_text(encoding="utf-8")
        assert content.startswith("---"), f"{skill.name}/SKILL.md missing frontmatter"

        # Check for name and description in frontmatter
        frontmatter_end = content.index("---", 3)
        frontmatter = content[3:frontmatter_end]
        assert "name:" in frontmatter, f"{skill.name}/SKILL.md missing name"
        assert "description:" in frontmatter, f"{skill.name}/SKILL.md missing description"


def test_skill_name_matches_directory():
    """SKILL.md name field must match the directory name (npx skills add requirement)."""
    skills_dir = _get_data_dir() / "skills"
    for skill in skills_dir.iterdir():
        if not skill.is_dir():
            continue
        skill_md = skill / "SKILL.md"
        if not skill_md.exists():
            continue

        content = skill_md.read_text(encoding="utf-8")
        match = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
        assert match, f"{skill.name}/SKILL.md has no name field"
        assert match.group(1).strip() == skill.name, f"{skill.name}: name field '{match.group(1).strip()}' != dir name"


def test_skill_description_under_1024_chars():
    """Descriptions must be <=1024 chars (npx skills add limit)."""
    skills_dir = _get_data_dir() / "skills"
    for skill in skills_dir.iterdir():
        if not skill.is_dir():
            continue
        skill_md = skill / "SKILL.md"
        if not skill_md.exists():
            continue

        content = skill_md.read_text(encoding="utf-8")
        parts = content.split("---", 2)
        if len(parts) < 3:
            continue

        # Extract multiline description
        match = re.search(r"description:\s*>\s*\n((?:\s+.+\n)*)", parts[1])
        if match:
            desc = " ".join(match.group(1).split())
        else:
            match = re.search(r"description:\s*(.+)", parts[1])
            desc = match.group(1).strip() if match else ""

        assert len(desc) <= 1024, f"{skill.name}: description is {len(desc)} chars (max 1024)"


def test_skill_has_license():
    """Every SKILL.md should have a license field."""
    skills_dir = _get_data_dir() / "skills"
    for skill in skills_dir.iterdir():
        if not skill.is_dir():
            continue
        skill_md = skill / "SKILL.md"
        if not skill_md.exists():
            continue

        content = skill_md.read_text(encoding="utf-8")
        parts = content.split("---", 2)
        if len(parts) >= 3:
            assert "license:" in parts[1], f"{skill.name}/SKILL.md missing license"


def test_skill_reference_links_resolve():
    """Reference file links in SKILL.md must point to existing files."""
    skills_dir = _get_data_dir() / "skills"
    for skill in skills_dir.iterdir():
        if not skill.is_dir():
            continue
        skill_md = skill / "SKILL.md"
        if not skill_md.exists():
            continue

        content = skill_md.read_text(encoding="utf-8")
        # Find markdown links to references/
        refs = re.findall(r"\(references/([^)]+)\)", content)
        for ref in refs:
            ref_path = skill / "references" / ref
            assert ref_path.exists(), f"{skill.name}: broken reference link references/{ref}"


def test_agent_has_frontmatter():
    """Agent definitions should have YAML frontmatter."""
    agents_dir = _get_data_dir() / "agents"
    for agent_file in agents_dir.glob("*.md"):
        content = agent_file.read_text(encoding="utf-8")
        assert content.startswith("---"), f"{agent_file.name} missing frontmatter"
        assert "name:" in content, f"{agent_file.name} missing name"
        assert "skills:" in content, f"{agent_file.name} missing skills"


def test_agent_skills_all_exist():
    """Every skill listed in the agent definition should have a matching directory."""
    agents_dir = _get_data_dir() / "agents"
    skills_dir = _get_data_dir() / "skills"
    for agent_file in agents_dir.glob("*.md"):
        content = agent_file.read_text(encoding="utf-8")
        parts = content.split("---", 2)
        if len(parts) < 3:
            continue

        # Extract skills list from frontmatter
        in_skills = False
        for line in parts[1].splitlines():
            if line.strip().startswith("skills:"):
                in_skills = True
                continue
            if in_skills:
                if line.strip().startswith("- "):
                    skill_name = line.strip().lstrip("- ").strip()
                    assert (skills_dir / skill_name).is_dir(), (
                        f"Agent references skill '{skill_name}' but directory not found"
                    )
                elif not line.strip():
                    continue
                else:
                    break


def test_init_creates_claude_skills(tmp_path):
    """init with claude agent creates .claude/skills/ with all skill directories."""
    cmd_init(str(tmp_path), ["claude"])
    skills = tmp_path / ".claude" / "skills"
    assert skills.is_dir()
    expected = {
        "aws-test-orchestrator",
        "aws-unit-testing",
        "aws-e2e-testing",
        "aws-integration-testing",
        "aws-contract-testing",
        "aws-perf-load-testing",
    }
    actual = {d.name for d in skills.iterdir() if d.is_dir()}
    assert actual == expected


def test_init_creates_copilot_skills(tmp_path):
    """init with copilot agent creates .github/skills/."""
    cmd_init(str(tmp_path), ["copilot"])
    assert (tmp_path / ".github" / "skills").is_dir()
    assert (tmp_path / ".github" / "agents" / "aws-test-engineer.md").exists()


def test_init_creates_codex_agents_md(tmp_path):
    """init with codex agent creates AGENTS.md at project root."""
    cmd_init(str(tmp_path), ["codex"])
    agents_md = tmp_path / "AGENTS.md"
    assert agents_md.exists(), "AGENTS.md not created for Codex"
    content = agents_md.read_text(encoding="utf-8")
    assert "AWS Test Plugin" in content


def test_init_skip_existing(tmp_path):
    """init should not overwrite existing files."""
    # First install
    cmd_init(str(tmp_path), ["claude"])
    # Modify a file
    marker = tmp_path / ".claude" / "skills" / "aws-test-orchestrator" / "SKILL.md"
    marker.write_text("custom content", encoding="utf-8")
    # Second install
    cmd_init(str(tmp_path), ["claude"])
    # Should NOT be overwritten


# ── Claude Code plugin manifest tests ──


def test_plugin_json_exists():
    """Repo must have .claude-plugin/plugin.json for Claude Code plugin system."""
    manifest = _repo_root() / ".claude-plugin" / "plugin.json"
    assert manifest.exists(), ".claude-plugin/plugin.json missing — not a valid Claude Code plugin"


def test_plugin_json_valid():
    """plugin.json must be valid JSON with required fields."""
    manifest = _repo_root() / ".claude-plugin" / "plugin.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert "name" in data, "plugin.json missing required 'name' field"
    assert isinstance(data["name"], str)
    assert len(data["name"]) > 0


def test_plugin_json_name_is_kebab_case():
    """plugin.json name must be kebab-case (no spaces)."""
    manifest = _repo_root() / ".claude-plugin" / "plugin.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    name = data["name"]
    assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name), f"plugin name '{name}' is not kebab-case"


def test_plugin_components_not_inside_claude_plugin_dir():
    """skills/, agents/ must be at plugin root, NOT inside .claude-plugin/."""
    claude_plugin = _repo_root() / ".claude-plugin"
    assert not (claude_plugin / "skills").exists(), "skills/ must not be inside .claude-plugin/"
    assert not (claude_plugin / "agents").exists(), "agents/ must not be inside .claude-plugin/"
    assert not (claude_plugin / "commands").exists(), "commands/ must not be inside .claude-plugin/"
