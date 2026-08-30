# Repository settings

GitHub branch protection and rulesets live outside the repository, so they
cannot be enforced by a workflow file alone. Configure the default branch with
the following settings after importing or transferring the repository.

## Required pull-request rules

- Require a pull request before merging and dismiss stale approvals when new
  commits are pushed.
- Require at least one approving review. Require code-owner review if a
  `CODEOWNERS` file is added for a team-owned deployment.
- Require branches to be up to date before merging.
- Require conversation resolution.
- Prevent force pushes and branch deletion.
- Apply the rules to administrators; use a documented break-glass process for
  production incidents.

Require these stable status-check names from `.github/workflows/ci.yml`:

- `Quality`
- `dbt (dev)`
- `dbt (prod)`
- `orchestration`

The workflow runs on every branch push and pull request. Do not rename a job
without updating the repository ruleset, because GitHub identifies required
checks by their displayed name.

## Merge and security settings

- Allow squash merges and automatically delete merged branches.
- Enable Dependabot alerts and security updates.
- Enable secret scanning and push protection where the repository plan permits.
- Keep Actions permissions read-only by default and grant write permissions to
  an individual job only when it needs them.

These settings are an operator checklist, not evidence that protection is
currently enabled. Verify the active ruleset in GitHub before treating the
default branch as protected.
