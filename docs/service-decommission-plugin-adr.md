# Custom Backstage Plugin for Service Archive/Delete

## Status
Proposed — design discussion only, not started. Blocked on wiring up a real Backstage
auth provider first (see [[Consequences]]); pursued after that lands.

## Context

Investigating the golden path's end-to-end health surfaced a real gap: GHCR packages
aren't deleted when their source repository is deleted — they become account-level
orphans, silently readable and blocking any future repo of the same name from pushing
images (`docker.yml` fails with `permission_denied: write_package`). Hit live 2026-08-19
scaffolding `lukas-test-e2e-verify`, which collided with an orphaned package left over
from an older, already-deleted scaffold of the same name.

That surfaced the bigger question this ADR is about: there is no decommissioning story
for a golden-path service at all today. Retiring a service currently means deleting the
GitHub repo by hand and hoping someone remembers the rest — the persistent Argo CD
Application, the GHCR packages, the Backstage catalog entity all get left behind with no
mechanism prompting their removal.

## Decision (proposed, not yet built)

A two-tier operation, not a single "delete" button:

- **Archive** — soft, reversible-ish. Removes the persistent Argo CD Application
  manifest from `application-argocd-control` (so Argo prunes the live k8s resources),
  deletes the GHCR packages, and sets `spec.lifecycle: archived` on the catalog
  entity — an existing, idiomatic Backstage field, not a custom annotation. The GitHub
  repo and catalog entity both stay, so history and provenance remain queryable.
- **Delete** — hard. Everything Archive does, plus deregisters the catalog location
  entirely (`DELETE /api/catalog/locations/:id`, cascades to the entity — same call
  already used for throwaway-scaffold cleanup) and deletes the GitHub repo itself.

**Proposed architecture:** a new custom **backend plugin**, not an extension of the
existing `goldenPath:restrictPrCreation` scaffolder-action module
(`backstage-app`'s `packages/backend/src/modules/goldenPathActions.ts`) — that module
only runs as a step inside a template task. Archive/Delete need to be callable on
demand against an *already-existing* entity, so this needs its own registered routes
(`createBackendPlugin`, not `createTemplateAction`). Paired with a frontend plugin
contributing a card/buttons on the Component's entity page — following the same
`app.packages: all` auto-discovery pattern the scaffolder plugin already relies on
(see [[project-golden-path-custom-scaffolder-actions]] equivalent reasoning), no
`App.tsx` wiring expected to be needed.

## Consequences

**This is the first capability in the golden path that needs `delete_repo` and
`packages:delete` on Backstage's GitHub integration token.** Everything the backend
currently does with that token — creating repos, opening PRs, setting branch
protection — is additive. Combined with this instance's current auth posture
(`guest.dangerouslyAllowOutsideDevelopment: true`, `allow-all` permission policy,
documented as an accepted risk in `docs/`'s security-posture discussion since the
worst case was "an anonymous visitor can create repos"), adding a delete/nuke action
behind the same unauthenticated surface changes the worst case to "an anonymous
visitor can delete any repo and its packages." Judged not acceptable even though this
instance is LAN-only, not internet-facing — internal-only genuinely lowers severity
(consistent with how the existing guest-auth risk was already reasoned about) but
doesn't remove the case for real auth ahead of a strictly more dangerous capability
than anything currently granted. **This is the concrete reason this project is
pivoting to wiring up a real Backstage auth provider next**, rather than an
abstract "we should do this eventually."

**On credential granularity** — GitHub's permission model was discussed at length and
is worth recording: fine-grained PATs scope along two axes, *which repos* (specific
repos, or all) and *which permission category* per repo (Contents, Pull requests,
Administration, Packages, …) at none/read/write. Repository deletion specifically
sits under "Administration: write". This gives real resource-level scoping,
comparable in spirit to an IAM resource restriction, but the *action* granularity is
coarser than IAM — GitHub bundles several related admin actions (deletion,
visibility, collaborators) under one category rather than exposing each as an
independently-grantable action, and there's no conditional logic (no IP restriction,
no time-of-day, nothing MFA-gated) available to a personal-account PAT. GitHub Apps
add one more lever already flagged elsewhere in this project (the deferred
`goldenPath:setRepoSecrets` discussion): short-lived, per-request tokens
(`actions/create-github-app-token`) instead of one static broadly-scoped PAT sitting
in Backstage's config indefinitely — same coarse permission categories, but nothing
long-lived to leak. Worth using this pattern here rather than a static PAT, once this
plugin is actually built.

**Shared root cause with an already-known bug** — Archive's Argo-prune step would hit
the exact same namespace-orphaning issue already found in `cleanup.yml`
(`CreateNamespace=true` isn't a tracked resource, so pruning the Application never
removes the namespace). That fix — parked as part of the deferred "stale-environment
reaping" P4 item — is a shared prerequisite for this plugin's Archive step too, not
two independent problems with two independent fixes.

## Open questions (not yet resolved)

- What actually triggers Archive vs. Delete — a manual button only, or also some
  policy-driven path (e.g., N days with no activity)? Leaning manual-only for now,
  given this is a one-maintainer platform with no volume problem to automate away.
- Should Archive block if the service has open PRs (unclosed ephemeral environments),
  or force-close them first?
- Does re-scaffolding a new service under an already-archived name need special
  handling, or does the existing GHCR-collision problem this whole investigation
  started from just recur identically?
- Exact sign-in/permission-policy shape once real auth lands — this plugin's own
  authorization model (who's allowed to Archive/Delete) depends on decisions not yet
  made in the auth pivot this ADR is now blocked on.

## Revisit Trigger

Once a real Backstage auth provider and a non-`allow-all` permission policy are live,
revisit this ADR to move it from Proposed to Accepted (or revise the design based on
whatever the auth work surfaces) before writing any code.
