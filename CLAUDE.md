# CLAUDE.md — Agent Instructions for aws-test-plugin

This file is read by Claude Code before any operation in this repository.
Follow all rules here in addition to the instructions in `src/aws_test_plugin/AGENTS.md`.

## Commands

```bash
# Sync dependencies (after cloning or pulling)
uv sync --locked

# Run all tests
uv run pytest tests/ -v

# Lint — check mode (CI)
uv run ruff check src tests
uv run ruff format --check src tests

# Lint — fix mode (local dev: always fix before format)
uv run ruff check --fix src tests
uv run ruff format src tests

# Type checking — ty is the primary checker (fast, replaces mypy)
uv run ty check src

# Type checking — mypy (secondary; kept for compatibility)
uv run mypy src

# Security scans
uv run bandit -q -c pyproject.toml -r src
uv run pip-audit

# Verify lockfile is up to date (must pass before any commit)
uv lock --check

# Regenerate lockfile when pyproject.toml changes
uv lock
```

## Change Workflow

Every change, regardless of size, follows this sequence:

1. **Branch** — `git checkout -b feat/<name>` or `fix/<name>` from `develop`
2. **Implement** — make the change
3. **Docs review** — ask: does this change affect README.md, CONTRIBUTING.md, or CLAUDE.md?
   - CI/CD changes → update CLAUDE.md (Commands section) if any command changes
   - Dependency changes → update README.md and CONTRIBUTING.md if setup steps change
   - Workflow/process changes → update CLAUDE.md (relevant section)
   - `src/` public API changes → update README.md usage examples
4. **Version bump** — see Version Policy below
5. **Local checks** — must all pass before committing:
   ```bash
   uv lock --check
   uv run ruff check src tests
   uv run ruff format --check src tests
   uv run ty check src        # or: uv run mypy src
   uv run pytest tests/ -v
   uv run bandit -q -c pyproject.toml -r src
   ```
6. **Commit** — conventional commit with full body for non-trivial changes
7. **PR → develop → main** — follow Branch Strategy below

## Version Policy

Bump the version in `pyproject.toml` (and run `uv lock`) only when the
**installed package changes**:

| Change type | Bump? |
|---|---|
| `src/aws_test_plugin/` code change | **Yes** |
| Runtime dep added/removed/changed (`[project.dependencies]`) | **Yes** |
| Dev dep change (`[dependency-groups] dev`) | No |
| CI/CD workflow change (`.github/`) | No |
| Docs only (`README.md`, `CONTRIBUTING.md`, `CLAUDE.md`) | No |
| Tool config (`[tool.ruff]`, `[tool.ty]`, etc.) | No |
| `skills/`, `agents/` content | No |

Version follows [Semantic Versioning](https://semver.org/):
- **patch** (0.1.x) — bug fixes, no API change
- **minor** (0.x.0) — new backward-compatible features
- **major** (x.0.0) — breaking changes

## Pre-Commit Enforcement

**Always run `uv lock --check` before committing.**
If it reports that `uv.lock` needs updating, run `uv lock` first, stage
`uv.lock`, and include it in the same commit as the `pyproject.toml` change.

Never commit a stale lockfile. The CI `lockfile` job runs `uv lock --check`
on every push and pull request; a stale lockfile will block the entire
pipeline.

Triggers that require `uv lock`:
- Any edit to `pyproject.toml` (adding, removing, or changing a dependency)
- Any uv or Python version bump

## Branch Strategy

Releases follow exactly one path:

```
feature/fix branch  →  develop  →  main  →  annotated tag  →  GitHub Release  →  PyPI
```

- **Never push directly to `main` or `develop`.**
- Branch from `develop` for all changes: `git checkout -b feat/<name> origin/develop`
- Open a pull request targeting `develop`.
- Release promotion: maintainer runs `git merge --ff-only develop` from `main`
  locally, then pushes. No GitHub merge button for main promotion.
- PyPI publish is triggered only by creating a GitHub Release targeting a
  version tag on `main`.

## Commit Message Style

Use Conventional Commits. For non-trivial changes include the full body:

```
type(scope): short imperative summary

INTENTION:
WHAT CHANGED:
WHY:
ALTERNATIVES CONSIDERED:
REFS:
VERIFIED:
```

See `CONTRIBUTING.md` for the full template and examples.

## Project Layout

```
aws-test-plugin/
├── CLAUDE.md                         # This file — agent instructions
├── CONTRIBUTING.md                   # Human + AI contributor guide
├── pyproject.toml                    # Project metadata and deps
├── uv.lock                           # Locked dependency graph (never stale)
├── skills/                           # Skill definitions
├── agents/                           # Agent definitions
├── src/aws_test_plugin/
│   ├── __init__.py
│   ├── cli.py
│   ├── AGENTS.md                     # Codex-compatible instructions
│   └── scripts/
└── tests/
```

## Safety

- Never run E2E or load tests against production without confirmation.
- Never hardcode secrets. Use `.env` (gitignored) or AWS Secrets Manager/SSM.
- All test data uses prefixes: `TEST-`, `E2E-TEST-`, `LOAD-TEST-`.
- Integration tests use moto — no real AWS calls.
