# backstage-templates

Backstage Software Templates for the golden path, plus the platform
architecture docs for the whole system they scaffold into.

Ships one template today:

- **[http-service](templates/http-service/template.yaml)** — a long-running
  HTTP service (Python/FastAPI in v1): Deployment + Service + Ingress + a
  health route + black-box HTTP tests, with CI, a multi-stage Docker build,
  branch protection, catalog registration, and a per-PR ephemeral Argo CD
  environment wired in from the start. Not for a CronJob or a queue worker.

## Docs

Rendered as a [TechDocs](https://backstage.io/docs/features/techdocs/) site
inside Backstage (see `catalog-info.yaml`'s `backstage.io/techdocs-ref`), or
readable directly here:

| Doc | Covers |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | How one scaffolded service's request path actually works end to end — the push→build→deploy→test sequence and which repo owns which piece |
| [docs/platform-overview.md](docs/platform-overview.md) | The five repos that make up the whole golden-path system, and why there are two separate Argo CD control repos |
| [docs/argocd-notifications-gate-adr.md](docs/argocd-notifications-gate-adr.md) | Why the integration-test merge gate stays in-cluster rather than moving to Argo CD Notifications, and the fork-PR security gap this closed along the way |
| [docs/claude-review-and-triage-adr.md](docs/claude-review-and-triage-adr.md) | The label-triggered Claude PR review and issue triage workflows shipped in the skeleton, and the `claude-code-action` config traps found running them live |
| [docs/orphan-detector-plugin-adr.md](docs/orphan-detector-plugin-adr.md) | The `stale-environment-finder` Backstage plugin — what shipped (Argo-vs-PR-state detection) and what didn't (GHCR-orphan detection) |

## What the template actually creates

Running `http-service` through Backstage's `/create` wizard does all of this,
in order (see [`template.yaml`](templates/http-service/template.yaml)):

1. Fetches the base skeleton, then the language-specific skeleton, into a new
   repo — `templates/http-service/skeletons/app/base` +
   `skeletons/app/languages/<language>` merged together.
2. Publishes it to GitHub and sets up branch protection (0 required
   approvals, admins not enforced — deliberate for a single-maintainer
   account; see the skeleton's own `CONTRIBUTING.md` for why the GitHub
   defaults would otherwise make every PR permanently unmergeable).
3. Restricts PR creation to collaborators via
   [`goldenPath:restrictPrCreation`](docs/platform-overview.md#extending-the-scaffolder-with-custom-logic),
   a custom scaffolder action living in `backstage-app`, not this repo.
4. Opens a PR against `application-argocd-control` adding the new service's
   persistent Argo CD `Application`.
5. Registers the new repo in the Backstage catalog and notifies the owner.

From there, every PR the new service opens builds and pushes two images to
GHCR, then a per-service Argo CD `ApplicationSet` (delivered once, at scaffold
time, alongside the persistent `Application`) stands up a namespaced,
self-cleaning ephemeral environment pinned to that PR's exact commit, and runs
its integration tests against the real deployed Service — see
[docs/architecture.md](docs/architecture.md) for the full sequence diagram,
and [the ApplicationSet migration ADR](docs/argocd-applicationset-migration-adr.md)
for how this replaced an earlier CI-git-push mechanism (`template-version: v1`,
now legacy — only `lukas-test` still runs on it).

## Repository layout

```
templates/http-service/
  template.yaml              # the Template entity: parameters + scaffolder steps
  skeletons/
    app/base/                 # language-agnostic: CI scaffolding, k8s/, docs/, CODEOWNERS, ...
    app/languages/python/     # FastAPI app code, Dockerfile, poetry config
    control/                  # the persistent Application + previews ApplicationSet, templated per service
scripts/verify_template.py   # static checks — see below
docs/                        # architecture + ADRs, rendered as TechDocs
.github/workflows/
  verify-template.yml         # runs verify_template.py + the python skeleton's own tests on PRs
```

## Verifying template changes

[`scripts/verify_template.py`](scripts/verify_template.py) runs on every PR
touching `templates/**` ([`verify-template.yml`](.github/workflows/verify-template.yml)).
It's deliberately static — it doesn't call Backstage's scaffolder dry-run API,
since that endpoint only resolves inside the homelab's VPN and a GitHub-hosted
runner can't reach it. Instead it checks the same failure patterns this
template has actually hit live: `fetch:template` URLs and enum values that
don't line up with real directories, and `copyWithoutTemplating` glob patterns
that silently match nothing (a leading `./` is enough to break this — see the
script's own comments for why).

The same workflow separately assembles the `app/` tree a real scaffold would
produce (base skeleton + Python skeleton merged, matching `template.yaml`'s
fetch order), fills in the handful of Nunjucks tokens by hand, and runs the
skeleton's actual `pytest`/`flake8` commands against it — so a broken
`pyproject.toml` or a failing test in the skeleton itself gets caught here,
not on someone's next real scaffold.

## Related repositories

| Repo | Owns |
| --- | --- |
| [backstage-app](https://github.com/lukasb27/backstage-app) | The Backstage instance itself — portal, `/create` wizard, catalog, and custom scaffolder actions like `goldenPath:restrictPrCreation` |
| This repo | The `http-service` template and this documentation |
| [homelab-argocd-control](https://github.com/lukasb27/homelab-argocd-control) | Core platform Argo CD — CNPG, Postgres, Backstage itself |
| [application-argocd-control](https://github.com/lukasb27/application-argocd-control) | Per-service Argo CD Applications (persistent + ephemeral), created and destroyed by each scaffolded service's own CI |
| Scaffolded services | Application code, `k8s/` base, CI — one repo per service, all built from this template |

See [docs/platform-overview.md](docs/platform-overview.md) for the full
reasoning behind the repo split.
