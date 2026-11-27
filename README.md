# aws-test-plugin

AI agent skills for generating comprehensive tests for **any AWS Python project** — Lambda, API Gateway, Step Functions, and Batch.

Works with **Claude Code**, **GitHub Copilot**, **OpenAI Codex**, **CodeBuddy**, and **Qoder**.

## What It Does

Install this plugin into your AWS project, and your AI coding agent can:

- **Discover** all Lambdas, Batch jobs, Step Functions, and API specs in your repo
- **Read handler code** to understand branches, AWS calls, validation rules, error handling
- **Generate tests** covering every code path — not just happy-path templates
- **Run & fix** — execute tests, parse failures, fix root causes, re-run until green

### Test Types

| Type | Tool | Needs Deploy? |
|------|------|:---:|
| Unit | pytest + mocks | No |
| Integration | moto, testcontainers, or AWS Emulator + pytest | No |
| Contract | jsonschema + pytest | No |
| Performance | pytest-benchmark | No |
| E2E | requests + pytest | Yes |
| Load | Locust | Yes |

### AWS Components Covered

| Component | Integration | E2E | Contract | Perf | Load |
|-----------|:-----------:|:---:|:--------:|:----:|:----:|
| API Gateway + Lambda | ✓ | ✓ | ✓ | ✓ | ✓ |
| Step Functions | ✓ | ✓ | ✓ | ✓ | |
| Batch Jobs | ✓ | ✓ | | ✓ | |
| Lambda + DynamoDB | ✓ | | | ✓ | |
| Lambda + S3 | ✓ | | | | |
| Lambda + RDS/PostgreSQL | ✓ | | | | |

## Installation

### Option 1: Claude Code Plugin (recommended for Claude Code users)

This repo is a native Claude Code plugin. Install it directly:

```bash
# Test locally — load the plugin for one session
claude --plugin-dir /path/to/aws-test-plugin
```

After loading, skills are namespaced as `/aws-test-plugin:aws-test-orchestrator`, etc.
Use `/reload-plugins` to pick up changes during development.

### Option 2: `npx skills add`

This third-party installer runs code from npm. For repeatable setup, select a
reviewed CLI version with `npx skills@<reviewed-version>` and a reviewed source
revision. The Python CLI below installs the same skills without this npm tool.

```bash
# Install skills into your project — auto-detects Claude Code, Copilot, Codex
npx skills add whitewhiteqq/aws-test-plugin
```

Flags:

```bash
npx skills add whitewhiteqq/aws-test-plugin --skill aws-e2e-testing   # Single skill
npx skills add whitewhiteqq/aws-test-plugin --list                    # List skills
npx skills add whitewhiteqq/aws-test-plugin -a qoder                  # Qoder only
npx skills add whitewhiteqq/aws-test-plugin -g                        # Install globally
```

### Option 3: `uv` (with CLI tools)

```bash
# Install the CLI tool globally (isolated venv, auto-managed by uv)
uv tool install git+https://github.com/whitewhiteqq/aws-test-plugin

# Then install skills into your project
cd your-aws-project
aws-test-plugin init .
```

### Option 4: `pip`

```bash
pip install git+https://github.com/whitewhiteqq/aws-test-plugin
cd your-aws-project
aws-test-plugin init .
```

### Option 5: Manual copy

```bash
git clone https://github.com/whitewhiteqq/aws-test-plugin.git
cd your-aws-project

# For Claude Code
cp -r aws-test-plugin/skills/*  .claude/skills/
cp -r aws-test-plugin/agents/*  .claude/agents/

# For GitHub Copilot
cp -r aws-test-plugin/skills/*  .github/skills/
cp -r aws-test-plugin/agents/*  .github/agents/
```

### Install test dependencies

```bash
# All test deps at once
pip install "aws-test-plugin[all] @ git+https://github.com/whitewhiteqq/aws-test-plugin"

# Or just what you need
pip install "aws-test-plugin[test] @ git+https://github.com/whitewhiteqq/aws-test-plugin"   # moto + pytest
pip install "aws-test-plugin[load] @ git+https://github.com/whitewhiteqq/aws-test-plugin"   # Locust
pip install "aws-test-plugin[db] @ git+https://github.com/whitewhiteqq/aws-test-plugin"     # testcontainers
pip install "aws-test-plugin[perf] @ git+https://github.com/whitewhiteqq/aws-test-plugin"   # pytest-benchmark
```

## CLI Commands

```bash
# Install skills for all five agents
aws-test-plugin init .

# Install for specific agents only
aws-test-plugin init . --agent claude
aws-test-plugin init . --agent copilot
aws-test-plugin init . --agent codebuddy
aws-test-plugin init . --agent qoder
aws-test-plugin init . --agent codex

# List available skills
aws-test-plugin list

# Scaffold test directories (discovers Lambdas, creates conftest.py, pytest.ini)
aws-test-plugin scaffold .
```

