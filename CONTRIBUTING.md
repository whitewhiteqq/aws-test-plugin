# Contributing to aws-test-plugin

## Development Setup

```bash
# Clone
git clone https://github.com/whitewhiteqq/aws-test-plugin.git
cd aws-test-plugin

# Install uv (if not already installed)
# Windows: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh

# Install with dev dependencies
uv sync

# Run tests
uv run pytest tests/ -v

# Lint
uv run ruff check src tests
uv run ruff format --check src tests

# Type checking
uv run mypy src

# Security scans
uv run bandit -q -c pyproject.toml -r src
uv run pip-audit
```

## Project Structure

```
aws-test-plugin/
├── skills/                         # Skill definitions (auto-discovered by npx skills add)
│   ├── aws-test-orchestrator/SKILL.md
│   ├── aws-e2e-testing/            # SKILL.md + references/
│   ├── aws-integration-testing/
│   ├── aws-contract-testing/
│   └── aws-perf-load-testing/
├── agents/
│   └── aws-test-engineer.md        # Agent definition
├── src/aws_test_plugin/
│   ├── __init__.py                 # Package version
│   ├── cli.py                      # CLI entry point (aws-test-plugin command)
│   ├── AGENTS.md                   # Codex-compatible instructions
│   └── scripts/                    # Scaffold, run, analyze scripts
└── tests/
```

## Adding a New Skill

1. Create `skills/<skill-name>/SKILL.md`
2. Add YAML frontmatter with `name`, `description`, `license`, and `metadata`
3. Add reference patterns in `references/` subdirectory
4. Update the orchestrator skill's delegation table if needed
5. Add the skill name to the agent's `skills:` list in `agents/aws-test-engineer.md`

## Adding Reference Patterns

Reference files go in `skills/<skill-name>/references/<pattern-name>.md`.
Each file should contain:
- A clear heading describing the pattern category
- Multiple `## Pattern N: <Name>` sections
- Complete, runnable Python code blocks
- Inline comments explaining key decisions

## Skill YAML Frontmatter

```yaml
---
name: skill-name              # Must match directory name
license: Apache-2.0
metadata:
  author: whitewhiteqq
  version: "0.1.0"
description: >                # Max 1024 chars — this triggers the skill
  What it does, when to use it,
  trigger phrases that should activate it.
---
```

## Code Style

- Python 3.10+ (use `|` union types, not `Optional`)
- Ruff for linting and formatting
- Keep runtime dependencies minimal and justified
- Test patterns should be self-contained and runnable

## Git as Engineering Memory

This project treats git history as a **persistent knowledge base** for both
human contributors and AI agents — not just a code transport mechanism.
Every commit message, PR description, and release tag is a record that
future readers will use to reconstruct *why* the codebase looks the way it
does, without opening a browser or searching Slack.

Design every commit message as if it will be read with zero prior context.
The goal: anyone should be able to run `git log --oneline`, pick a commit,
read its body, and fully understand the decision.

Principles:

- **Preserve the reasoning chain.** Record what changed, why, what
  alternatives were considered, and what evidence supported the choice.
  An AI agent that sees "we rejected approach X because of constraint Y"
  will not waste a session re-proposing X.
- **Prefer granular commits over squashed blobs.** A well-structured
  sequence of 4 commits teaches more than 1 squashed commit with a bullet
  list. Default to `Rebase and merge`; reserve `Squash and merge` for
  branches whose intermediate commits are unsalvageable noise.
- **Keep context in git, not only on GitHub.** PR discussions, review
  feedback, and design context must be distilled into the merge commit
  message or individual commit bodies, because `git log` works offline
  and survives forks — GitHub PR threads do not.
- **Make history searchable.** Use consistent Conventional Commit types,
  scopes, and keywords so `git log --grep` and AI semantic search return
  focused results.
- **Tag decision boundaries.** Annotated release tags mark the point where
  a set of changes was considered stable. Tag messages summarize what
  shipped and why, giving AI agents a coarse-grained timeline.

## Branch Strategy

