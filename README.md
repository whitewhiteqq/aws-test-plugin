# aws-test-plugin

AI agent skills for generating comprehensive tests for **any AWS Python project** — Lambda, API Gateway, Step Functions, and Batch.

Works with **Claude Code**, **GitHub Copilot**, and **OpenAI Codex**.

## What It Does

Install this plugin into your AWS project, and your AI coding agent can:

- **Discover** all Lambdas, Batch jobs, Step Functions, and API specs in your repo
- **Read handler code** to understand branches, AWS calls, validation rules, error handling
- **Generate tests** covering every code path — not just happy-path templates
- **Run & fix** — execute tests, parse failures, fix root causes, re-run until green

### Test Types

| Type | Tool | Needs Deploy? |
|------|------|:---:|
| Integration | moto + pytest | No |
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

```bash
# Install skills into your project — auto-detects Claude Code, Copilot, Codex
npx skills add whitewhiteqq/aws-test-plugin
```

Flags:

```bash
npx skills add whitewhiteqq/aws-test-plugin --skill aws-e2e-testing   # Single skill
npx skills add whitewhiteqq/aws-test-plugin --list                    # List skills
npx skills add whitewhiteqq/aws-test-plugin -a copilot                # Copilot only
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
# Install skills for all agents (Claude Code + Copilot + Codex)
aws-test-plugin init .

# Install for specific agents only
aws-test-plugin init . --agent claude
aws-test-plugin init . --agent copilot

# List available skills
aws-test-plugin list

# Scaffold test directories (discovers Lambdas, creates conftest.py, pytest.ini)
aws-test-plugin scaffold .
```

## What Gets Installed

Running `aws-test-plugin init .` creates:

```
your-project/
├── .claude/                          # Claude Code
│   ├── skills/
│   │   ├── aws-test-orchestrator/    # Master skill: discover → delegate
│   │   ├── aws-e2e-testing/          # E2E patterns for API GW, SFN, Batch
│   │   ├── aws-integration-testing/  # moto patterns for S3, DDB, RDS
│   │   ├── aws-contract-testing/     # OpenAPI schema validation
│   │   └── aws-perf-load-testing/    # Benchmarks + Locust load tests
│   └── agents/
│       └── aws-test-engineer.md      # Agent definition
├── .github/                          # GitHub Copilot
│   ├── skills/  (same skills)
│   └── agents/  (same agent)
└── AGENTS.md                         # OpenAI Codex instructions
```

## Usage

After installing, ask your AI agent:

| Request | What Happens |
|---------|-------------|
| "Write integration tests for my Lambda" | Reads handler code → generates moto tests for all branches |
| "Create E2E tests for my API" | Finds spec → reads handlers → generates endpoint tests |
| "Test my Step Function" | Finds ASL definition → reads state handlers → tests flow |
| "Benchmark my handler" | Reads handler → mocks deps → pytest-benchmark tests |
| "Load test my API at 100 users" | Reads spec → generates Locust users with weighted endpoints |
| "Scaffold test directories" | Creates `tests/` with conftest.py, pytest.ini, layout |
| "What's not tested?" | Compares code paths vs existing tests → reports gaps |

## How Test Generation Works

This plugin doesn't fill in templates — it reads your **actual code** and generates tests based on:

1. **Handler signatures** — event shapes, input parameters
2. **Branching logic** — if/else, try/except → one test per code path
3. **AWS service calls** — which boto3 clients → mock them with moto
4. **Validation rules** — pydantic models, manual checks → test valid + invalid
5. **Error handling** — exceptions caught/raised → verify error responses
6. **Return shapes** — response structures → contract assertions
7. **Environment deps** — env vars → set up in fixtures

## Skills Included

| Skill | Triggers When You Say | Reference Patterns |
|-------|----------------------|------------|
| `aws-test-orchestrator` | "test my project", "set up testing" | — |
| `aws-e2e-testing` | "E2E tests", "endpoint tests" | API Gateway, Step Function, Batch |
| `aws-integration-testing` | "integration tests", "moto tests" | S3, DynamoDB, RDS/PostgreSQL |
| `aws-contract-testing` | "contract tests", "schema validation" | OpenAPI validation |
| `aws-perf-load-testing` | "benchmark", "load test", "Locust" | Benchmark, Locust |

## Agent Compatibility

| Feature | Claude Code | GitHub Copilot | OpenAI Codex |
|---------|:-----------:|:--------------:|:------------:|
| Native plugin system | ✓ `.claude-plugin/` | — | — |
| Skills auto-loaded | ✓ `skills/` | ✓ `.github/skills/` | — |
| Agent definitions | ✓ `agents/` | ✓ `.github/agents/` | — |
| Project instructions | ✓ `CLAUDE.md` | ✓ `AGENTS.md` | ✓ `AGENTS.md` |
| Marketplace distribution | ✓ plugin marketplace | — | — |
| Triggered by description | ✓ | ✓ | — |
| Reference files on-demand | ✓ | ✓ | — |

## Project Structure

```
aws-test-plugin/
├── .claude-plugin/
│   └── plugin.json               # Claude Code plugin manifest
├── pyproject.toml                # uv/pip package config
├── LICENSE                       # Apache 2.0
├── README.md
├── CONTRIBUTING.md
├── .python-version               # 3.12
├── skills/                       # Plugin skills (Claude Code auto-discovers)
│   ├── aws-test-orchestrator/SKILL.md
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
uv sync

# Run tests
uv run pytest tests/ -v

# Lint
uv run ruff check src/
uv run ruff format --check src/

# Type checking
uv run mypy src/

# Security scans
uv run bandit -q -c pyproject.toml -r src/
uv run pip-audit
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.


## Review Flow

- Pull requests should target `develop`; maintainers promote `develop` to `main` with a fast-forward release update.
- PyPI publishing happens only from an annotated `v*` tag pushed from `main` after that promotion.
- Review ownership is defined in `.github/CODEOWNERS`.
- Pull request expectations are defined in `.github/pull_request_template.md`.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## License

Apache 2.0 — see [LICENSE](LICENSE)
