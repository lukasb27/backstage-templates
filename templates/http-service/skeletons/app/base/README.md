# ${{ values.name }}

${{ values.description }}

Scaffolded from the [http-service](https://github.com/lukasb27/backstage-templates)
golden-path template. See [docs/architecture.md](docs/architecture.md) for how the
pieces fit together — this repo, the control repo, and the referenced
`ephemeral-env.yml` workflow.

## One-time setup

Three secrets aren't provisioned automatically (no custom scaffolder action in v1 —
see the plan's Secrets decision) and need setting once per new service:

```
gh secret set ANTHROPIC_API_KEY --repo lukasb27/${{ values.name }}
gh secret set ARGO_CD_REPO_TOKEN --repo lukasb27/${{ values.name }}
gh secret set RELEASE_PLEASE_TOKEN --repo lukasb27/${{ values.name }}
```

- `ANTHROPIC_API_KEY` — `pr-review.yml` and `claude-issue-triage.yml`
- `ARGO_CD_REPO_TOKEN` — write access to `application-argocd-control`, used by
  the referenced `ephemeral-env.yml` workflow and by `cleanup.yml`
- `RELEASE_PLEASE_TOKEN` — a PAT (not the default `GITHUB_TOKEN`) so release-please's
  merge commit to `main` actually triggers `docker.yml`

## Local development

```
poetry install
poetry run uvicorn app.main:app --reload
```

## Repositories

| Repo | Holds |
| --- | --- |
| This repo | Application code, Dockerfile, `k8s/` base, CI |
| [application-argocd-control](https://github.com/lukasb27/application-argocd-control) | The Argo CD `Application` for `main`, and one per open PR |
| [backstage-templates](https://github.com/lukasb27/backstage-templates) | The template this was scaffolded from, and the `ephemeral-env.yml` workflow this repo's CI calls by version |
