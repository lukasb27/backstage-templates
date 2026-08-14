# Agent Guide

## Quality bar

- Prefer logical, maintainable code over brevity or cleverness.
- Keep module boundaries clean: routes in `app/routers`, shared dependencies in
  `app/dependencies.py`.
- Add or update automated tests for every feature change and every behavior change.
- Keep all Python code `flake8` compliant.
- Add type hints for new or changed function signatures.

## Testing expectations

- Unit tests (`tests/`, `-m "not e2e"`) run fast, no external boundaries.
- E2E tests (`tests/`, `-m e2e`) exercise the FastAPI app in-process via `httpx`.
- `integration_tests/` is different from both — it runs **inside the cluster**, as a
  Kubernetes Job, against the real deployed Service over its DNS name
  (`TARGET_HOST`). It's not run locally or in CI directly; it only runs once a PR's
  ephemeral environment is actually healthy. Don't hardcode the target host there —
  it's injected as an env var by `k8s/job.yaml` on purpose, so this file stays out of
  the scaffolder's template-rendering path.

## Workflow

- Before making any commit, always create a new branch first. Never commit directly
  onto whatever branch happens to already be checked out.
- Always branch from `main`, never from another unmerged branch — no stacked
  branches/PRs. This repo merges via squash, which rewrites history on merge; a
  branch stacked on an unmerged branch loses its common ancestor with `main` the
  moment that branch merges, turning a small diff into add/add conflicts on every
  file the stack touched.
- Make focused commits using Conventional Commits: `type(scope): summary`, where
  `type` is one of `build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test` —
  the exact set `.github/workflows/actions.yml` enforces on both the PR title and
  every commit subject.
- Before committing, run `poetry run pytest -m "not e2e"` and `poetry run flake8
  app/ tests/`.
- Before opening a pull request, wait for `ci` and `docker` to pass, and check the
  ephemeral environment's `kubernetes/integration-tests` status once it reports —
  it's the only check that exercises the real deployed service.

## Pull requests

- PR titles must follow Conventional Commits — squash merges use the PR title, and
  release-please reads it to decide the next version.
- `ci` and `docker` must pass before merge (both are required status checks).
  `pr-review` and `kubernetes/integration-tests` are advisory — read them, but they
  don't block.