- `main` is the release branch and should always be releasable.
- `develop` is the integration branch for reviewed work that is not yet released.
- Contributors should open short-lived feature or fix branches from `develop`.
- Do not push directly to `main` or `develop` except for urgent maintainer-only repository administration.
- Default to `Rebase and merge` for pull requests into `develop` so that every individual commit — and its reasoning — is preserved in the public history. Use `Squash and merge` only when the branch contains exploratory or fixup commits that add no lasting value; when squashing, the single merge commit must capture all essential context from the branch (see Commit Message Style).
- Avoid GitHub merge commits for routine pull requests because they create noisy branch divergence and a less readable graph.
- Promote releases from `develop` to `main` with a maintainer-run fast-forward update so both branches share identical history.
- Tag every release on `main` with an annotated tag (`git tag -a v0.1.0 -m "..."`). The tag message should summarize what shipped, key decisions made since the prior release, and any known limitations. Annotated tags are git objects — they survive cloning and forking, unlike GitHub-only release notes.

## Commit Message Style

Use Conventional Commits for public history. The preferred format is:

```text
type(scope): short imperative summary
```

For non-trivial changes, include the full body template so git history
serves as **engineering memory** — future contributors (and LLMs) can
reconstruct the reasoning behind every decision:

```text
type(scope): short imperative summary

INTENTION:
Why this change exists and what engineering principle it serves.
Connect to the broader goal so future readers understand the
"why behind the why."

WHAT CHANGED:
- Concise bullet list of specific changes
- Group by file or area when helpful

WHY:
Context that connects this change to the codebase's evolution.
What was wrong or missing before, and how this moves the project
forward.

ALTERNATIVES CONSIDERED:
- Option A: description — rejected because <reason>
- Option B: description — rejected because <reason>
(Omit when no meaningful alternatives exist. Include whenever a
design choice was made — this prevents future contributors and
AI agents from re-proposing already-rejected approaches.)

REFS:
- Closes #<issue>
- Related: <short-sha> (<one-line summary>)
- Follows up on: <short-sha>
(Omit when no related items apply. These cross-references let
AI agents trace reasoning chains across multiple commits.)

VERIFIED:
- What was tested or checked before committing
- Which checks were intentionally skipped and why
```

Examples:

```text
feat(cli): add agent filter for init command
fix(scaffold): handle missing tests directory on Windows
docs(readme): clarify GitHub merge strategy
test(cli): cover invalid agent option
ci(codeql): upgrade action to v4
refactor(scripts): simplify test result parsing
```

Full body example:

```text
refactor(scripts): align scaffold and runner to component-prefixed naming

INTENTION:
The plugin provides generic building blocks that the LLM customises to
the user's actual codebase. If the building blocks themselves use
inconsistent naming, the LLM inherits those inconsistencies. This commit
enforces the component-prefixed env var convention across all scripts.

WHAT CHANGED:
- scaffold.py: ENV_EXAMPLE_TEMPLATE uses ORDERS_API_BASE_URL, not
  API_BASE_URL; removed fake AWS creds (conftest handles those)
- run_tests.py: removed non-prefixed API_BASE_URL gate check; E2E
  tests now self-skip via pytest.skip()

WHY:
Previous iterations added component-prefixed naming to all skill docs
but scaffold.py and run_tests.py still assumed a single global
API_BASE_URL. This mismatch would confuse an LLM generating tests
for a real monorepo project.

ALTERNATIVES CONSIDERED:
- Keep a single global API_BASE_URL and add per-component overrides —
  rejected because it creates ambiguity about which variable the LLM
  should reference in generated tests.

REFS:
- Follows up on: a1b2c3d (docs: add component-prefixed env vars to skills)

VERIFIED:
- All 19 existing tests pass (pytest tests/ -v)
- No remaining non-prefixed API_BASE_URL in os.getenv() calls
```

Guidelines:

