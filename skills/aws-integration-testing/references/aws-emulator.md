# Test AWS workflows with AWS Emulator

Use AWS Emulator for explicitly selected local integration tests. Keep existing
moto tests for in-process mocks and deployed tests for behavior that needs AWS.

## Check the workflow before setup

List the AWS operations and resources the selected tests use. Check those
operations against the selected release's fidelity scores and evaluation tests.
A service name alone does not establish support for its workflows. See AWS's
[project compatibility guide](https://docs.aws.amazon.com/emulator/latest/userguide/check-project.html)
and [fidelity guide](https://docs.aws.amazon.com/emulator/latest/userguide/fidelity.html).

Keep IAM, resource-policy, and cross-account security assertions on AWS. The
emulator does not establish their enforcement. Use one account and Region per
instance. It is not a target for production, load tests, or deployed latency
claims. See the [limitations](https://docs.aws.amazon.com/emulator/latest/userguide/what-is-service.html).

## Prepare a reviewed local instance

- Reuse an installed, reviewed official `aws-emulator` skill when available.
  AWS CLI 2.35.0 or later is needed for its Agent Toolkit installation path.
  The skill is optional; these tests do not require a second agent plugin.
  [AWS's agent guide](https://docs.aws.amazon.com/emulator/latest/userguide/getting-started-agent.html)
  describes that path. Toolkit installs default to the latest skill globally
  across detected agents. Review a pinned version and select the intended agent
  before installation; follow the environment's installation checks. See
  [Toolkit skill management](https://docs.aws.amazon.com/agent-toolkit/latest/userguide/aws-cli.html).
- On Linux, use a versioned official package and verify its signature as shown
  in the [Linux guide](https://docs.aws.amazon.com/emulator/latest/userguide/getting-started-linux.html).
  On Windows and macOS, follow the [Docker guide](https://docs.aws.amazon.com/emulator/latest/userguide/getting-started-docker.html).
  AWS does not publish a prebuilt emulator image. Pin the reviewed base image and
  verified package when building one; avoid unattended mutable `latest` downloads.
- Keep authentication and certificate verification enabled. Publish Docker ports
  on `127.0.0.1` and mount only the emulator's directory, not the whole AWS
  credentials directory. Keep the host and container API ports equal. Publish
  separate resource ports only when the selected workflow needs them.

After a reviewed Linux installation, this starts a bounded local instance:

```bash
aws-emulator --bind 127.0.0.1 --port 9297 --auth on --telemetry off --idle-timeout 300
```

For Docker, keep the container's bind address at `0.0.0.0` and publish its ports
on host `127.0.0.1`. Pass `--port 9297 --auth on --telemetry off --idle-timeout 300`
after the image name in AWS's documented run command. Record the selected version.
Run only trusted application code. The emulator is not a sandbox for function code. See
[emulator security](https://docs.aws.amazon.com/emulator/latest/userguide/security.html).

## Configure the selected test process

Use a separate shell or test job. Set the following before importing handlers.
The run directory is `~/.aws/emulator/9297/` on the host for the example above.
On Windows it is under `%USERPROFILE%\.aws\emulator\9297\`. Read the current
instance's startup output and use its port and generated files.

| Variable | Value for this instance |
|----------|-------------------------|
| `AWS_ENDPOINT_URL` | `https://127.0.0.1:9297` |
| `AWS_SHARED_CREDENTIALS_FILE` | Run directory's `emulator_credentials` |
| `AWS_CONFIG_FILE` | Run directory's `config` |
| `AWS_CA_BUNDLE` | Run directory's `ca.pem` |
| `AWS_EC2_METADATA_DISABLED` | `true` |
| `AWS_DISABLE_HOST_PREFIX_INJECTION` | `true` |
| `AWS_REGION` | `us-east-1` |
| `AWS_DEFAULT_REGION` | `us-east-1` |

Clear inherited `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`,
`AWS_SECURITY_TOKEN`, `AWS_PROFILE`, and `AWS_DEFAULT_PROFILE` in this process.
Use the generated credentials file; both real AWS keys and moto's `testing`
keys are wrong for this instance. Keep deployed credentials and roles out of
the job. Remove conflicting service-specific `AWS_ENDPOINT_URL_*` settings and
`AWS_IGNORE_CONFIGURED_ENDPOINT_URLS`. Inspect application client overrides too.
Before resource creation, assert that each selected Boto3 client's
`meta.endpoint_url` matches the chosen emulator endpoint.

Trust the generated CA with `AWS_CA_BUNDLE`. Keep `127.0.0.1` as the hostname
for S3 and disable host-prefix injection for Boto3. Restore normal settings by
ending this shell or job. AWS provides
[SDK setup examples for both shells](https://docs.aws.amazon.com/emulator/latest/userguide/point-sdk-to-emulator.html).

## Run the emulator suite separately

1. Wait with a bounded timeout for HTTPS `GET /__admin/health` to return `200`
   and `ok`, using the generated CA. Connection, TLS, and signature failures
   require a setup fix; do not disable verification or authentication.
2. In the configured process, check identity with an explicit local endpoint:

   ```bash
   aws --endpoint-url https://127.0.0.1:9297 sts get-caller-identity
   ```

   Expect account `000000000000` and ARN `arn:aws:iam::000000000000:user/emulator`.
   Stop on another identity. Never fall back to real AWS.
3. Reuse the project's emulator command and suite isolation. For a new suite,
   use a separately selected directory such as `tests/emulator/`, outside the
   packaged runner's `tests/integration/`. Keep it out of default mocked-test
   collection. Scope emulator fixtures to that suite; do not apply moto or an
   autouse fake-credential fixture. Use only registered pytest markers.
4. Run the selected suite directly after configuration, for example:

   ```bash
   python -m pytest tests/emulator/ -v --junitxml=tests/reports/emulator_results.xml
   ```

   The packaged `run_tests integration`, `all`, and offline phase of `full`
   replace credentials with fake keys. Use the project command or direct pytest
   for signed emulator tests.
5. Report the backend, release, operations exercised, and executed, failed, and
   skipped tests. Treat unsupported operations such as `501 NotImplemented` as
   coverage gaps. Missing required coverage is incomplete, not a pass.
6. Stop only the instance started for this run. State is in memory; stopping or
   restarting loses its resources. Create fixtures for each run and restart for
   a clean instance. Do not invent a reset API or delete other instances' files.

The [command reference](https://docs.aws.amazon.com/emulator/latest/userguide/cli-reference.html)
documents startup output, health checks, generated files, and shutdown.
