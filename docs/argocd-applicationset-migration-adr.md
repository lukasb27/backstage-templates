# Argo CD ApplicationSet Migration for Ephemeral PR Environments

## Status

Accepted — implementation started 2026-09-15. See "Update — 2026-09-15" below:
the second-service half of this ADR's original Revisit Trigger was explicitly
waived by the platform owner, not satisfied; the Open questions below were
resolved by direct live verification first.

## Context

Every golden-path service creates its own per-PR ("ephemeral") Argo CD
`Application` the same way today: a shared reusable workflow,
[`ephemeral-env.yml`](https://github.com/lukasb27/backstage-templates/blob/main/.github/workflows/ephemeral-env.yml),
polls GHCR for the PR's Docker images, renders an `Application` manifest by
hand (shell heredoc), and `git push`es it into
[`application-argocd-control`](https://github.com/lukasb27/application-argocd-control)'s
`apps/` directory using a per-repo `ARGO_CD_REPO_TOKEN` secret. On PR close,
[`cleanup.yml`](https://github.com/lukasb27/backstage-templates/blob/main/templates/http-service/skeletons/app/base/.github/workflows/cleanup.yml)
does the reverse. Both files independently recompute the same branch-name
slugification
([`ephemeral-env.yml` L73](https://github.com/lukasb27/backstage-templates/blob/main/.github/workflows/ephemeral-env.yml#L73),
[`cleanup.yml` L24](https://github.com/lukasb27/backstage-templates/blob/main/templates/http-service/skeletons/app/base/.github/workflows/cleanup.yml#L24))
— `cleanup.yml`'s own comment already flags that a mismatch here makes
cleanup silently no-op.

The rendered `Application` targets the **branch name**, not a commit, for both
`targetRevision` and the container image tag
([`ephemeral-env.yml` L90, L94-95](https://github.com/lukasb27/backstage-templates/blob/main/.github/workflows/ephemeral-env.yml#L90-L95)),
even though
[`docker.yml`](https://github.com/lukasb27/backstage-templates/blob/main/templates/http-service/skeletons/app/base/.github/workflows/docker.yml#L27)
already publishes a `type=sha` tag on every build that nothing currently
reads — so a force-push can silently change what's deployed without the
`Application` ever seeing a new revision.

`application-argocd-control` is an app-of-apps: its root
[`main.yaml`](https://github.com/lukasb27/application-argocd-control/blob/main/main.yaml)
Application watches everything under `apps/` and auto-syncs it, regardless of
resource kind — both the persistent, scaffold-time `main`-branch Application
(delivered once via the template's `register-argo-app` PR step) and every
ephemeral Application committed by CI land in that same watched directory.

Argo CD's `ApplicationSet` controller has a built-in `pullRequest` (GitHub)
generator that exposes `number`, `branch`, `branch_slug`, `head_sha`,
`head_short_sha`, and `labels` per open PR, and can template an `Application`
per match directly — no CI-driven git write required. `job.yaml`'s PR-status
reporting already reads `prNumber`/`commitSha` from the Application's
`kustomize.commonAnnotations` via the Kubernetes downward API, so it is
agnostic to *how* the Application was created.

## Decision

Replace `ephemeral-env.yml`'s git-push-based Application creation and
`cleanup.yml`'s git-push-based deletion with a single `ApplicationSet`
(`pullRequest` GitHub generator) per service, for **ephemeral, per-PR
Applications only**. The persistent, `main`-branch Application per service
keeps its current mechanism unchanged — templated once by
`register-argo-app`, delivered as a one-time reviewed PR to
`application-argocd-control`.

The `ApplicationSet` resource itself is generated at scaffold time, as a new
file alongside the existing `${{ values.name }}-main.yaml` in the template's
`control` skeleton, and delivered through the same `register-argo-app` PR —
so it rides the existing app-of-apps root Application with no new bootstrap
step. Ephemeral Applications key off `{{.head_sha}}` for `targetRevision` and
`sha-{{.head_short_sha}}` for the image tag (matching `docker.yml`'s existing,
currently-unused `type=sha` output), replacing the mutable branch reference.

### Alternatives considered

- **Keep the current mechanism, fix the two known bugs in place** (dedupe the
  branch-slug computation into one shared script; switch to SHA-based
  tags/`targetRevision` without changing the git-push architecture). Rejected
  as the near-term option, not the target one: it doesn't remove the per-repo
  `ARGO_CD_REPO_TOKEN` or the CI-as-git-writer pattern that the original plan
  identified as worth migrating away from once proven.
- **Argo CD Notifications for PR status, independent of this migration**
  (inferred from the original plan's own aside that it's "already the
  recommended answer for the reporting credential"). Not part of this
  decision — `job.yaml`'s existing downward-API-based reporting path is
  preserved as-is; Notifications is a separate, later decision.

## Consequences

**Positive:**
- Deletes `ephemeral-env.yml`'s image-wait polling loop, `cleanup.yml`
  entirely, and the per-repo `ARGO_CD_REPO_TOKEN` secret — the
  `ApplicationSet` controller authenticates to GitHub once, in-cluster, via
  its own Secret, not a token every newly scaffolded repo must have set by
  hand.
- Removes the two-file branch-slug duplication; `branch_slug` becomes a
  single computation done once by the controller.
- Pins ephemeral deploys to a commit instead of a mutable branch reference,
  closing the force-push gap.
- No change required to `job.yaml`, `docker.yml`, or the reporting path.

**Negative / new debt:**
- Loses the git commit history in `application-argocd-control` of when each
  ephemeral Application was created/removed — that lifecycle becomes
  controller-managed cluster state instead of an auditable commit log.
- New race: without an explicit "wait for image" step, the generator can
  match a PR and create its Application before `docker.yml` has finished
  pushing the SHA-tagged image, producing a transient `ImagePullBackOff`.
  Needs a `preview` label that CI applies only after a successful push, with
  the generator filtering on it.
- Default `requeueAfterSeconds` (1800s) means up to 30 minutes of staleness
  between real PR state and the generated Applications unless the
  `ApplicationSet` webhook server is separately configured.
- Introduces a new class of cluster-scoped infrastructure (one `ApplicationSet`
  per service) whose existence and permissions have to be verified rather
  than assumed — see Open questions.

## Open questions (resolved — see Update below)

- ~~Whether the `applicationsets.argoproj.io` CRD/controller is installed on
  the homelab cluster at all~~ — confirmed live: CRD present, and
  `argocd-applicationset-controller` pod is `Running`, not just deployed.
- ~~Whether the `default` AppProject's namespaced-resource permissions
  actually let the app-of-apps root Application create an `ApplicationSet`
  custom resource~~ — confirmed live: the `default` `AppProject` is wide
  open (`sourceRepos: ['*']`, `destinations: ['*'/'*']`,
  `clusterResourceWhitelist: ['*'/'*']`), imposing no restriction beyond what
  every existing hand-written `Application` already relies on.
- ~~Whether a GitHub token Secret for the generator already exists in the
  `argocd` namespace, or needs to be created~~ — a `github-pr-token` Secret
  already existed there, but as a side effect of an unrelated, cluster-wide
  External Secrets Operator mirror (`global-github-token`, empty
  `namespaceSelectors`), not something scoped for this purpose. A new,
  distinct `github-pr-generator-token` `ExternalSecret` was added instead
  (`homelab-argocd-control` PR #7), reading the same underlying
  `central-github-token-secret` without minting a new GitHub App — landing
  exactly where this ADR speculated it would.
- Whether `head_short_sha`'s format matches `docker.yml`'s `type=sha` tag
  output byte-for-byte — not verified, and no longer needs to be: the
  implementation templates the image tag as `sha-{{ trunc 7
  .head_short_sha }}` (Sprig, via `goTemplate: true`), fixing the length
  structurally so drift on either side can't cause a mismatch.

## Revisit Trigger

Original trigger (superseded — see Update below): once a second real service
has been scaffolded and is running on the current mechanism without issue,
and once the Open questions above are resolved by direct verification
against the live cluster.

## Update — 2026-09-15

Implementation started at the platform owner's explicit direction, with only
one real scaffold (`lukas-test`) still existing — the "second real service"
half of the original Revisit Trigger above was **waived, not satisfied**.
This is a deliberate, acknowledged deviation from this ADR's own stated
precondition, not an oversight: recorded here rather than silently building
past it. The Open questions half of the trigger *was* met in full first, via
direct live verification (`kubectl get crd`/`get pods`/`get appproject`,
read-only throughout — the implementation plan's Phase 0 spike), before any
code or cluster change was made.

Implementation is tracked via the phased plan at
`~/.claude/plans/wiggly-plotting-lerdorf.md` (not itself in this repo).
Phase 0 (spike) and Phase 1 (`github-pr-generator-token` provisioning) are
done as of this update; Phases 2-5 (the `preview` label gate, the
`backstage-templates` skeleton changes, `application-argocd-control` doc
updates, and end-to-end verification on a throwaway scaffold) are in
progress.
