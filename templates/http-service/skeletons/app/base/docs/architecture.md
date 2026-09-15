# Architecture

## Repositories

| Repo | Holds |
| --- | --- |
| This repo | Application code, Dockerfile, `k8s/` base, CI |
| [application-argocd-control](https://github.com/lukasb27/application-argocd-control) | The persistent Argo CD `Application` for `main`, and the previews `ApplicationSet` that generates one ephemeral `Application` per open PR |
| [backstage-templates](https://github.com/lukasb27/backstage-templates) | The template this repo was scaffolded from |

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
2. **The previews `ApplicationSet`** — lives in the control repo, generated once at
   scaffold time. Don't hand-edit it there; if the generator logic needs to change,
   that change happens upstream, in the template.
