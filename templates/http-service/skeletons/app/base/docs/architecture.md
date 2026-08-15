# Architecture

## Repositories

| Repo | Holds |
| --- | --- |
| This repo | Application code, Dockerfile, `k8s/` base, CI |
| [fermentation-station-argocd-control](https://github.com/lukasb27/fermentation-station-argocd-control) | The persistent Argo CD `Application` for `main`, and one per open PR |
| [backstage-templates](https://github.com/lukasb27/backstage-templates) | The template this repo was scaffolded from, and the `ephemeral-env.yml` reusable workflow this repo's CI calls by version (`@v1`) |

## Request path

See [backstage-templates' own architecture docs](https://github.com/lukasb27/backstage-templates/blob/main/docs/architecture.md)
for the full request-path diagram and explanation — what happens on every push,
end to end. It lives there rather than here because the flow is identical for
every service this template produces; documenting it once means it can't drift
out of sync with reality one scaffolded repo at a time.

## Day 2

This repo is yours from here — drift in application code, the Dockerfile, resource
values, tests, and docs is expected and correct. Two things are platform contract,
not this service's business:

1. **The template version** — the `goldenpath.lukasb27/template-version` annotation
   in `catalog-info.yaml` records what you were scaffolded from.
2. **The ephemeral-env workflow** — referenced by version (`@v1`), not copied. Don't
   inline its logic here; if it needs to change, that change happens once, upstream.
