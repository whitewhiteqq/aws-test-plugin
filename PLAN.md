# Rename: `claude-aws-test-plugin` → `aws-test-plugin`

## Summary

Drop the `claude-` prefix from the project name to make it agent-agnostic for marketplace publishing. The plugin already supports Claude Code, GitHub Copilot, and OpenAI Codex — the name should reflect that.

## Naming Changes

| What | Old | New |
|------|-----|-----|
| Package name | `claude-aws-test-plugin` | `aws-test-plugin` |
| Python module | `claude_aws_test_plugin` | `aws_test_plugin` |
| CLI command | `aws-test-plugin` | `aws-test-plugin` (unchanged) |
| Skill names | `aws-*` | `aws-*` (unchanged) |
| Agent name | `aws-test-engineer` | `aws-test-engineer` (unchanged) |
| Repo URL refs | `whitewhiteqq/claude-aws-test-plugin` | `whitewhiteqq/aws-test-plugin` |

## Steps

### 1. Rename Python module directory
- `src/claude_aws_test_plugin/` → `src/aws_test_plugin/`

### 2. Update `pyproject.toml`
- `name = "aws-test-plugin"`
- `claude_aws_test_plugin.cli:main` → `aws_test_plugin.cli:main`
- `packages = ["src/aws_test_plugin"]`
- All `claude_aws_test_plugin/` force-include paths → `aws_test_plugin/`
- `claude-aws-test-plugin[all]` self-ref → `aws-test-plugin[all]`
- All GitHub URLs: `claude-aws-test-plugin` → `aws-test-plugin`

### 3. Update `.claude-plugin/plugin.json`
- `name`: `aws-test-plugin`
- `homepage` / `repository` URLs

### 4. Update `src/aws_test_plugin/__init__.py`
- Docstring: `"""aws-test-plugin — ..."""`

### 5. Update `src/aws_test_plugin/cli.py`
- Docstring: `"""CLI entry point for aws-test-plugin."""`
- `files("aws_test_plugin")` import reference
- `pip install 'aws-test-plugin[test]'` message (already correct)

### 6. Update `src/aws_test_plugin/AGENTS.md`
- `claude-aws-test-plugin` → `aws-test-plugin` in text

### 7. Update `tests/test_cli.py`
- `from claude_aws_test_plugin.cli` → `from aws_test_plugin.cli`
- `"AWS Test Plugin"` assertion text (already correct)

### 8. Update `README.md`
- Title: `# aws-test-plugin`
- All `claude-aws-test-plugin` references → `aws-test-plugin`
- All `claude-aws-test-plugin/` path refs in commands → `aws-test-plugin/`
- Plugin namespace ref: `/claude-aws-test-plugin:aws-test-orchestrator` → `/aws-test-plugin:aws-test-orchestrator`

### 9. Update `CONTRIBUTING.md`
- Title: `# Contributing to aws-test-plugin`
- All `claude-aws-test-plugin` → `aws-test-plugin`
- Directory tree: `claude-aws-test-plugin/` → `aws-test-plugin/`
- `src/claude_aws_test_plugin/` → `src/aws_test_plugin/`

### 10. Regenerate `uv.lock`
- Run `uv lock` to update the lock file with the new package name

### 11. Run tests
- `uv run pytest tests/ -v` to verify everything works

## NOT Changing
- Skill directory names (`aws-*`) — they're correct as-is
- Skill SKILL.md `name:` fields — must match directory names
- Agent name (`aws-test-engineer`) — correct
- CLI command (`aws-test-plugin`) — already the target name
- Reference pattern files — no project name references
- `.github/workflows/` — no project name references
- `.github/CODEOWNERS`, `pull_request_template.md` — no project name references

## Risk
- The git repo directory itself (`claude-aws-test-plugin/`) is outside our scope — that's the local clone name and the GitHub repo name, which the user can rename separately on GitHub.
