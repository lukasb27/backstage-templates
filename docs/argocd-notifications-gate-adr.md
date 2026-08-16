# Argo CD Notifications for the Integration-Test Gate

## Status
Rejected (for now — see Revisit Trigger)

## Context

The golden-path implementation plan listed "Argo CD Notifications for the `kubernetes/integration-tests`
gate" as an open item. The idea: instead of the in-cluster integration-test
[`Job`](https://github.com/lukasb27/backstage-templates/blob/main/templates/http-service/skeletons/app/base/k8s/job.yaml)
posting the pass/fail commit status itself (via
[`post_report_to_pr.py`](https://github.com/lukasb27/backstage-templates/blob/main/templates/http-service/skeletons/app/languages/python/integration_tests/post_report_to_pr.py)),
Argo CD's built-in Notifications controller would post it directly from the `Application`'s sync/health
result, using a GitHub token held once, centrally, in the `argocd` namespace.

Investigating this surfaced a real, separate bug along the way: `post_report_to_pr.py` reads
`Path("/etc/github/token")` unconditionally, but nothing in `job.yaml` ever mounted that file — every
scaffolded service's integration-test Job crashed with `FileNotFoundError` the first time it ran. That bug
is fixed independently of this ADR (the missing volume mount was added, matching the already-working
pattern in `fermentation-station-agent`'s own `job.yaml`). This ADR is only about whether to *also* adopt
Notifications for the gate signal on top of that fix.

Two separate rationales were considered for doing so:

1. **Security.** The original motivation: a GitHub token capable of writing commit statuses (and, in the
   current shared-token design, considerably more — see below) sits inside a namespace running code from an
   unreviewed PR branch. Moving the gate signal to a centrally-held credential would keep that token out of
   the namespace entirely.
2. **Reliability.** A narrower rationale, independent of security: the commit status that actually gates
   merging currently depends on the test pod successfully completing an outbound HTTP POST to GitHub's API,
   *after* the test suite has already run. If that pod dies, gets OOMKilled, or hits a network blip in that
   window, the check hangs at `pending` forever — a required check that never resolves permanently blocks
   every future merge. Argo CD Notifications, by contrast, would read the Job's actual exit status via the
   Kubernetes API, which Argo CD is already tracking regardless of what the pod itself manages to do
   afterward.

## Decision

Reject both rationales for now, and fix only the crash.

**Security rationale rejected — but only after actually closing the gap, not by assuming it away.** The
first pass at this reasoning claimed "only the repository owner can open PRs against these repositories,"
treating that as a given. It wasn't: all five repositories involved
(`backstage-templates`, `application-argocd-control`, `homelab-argocd-control`,
`fermentation-station-agent`, `backstage-app`) were **public**, with no branch protection on `main`, and
GitHub's REST API confirmed each carried `"pull_request_creation_policy": "all"` — meaning, until this ADR,
any GitHub account could fork any of them and open a PR, independent of collaborator lists (collaborator
access governs push/merge rights, not who can open a PR from a fork; this is standard GitHub behaviour, not
a per-repo bug). `fermentation-station-agent` was already exposed to this in production, unrelated to
tonight's changes — its own `github-pr-token` mount predates this investigation.

The fix: GitHub added a real, first-party control for exactly this
([`github/roadmap#1232`](https://github.com/github/roadmap/issues/1232), GA, available on the Free SKU).
The REST API's ["Update a repository"](https://docs.github.com/en/rest/repos/repos?apiVersion=2022-11-28#update-a-repository)
endpoint exposes `pull_request_creation_policy`, accepting `all` (the previous, default state) or
`collaborators_only`. All five repositories above were switched to `collaborators_only` as part of this ADR
— confirmed via the API response echoing the new value back on each. With no collaborators on any of these
repositories besides the owner, the original claim is now actually true, enforced by GitHub itself rather
than assumed. **This is what the security rationale actually needed** — not routing the gate signal through
Notifications, which would have left the fork-PR path itself wide open while only changing which credential
sits in the namespace.

**Reliability rationale considered and set aside, not dismissed:** it is a real argument — the in-cluster
reporting script has produced several distinct bugs this session alone (a hardcoded commit SHA, a
`sha`/`commitSha` annotation-key mismatch, a double test-execution race in the original `behave`-based
version, and now this missing-mount crash), which is exactly the kind of fragility that would justify
decoupling the merge gate from the script's correctness. But adopting it means standing up a second,
previously-unconfigured cluster-level system (`argocd-notifications-cm`/`-secret`, currently empty) as a new
manual prerequisite, for a benefit that is real but not urgent — the crash fix alone resolves today's actual,
concrete problem. Not worth the added moving parts tonight.

`fermentation-station-agent` was not touched by this investigation or decision — it keeps its own working
`post_report_to_pr.sh` path exactly as it is.

## Consequences

**Positive:** no new cluster-level configuration surface, no new manual prerequisite to document and keep
working. The fix that actually mattered (the crash) is small, self-contained, and matches an
already-proven pattern instead of introducing a new one. The fork-PR gap that motivated the security
rationale in the first place is genuinely closed — by GitHub itself enforcing it, not by an assumption about
who happens to have push access.

**Negative / debt:** the merge gate remains coupled to the in-cluster script's ability to complete an
outbound HTTP call after tests finish running. A future bug in that script — or a future outage that kills
the pod in the wrong window — can still hang a required check at `pending` indefinitely, exactly the failure
mode described above. This is accepted, not solved.

For the five repos patched directly, `pull_request_creation_policy` is a live setting, not something
tracked in git — if any of them is ever recreated (rename, transfer, disaster recovery), it needs reapplying
by hand. For every *future* scaffolded service, this is no longer manual: no stock scaffolder action exists
for this (there is no generic HTTP/settings action installed in this Backstage instance, and building a
custom one repeats the reasoning already rejected for `ANTHROPIC_API_KEY` distribution — the only bespoke
backend code, requiring an image rebuild for every change). Instead,
[`bootstrap-repo-settings.yml`](https://github.com/lukasb27/backstage-templates/blob/33a4b67/templates/http-service/skeletons/app/base/.github/workflows/bootstrap-repo-settings.yml)
(linked at the commit that added it — removed since, see the 2026-08-16 update below)
ships in every scaffolded service's skeleton and self-applies the setting on the first push to `main` (the
repo's own `github.token`, granted `administration: write`, patching its own settings — no new secret).
Re-runs on every subsequent push to `main` too, so it self-heals if the setting is ever reset by hand.

## Revisit Trigger

- **Security:** if `collaborators_only` is ever found unset on one of the five repos patched directly (e.g.
  after a repo recreation) — reapply it by hand; `bootstrap-repo-settings.yml` only covers newly scaffolded
  services, not these pre-existing repos. If a newly scaffolded service is ever found with the policy back on
  `all`, check whether `administration: write` actually behaves as expected for `GITHUB_TOKEN` on this
  account tier — that specific permission scope's behavior here was not independently verified beyond writing
  the workflow, only reasoned from GitHub's documented permission model.
- **Reliability:** if the in-cluster reporting script produces another bug that actually hangs a required
  check in production (not just a wrong count or a bad log line, but a merge genuinely blocked), the
  reliability case for Argo CD Notifications moves from "real but not urgent" to "worth the cluster-config
  cost."

## Update — 2026-08-16

The security revisit trigger above fired, on the first real test. `administration` is not "unverified for
`GITHUB_TOKEN` on this account tier" — it isn't a valid key in a workflow's `permissions:` block **at all**,
for any token, on any account (confirmed against GitHub's workflow-syntax reference: the full list is
`actions`, `artifact-metadata`, `attestations`, `checks`, `code-quality`, `contents`, `deployments`,
`discussions`, `id-token`, `issues`, `packages`, `pages`, `pull-requests`, `security-events`, `statuses`,
`vulnerability-alerts`). GitHub Actions rejects the whole workflow file at parse time over the unrecognized
key — zero jobs ever run, surfaced as a generic "failed because of a workflow file issue" — so
`bootstrap-repo-settings.yml` has never once succeeded, on any scaffold, since it was written.

Confirmed live: a fresh scaffold (`lukas-test-e2e-verify`, 2026-08-16) came up with
`pull_request_creation_policy` still `all`. The fork-PR gap this ADR set out to close on every future service
has been open on every one of them since `bootstrap-repo-settings.yml` shipped, silently — no error surfaced
anywhere a human would see it.

**Revised decision:** replace the workflow with a custom scaffolder action,
[`goldenPath:restrictPrCreation`](https://github.com/lukasb27/backstage-app/blob/main/packages/backend/src/modules/goldenPathActions.ts),
run once at scaffold time as a `template.yaml` step, right after branch protection. This does **not** repeat
the reasoning rejected for `goldenPath:setRepoSecrets` (the plan's P4 note on secret distribution) — that
rejection was about injecting a *new secret* into every scaffolded repo, where the real answer is an
org-level secret policy or short-lived App tokens, not custom backend code. This action injects nothing into
the scaffolded repo at all; it makes one authenticated API call from Backstage's own backend, using the
`backstage-scaffolder-github-token` credential Backstage already holds and already uses for
`github:branch-protection:create` a few steps earlier in the same template — the exact mechanism, and the
exact credential, that just proved live it can already do admin-level operations on a repo it didn't create
manually. No new secret, anywhere.

The five pre-existing repos patched directly by this ADR were unaffected by this bug (that was a one-time
manual API call, not the workflow) and remain `collaborators_only`.