- Use one of: `feat`, `fix`, `docs`, `refactor`, `test`, `ci`, `chore`, `build`, `perf`.
- Use a scope when it helps reviewers understand the affected area, for example `cli`, `readme`, `skills`, `tests`, `scaffold`, or `ci`.
- Write the summary in imperative mood: `add`, `fix`, `update`, not `added` or `fixed`.
- Keep the subject line short and specific. A good target is under 72 characters.
- Do not end the subject line with a period.
- If the change is breaking, use `!` after the type or scope and explain it in the body.
- For trivial changes (typo fixes, formatting), the subject line alone is sufficient — skip the body.
- For anything that changes behaviour, adds a feature, or fixes a bug, include at least INTENTION and WHAT CHANGED.
- Include ALTERNATIVES CONSIDERED whenever a design choice was made between two or more viable options. This is the single most valuable section for AI memory — it prevents circular re-discovery of rejected approaches.
- Include REFS when the commit relates to an issue, continues work from a prior commit, or responds to review feedback. Short SHAs and issue numbers create a navigable graph that AI agents can traverse with `git log --grep`.
- When a commit is generated or substantially assisted by an AI agent, add a `Co-authored-by: <agent-name>` trailer or note `AI-assisted: <tool>` in the body so future readers can calibrate trust and understand the commit's provenance.

## Pull Request Style

Treat the pull request as the public review record — but remember that
PR threads live on GitHub, not in git. Any context that matters long-term
must also land in the commit messages that enter `develop`.

- Keep each pull request focused on one concern.
- Use a PR title that follows the same Conventional Commit style as the final merge commit.
- In the description, explain the problem, the approach, the risk level, and alternatives that were considered.
- List the validation you ran and any checks you intentionally did not run.
- Call out follow-up work instead of mixing it into the same PR.
- Avoid noisy history such as merge commits, fixup chains, or exploratory commit messages in public branches.
- Treat contributor pull requests as changes into `develop`; release promotion to `main` is a maintainer operation, not the standard contributor PR flow.
- **Before merging**, verify that the commit message(s) entering `develop` contain all essential reasoning from the PR discussion. If review feedback changed the approach, update the relevant commit body to reflect the final rationale — do not leave the reasoning only in GitHub comments. `git log` is the AI agent's primary context source; PR comments are supplementary.
- When using `Squash and merge`, the single resulting commit message must consolidate context from all individual commits and the PR discussion into the full INTENTION / WHAT CHANGED / WHY / ALTERNATIVES CONSIDERED / REFS / VERIFIED template.

## Submitting Changes

1. Fork the repo
2. Create a feature branch from `develop`: `git checkout -b feat/new-pattern origin/develop`
3. Make your changes
4. Rebase your branch on the latest `origin/develop` before opening or updating the pull request
5. Run local quality checks: `uv run pytest tests/ -v`, `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy src`, `uv run bandit -q -c pyproject.toml -r src`, and `uv run pip-audit`
6. Submit a pull request to `develop` using `.github/pull_request_template.md`
7. Merge pull requests with `Rebase and merge` (preferred — preserves individual commit reasoning) or `Squash and merge` (only when intermediate commits are noise); do not use merge commits
8. Release `develop` to `main` with a maintainer-run fast-forward update after CI passes on `develop`; use `git merge --ff-only develop` from a local checkout of `main` so `main` advances without rewriting or duplicating commit history
9. Review responsibility is assigned through `.github/CODEOWNERS`

## Maintainer Notes

- Protect `main` and `develop` against direct pushes.
- Enable `Rebase and merge` (preferred) and `Squash and merge` (fallback) for contributor pull requests into `develop`. Disable `Create a merge commit` to enforce linear history.
- Do not rely on GitHub merge buttons for release promotion to `main`; use a local `git merge --ff-only develop` followed by `git push origin main`.
- Configure `develop` branch protection or rulesets to require linear history and the CI checks `Test (Python 3.10)`, `Test (Python 3.11)`, `Test (Python 3.12)`, `Test (Python 3.13)`, `Lint`, `Type Check`, and `Security`.
- Configure `main` so only maintainers can update it, with no force pushes or deletions.
- Keep release updates focused. Avoid mixing repository governance, experiments, and product changes in the same release.
- Do not rewrite shared branch history unless there is a clear operational reason and the change is communicated.
- After each fast-forward update to `main`, create an annotated tag and push it:
  ```bash
  git tag -a v<VERSION> -m "v<VERSION>: <one-line theme>

  WHAT SHIPPED:
  - Key changes since the prior release

  KEY DECISIONS:
  - Significant design choices made in this release cycle

  KNOWN LIMITATIONS:
  - Open issues or deferred work"
  git push origin v<VERSION>
  ```
