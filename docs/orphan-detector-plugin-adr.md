# Custom Backstage Plugin for Orphan/Stale Environment Detection

## Status
Accepted — built as the `stale-environment-finder` plugin in `backstage-app`
(PRs #16, #20). Only the `findStaleEnvironments` half of the design shipped;
see the note under Consequences — the `findOrphanedPackages` / GHCR-orphan
check described below was not built.

## Context

Two related gaps surfaced from direct investigation elsewhere in this project,
neither currently detected by anything:

- **Orphaned GHCR packages** — GHCR packages aren't deleted when their source
  repository is deleted; they become account-level orphans that silently block
  any future repo of the same name from pushing images
  (`docker.yml` fails with `permission_denied: write_package`). Hit live
  2026-08-19 scaffolding `lukas-test-e2e-verify`, which collided with a package
  orphaned by an older, already-deleted repo of the same name. See
  `service-decommission-plugin-adr.md` for the fuller writeup of this finding.
- **Stale ephemeral environments** — per-PR preview environments (Argo CD
  Applications) aren't guaranteed to be cleaned up when their PR closes or
  merges, leaving live k8s resources with nothing pointing back at an open PR.

Both are the same shape of problem: query an external system (GHCR, Argo),
correlate against what GitHub/the catalog actually knows is still live, and
list what doesn't match. Neither is served by anything already installed or
installable off the shelf — they depend on this platform's specific naming
conventions, not generic service health.

## Decision (proposed, not yet built)

A single custom plugin, **read-only / detection-only**:

- A `GET /anomalies` backend route (via `createBackendPlugin`) that runs two
  independent checks and returns their combined result:
  - `findStaleEnvironments` — cross-references Argo `Application` names
    against GitHub PR state.
  - `findOrphanedPackages` — cross-references GHCR packages against known
    live repos.
- A frontend page (new frontend system, matching the app's existing
  `app.packages: all` auto-discovery pattern) that fetches and displays the
  two anomaly lists.
- Gated behind a new permission (`goldenPath.fleet.read`) at the `read` RBAC
  tier, once the RBAC policy work lands — read-only data warrants the lowest
  tier, unlike anything that would act on the findings.

**Deliberately excludes any delete/reap action.** Acting on stale environments
(deleting the Argo Application, the namespace) is scoped as a separate
scaffolder template (`reap-stale-environments`, using an on-demand triggered
Template rather than a plugin — matching how `service-decommission-plugin-adr.md`
now also leans toward EntityPicker-driven templates over bespoke plugin routes
for anything that *acts* rather than *observes*). This plugin would be the
template's read-only detector — one produces the list, the other acts on it —
kept as two separate builds rather than one plugin that does both, so the
read-only surface never needs write-scoped credentials.

A full phased build plan (scaffolding steps, which Backstage APIs are involved
in each phase, test approach) is tracked outside this repo for now, as working
notes rather than committed documentation, since the plugin doesn't exist yet.

## Consequences

**Shared root cause with an already-known bug** — actually reaping a stale
environment (not detecting it — that's this plugin's job) would hit the same
Argo namespace-orphaning issue already found in `cleanup.yml`
(`CreateNamespace=true` isn't a tracked resource, so pruning the Application
never removes the namespace). That fix is a shared prerequisite for the
eventual `reap-stale-environments` template, not something this detector plugin
needs to solve itself since it never deletes anything.

**Credential posture stays low-risk** — because this plugin is read-only, it
only ever needs read-scoped tokens (GHCR package read, Argo read, GitHub PR
read), unlike the decommission work's need for `delete_repo`/`packages:delete`.
It can reasonably ship ahead of the full RBAC/auth rollout finishing, gated at
whatever the lowest available tier is at the time, without materially changing
the instance's current risk posture the way the decommission plugin would.

**`findOrphanedPackages` (the GHCR-orphan-package check) was not built.** The
plugin that shipped (`stale-environment-finder` /
`stale-environment-finder-backend` in `backstage-app`, PRs #16 and #20) only
implements `findStaleEnvironments` — the Argo-vs-GitHub-PR-state check. The
GHCR-vs-known-repos check scoped above in Decision is still just a design on
paper: no route, no client, no logic module for it exists in the built plugin.
This remains open future work. Anyone relying on this ADR for GHCR-orphan
coverage should not assume it shipped — the orphaned-package problem
described in Context is still undetected by anything today.

## Confirmed since first draft

**No naming-convention parsing needed, and no new label has to be added
anywhere.** The reusable workflow
[`ephemeral-env.yml`](https://github.com/lukasb27/backstage-templates/blob/main/.github/workflows/ephemeral-env.yml#L92-L99)
— called by every scaffolded service's own CI after tests pass, see the call
site in
[`actions.yml`](https://github.com/lukasb27/backstage-templates/blob/main/templates/http-service/skeletons/app/languages/python/.github/workflows/actions.yml#L196-L201)
— already writes the PR number and repo slug directly into the Argo
`Application` it creates, as plain `spec` fields (`spec.source.kustomize.commonAnnotations.prNumber`
/ `.repoSlug`). Argo's `GET /api/v1/applications` list endpoint returns each
Application's full `spec`, so this data is readable straight off the list
response with no name-string parsing and no change needed to
`k8s/deployment.yaml` (which carries no per-environment identity — checked
directly, see
[`deployment.yaml`](https://github.com/lukasb27/backstage-templates/blob/main/templates/http-service/skeletons/app/base/k8s/deployment.yaml)).

**Also confirmed (2026-08-21, checked directly in Argo):** persistent/production
Applications *do* carry the `prNumber` annotation — it's just set to an empty
string (`""`), not omitted. So the ephemeral-vs-persistent signal has to be
"`prNumber` is non-empty," not "the annotation is present" — the latter would
misclassify every production Application as an ephemeral environment. Worth
stating this explicitly in Phase 3's correlation logic rather than leaving it
implicit, since it's the kind of off-by-one-condition bug that's easy to
introduce and easy to miss until it's run against a real cluster.

## Open questions (not yet resolved)

None outstanding — both ground-truth items from the original open questions
list are now resolved.
- Whether results should ever be pushed anywhere proactively (e.g. a periodic
  digest) or stay strictly pull/on-page-load — leaning strictly pull for now,
  consistent with the "no volume problem to automate away" reasoning already
  used for the decommission plugin's manual-only trigger question.
- Whether `reap-stale-environments` should consume this plugin's `/anomalies`
  route directly as its dry-run source, or duplicate the same correlation
  logic inside the template action — leaning toward reuse once both exist, to
  avoid two implementations of the same check drifting apart.

## Revisit Trigger

Once the plugin is actually built (by hand, as a learning exercise — not
scaffolded via Claude Code), revisit this ADR to move it from Proposed to
Accepted and record anything the build surfaced that changed the design.
