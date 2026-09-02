# Argo CD ApplicationSet Migration for Ephemeral PR Environments

## Status

Proposed — design only, not started. Carried over from the original golden-path
build plan, where it was scoped as target architecture (P4, deferred): "migrate
once there is a working baseline and a second consumer to prove it against."
That baseline now exists — the `http-service` template is live and the
`stale-environment-finder` Backstage plugin has already read Application state
produced by today's mechanism in production — but no second real consumer
(a service other than the ones already scaffolded from this template) has
onboarded yet, so the original gating condition is only half met.

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

## Open questions (not yet resolved)

- Whether the `applicationsets.argoproj.io` CRD/controller is installed on
  the homelab cluster at all — unconfirmed; the cluster wasn't reachable from
  this session (VPN-gated) to run `kubectl get crd applicationsets.argoproj.io`.
- Whether the `default` AppProject's namespaced-resource permissions actually
  let the app-of-apps root Application create an `ApplicationSet` custom
  resource the same way it creates `Application` resources today — needs a
  real, throwaway test against the live cluster, not an assumption.
- Whether a GitHub token Secret for the generator already exists in the
  `argocd` namespace, or needs to be created — and if created, whether it
  belongs in `homelab-argocd-control` (core platform config, low churn) per
  the reasoning in
  [`two-argocd-repos-adr.md`](https://github.com/lukasb27/homelab-argocd-control/blob/main/docs/two-argocd-repos-adr.md),
  rather than `application-argocd-control`.
- Whether `head_short_sha`'s format is guaranteed to match `docker.yml`'s
  `type=sha` tag output (`sha-<7-char short SHA>`) byte-for-byte — asserted
  from each tool's documented default, not yet verified against a real PR.

## Revisit Trigger

Once a second real service has been scaffolded and is running on the current
mechanism without issue (satisfying the original plan's own gating condition
in full), and once the Open questions above are resolved by direct
verification against the live cluster — not before.
