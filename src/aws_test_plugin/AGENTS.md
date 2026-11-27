# AWS Test Plugin: agent instructions

This project uses `aws-test-plugin` skills for AWS Python tests, including Lambda,
API Gateway, Step Functions, and Batch.

## Choose the existing workflow first

1. Read the repository instructions, tests, fixtures, dependency locks, and CI.
2. Use the component's Python environment and test commands. Preserve its layout.
3. Read the selected handler, event schema, and service calls before generating tests.
4. Generate and run only the requested components and test categories.
5. Report what executed, passed, failed, or skipped. Missing required tests are incomplete.

The six installed skills contain category-specific patterns and reference files.
For AWS Emulator, use the integration skill's `references/aws-emulator.md`.
Run a separately selected emulator suite with its generated credentials and CA;
the packaged offline runner overwrites credentials with fake keys.
Codex discovers these under `.agents/skills/`. Other supported hosts use their
native project skill directories. This file supplements existing project rules.

## Test categories

| Category | Tool | Deployed access |
|----------|------|-----------------|
| Unit | pytest and mocks | No |
| Integration | moto, testcontainers, or AWS Emulator | No deployed AWS access |
| Contract | jsonschema and pytest | No |
| Performance | pytest-benchmark | No for mocked local benchmarks |
| E2E | requests or boto3 | Yes |
| Load | Locust | Yes |

## Commands for projects without an existing harness

Install the plugin into the project's Python environment before using its modules.
Use the existing project harness when available.

```bash
aws-test-plugin scaffold .
python -m aws_test_plugin.scripts.run_tests all
python -m aws_test_plugin.scripts.run_tests unit
python -m aws_test_plugin.scripts.analyze_results tests/reports/

# Deployed tests: select the target and permitted operations first.
python -m aws_test_plugin.scripts.run_tests e2e
python -m aws_test_plugin.scripts.run_tests load --base-url https://test.example --users 50 --duration 5m
```

`all` runs offline categories in separate processes. `full` also runs E2E and can
write deployed resources. `--base-url` applies only to load tests; E2E reads the
project's component-specific configuration. Missing suites are not passes.

## Safety and secrets

- Use fake AWS credentials with moto or service stubs for offline tests.
  Configure them before importing handlers. Fake keys alone do not block requests.
- Keep deployed credentials and `.env` loading out of shared offline fixtures.
- Keep AWS Emulator fixtures separate from mocked tests. Verify the local endpoint
  and emulator identity before tests; preserve HTTPS and request authentication.
- Select the AWS profile or CI role, expected account, region, and resource targets
  before deployed tests. Use the project's existing verification procedure.
- Never run E2E or load tests against production without explicit confirmation.
- Keep API secrets in ignored local environment files or Secrets Manager/SSM.
  Never print them in reports or hardcode them in tests.
- Bound load duration. Clean up only resources created and recorded by this run.
- Follow the orchestrator's `references/secrets-and-config.md` for configuration examples.