Repeat `--agent` to select several agents. The default installs for all five.
Existing files are preserved. Re-running `init` adds missing files; it does not
replace customized or older skill files. Review installed copies when upgrading.

CodeBuddy and Qoder use their native project skill directories, as documented by
[CodeBuddy](https://www.codebuddy.ai/docs/cli/skills) and
[Qoder](https://docs.qoder.com/extensions/skills). Restart or reload the host's
skills after installation. These integrations share the same six skills and
reference files. Their custom agent definitions are not installed.

## What Gets Installed

Running `aws-test-plugin init .` installs six skills and their references:

| Agent | Project skills | Additional files |
|-------|----------------|------------------|
| Claude Code | `.claude/skills/` | `.claude/agents/aws-test-engineer.md` |
| GitHub Copilot | `.github/skills/` | `.github/agents/aws-test-engineer.md` |
| OpenAI Codex | `.agents/skills/` | `AGENTS.md`, if absent |
| CodeBuddy | `.codebuddy/skills/` | None |
| Qoder | `.qoder/skills/` | None |

## Usage

After installing, ask your AI agent:

| Request | What Happens |
|---------|-------------|
| "Write integration tests for my Lambda" | Reads handler code → generates moto tests for all branches |
| "Test my workflow with AWS Emulator" | Checks operation fidelity, configures the local backend, and generates emulator tests |
| "Create E2E tests for my API" | Finds spec → reads handlers → generates endpoint tests |
| "Test my Step Function" | Finds ASL definition → reads state handlers → tests flow |
| "Benchmark my handler" | Reads handler → mocks deps → pytest-benchmark tests |
| "Load test my API at 100 users" | Reads spec → generates Locust users with weighted endpoints |
| "Scaffold test directories" | Creates `tests/` with conftest.py, pytest.ini, layout |
| "What's not tested?" | Compares code paths vs existing tests → reports gaps |

The agent first reads your repository instructions, existing tests, fixtures,
dependency locks, and CI commands. It keeps your layout and requested scope.
Scaffolding is optional and preserves existing pytest configuration. Discovery
skips common environment, dependency, cache, build, and test directories.

For projects without a test runner, install the plugin into the project's Python
environment and use `python -m aws_test_plugin.scripts.run_tests all` for offline
categories. This runner supplies fake AWS credentials before test collection and
does not load `.env` for offline runs. Use moto or service stubs to prevent real
service calls. Fake credentials alone do not block network access.

`e2e`, `full`, and `load` can access deployed resources. Select the target,
AWS identity, region, and permitted operations before running them. `--base-url`
applies only to `load`; E2E uses the project's component-specific configuration.
Missing suites and empty collections do not count as passes. The report analyzer
also reports empty or entirely skipped JUnit suites as incomplete.
The runner owns JUnit output under `tests/reports/`, including when `--extra`
contains another JUnit output option.

### Optional AWS Emulator tests

The integration skill supports [AWS Emulator](https://docs.aws.amazon.com/emulator/latest/userguide/getting-started-agent.html)
for local AWS API workflows. Read its
[emulator reference](skills/aws-integration-testing/references/aws-emulator.md)
for compatibility checks, reviewed setup, generated credentials, and HTTPS.
Run emulator tests separately with the project's command or direct pytest.
The packaged offline runner supplies fake keys that the emulator rejects.
Emulator setup is optional; it adds no plugin dependency or automatic installer.

## How Test Generation Works

This plugin doesn't fill in templates — it reads your **actual code** and generates tests based on:

1. **Handler signatures** — event shapes, input parameters
2. **Branching logic** — if/else, try/except → one test per code path
3. **AWS service calls** — identify boto3 operations and test the selected local backend
4. **Validation rules** — pydantic models, manual checks → test valid + invalid
5. **Error handling** — exceptions caught/raised → verify error responses
6. **Return shapes** — response structures → contract assertions
7. **Environment deps** — env vars → set up in fixtures

## Skills Included

| Skill | Triggers When You Say | Reference Patterns |
|-------|----------------------|------------|
| `aws-test-orchestrator` | "test my project", "set up testing" | — |
| `aws-unit-testing` | "unit tests", "branch coverage", "boundary tests" | Branches, boundaries, edge cases |
| `aws-e2e-testing` | "E2E tests", "endpoint tests" | API Gateway, Step Function, Batch |
| `aws-integration-testing` | "integration tests", "moto tests", "AWS Emulator" | S3, DynamoDB, RDS/PostgreSQL, emulator setup |
| `aws-contract-testing` | "contract tests", "schema validation" | OpenAPI validation |
| `aws-perf-load-testing` | "benchmark", "load test", "Locust" | Benchmark, Locust |

## Agent Compatibility

All five agents receive portable `SKILL.md` files with reference material loaded
as needed. Claude Code also supports the native `.claude-plugin/` distribution.
The Python installer copies custom agent definitions only for Claude Code and
GitHub Copilot. Codex, CodeBuddy, and Qoder use their native skill discovery.

## Project Structure

```
aws-test-plugin/
├── .claude-plugin/
│   └── plugin.json               # Claude Code plugin manifest
├── CLAUDE.md                     # Agent instructions (Claude Code / Copilot)
├── pyproject.toml                # uv/pip package config
├── uv.lock                       # Locked dependency graph (never stale)
├── LICENSE                       # Apache 2.0
├── README.md
├── CONTRIBUTING.md
├── .python-version               # 3.12
├── skills/                       # Plugin skills (Claude Code auto-discovers)
│   ├── aws-test-orchestrator/SKILL.md
│   ├── aws-unit-testing/
│   │   ├── SKILL.md
│   │   └── references/           # branches, boundaries, edge cases
│   ├── aws-e2e-testing/
│   │   ├── SKILL.md
│   │   └── references/           # api-gateway, step-function, batch
│   ├── aws-integration-testing/
│   │   ├── SKILL.md
│   │   └── references/           # S3, DynamoDB, RDS
│   ├── aws-contract-testing/
│   │   ├── SKILL.md
│   │   └── references/           # OpenAPI patterns
│   └── aws-perf-load-testing/
│       ├── SKILL.md
│       └── references/           # benchmark, Locust
├── agents/
│   └── aws-test-engineer.md      # Agent definition
├── src/
│   └── aws_test_plugin/
│       ├── __init__.py
│       ├── cli.py                # aws-test-plugin CLI
│       ├── AGENTS.md             # Bundled Codex instructions
│       └── scripts/
│           ├── scaffold.py       # Auto-discover project & create test dirs
│           ├── run_tests.py      # Run tests by category
│           └── analyze_results.py # Parse JUnit/Locust/benchmark output
└── tests/
    └── test_cli.py
```

## Development

```bash
git clone https://github.com/whitewhiteqq/aws-test-plugin.git
cd aws-test-plugin

# Install with uv (creates .venv automatically)
uv sync --locked --group build --no-build --no-install-project

# Run tests
uv run --no-sync pytest tests/ -v

# Lint
uv run --no-sync ruff check src tests
uv run --no-sync ruff format --check src tests

# Type checking — ty is the primary checker (fast, replaces mypy)
uv run --no-sync ty check src

# Type checking — mypy (secondary; kept for compatibility)
uv run --no-sync mypy src

# Security scans
uv run --no-sync bandit -q -c pyproject.toml -r src
uv audit --locked --no-build

# Verify lockfile is up to date (must pass before any commit)
uv lock --check --no-build

# Regenerate lockfile when pyproject.toml changes
uv lock --no-build
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.


## Review Flow

- Pull requests should target `develop`; maintainers promote `develop` to `main` with a fast-forward release update.
- PyPI publishing is triggered by creating a GitHub Release targeting an annotated `v*` tag on `main`.
- Review ownership is defined in `.github/CODEOWNERS`.
- Pull request expectations are defined in `.github/pull_request_template.md`.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) 0.13.10+ (recommended) or pip

## Dependency and release security

- The CLI has one runtime dependency, `defusedxml`, for safe XML parsing.
  Install only the test extras you need. The `test` extra includes Moto support
  for S3, DynamoDB, SQS, SNS, EventBridge, and Kinesis. Add other Moto service
  extras in your project when needed.
- This repository locks dependencies and build tools with hashes and a 14-day
  package cooldown. Consumer projects must maintain their own locks. Review and
  pin Git installs to a commit you trust rather than following a moving branch.
- CI uses commit-pinned actions and wheel-only dependency installation. It audits
  every dependency group and optional extra without executing dependency builds.
  Weekly scans detect advisories published after an update.
- Audits use the built-in `uv audit` command, which includes all groups and extras.
  This preview command is tested with the exact uv version pinned in CI. Using it
  avoids a separate scanner dependency tree. Sync also checks known malware
  statuses through uv's audit service.
- Release builds use locked build tools. A separate publishing job gets the
  PyPI OIDC permission and attests the resulting artifacts. Releases require an
  annotated version tag on `main` history.
- `uv` 0.13.10 is an explicit security update for
  [GHSA-vjvj-3m3f-fgmm](https://github.com/astral-sh/uv/security/advisories/GHSA-vjvj-3m3f-fgmm).
  The package cooldown remains enabled. Scans identify known vulnerabilities;
  they cannot prove that a dependency is free of malicious code.

## License

Apache 2.0 — see [LICENSE](LICENSE)
