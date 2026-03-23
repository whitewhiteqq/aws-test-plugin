## Summary

- Describe the change clearly.
- Link any issue, task, or discussion if relevant.
- Use a PR title in conventional format when possible, for example `feat(cli): add agent filter`.
- State the problem, the approach, and any important tradeoffs.

## PR Target

- [ ] This PR targets `develop`

## History Hygiene

- [ ] My branch is rebased on the latest target branch
- [ ] This PR is intended for `Rebase and merge` or `Squash and merge`
- [ ] I did not add merge commits to this branch unless a maintainer explicitly requested it

## Validation

- [ ] `uv run pytest tests/ -v`
- [ ] `uv run ruff check src tests`
- [ ] `uv run ruff format --check src tests`
- [ ] `uv run mypy src`
- [ ] `uv run bandit -q -c pyproject.toml -r src`
- [ ] `uv run pip-audit`

## Risk Review

- [ ] No secrets, credentials, or private data were added
- [ ] Documentation was updated if behavior or workflow changed
- [ ] CI should pass for this branch before merge

## Notes For Reviewers

- Call out any areas that need special attention.
- Note any follow-up work that is intentionally out of scope.
- Mention whether the final merge should be `Rebase and merge` or `Squash and merge` if maintainers need guidance.
