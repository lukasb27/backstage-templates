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
mode described above. This is accepted, not solved. Also, `pull_request_creation_policy` is a live repo
setting, not something tracked in git anywhere — if any of these five repos is ever recreated (rename,
transfer, disaster recovery), this needs to be reapplied by hand; it isn't part of `publish:github`'s
scaffolding step yet, so newly scaffolded services don't get it automatically either.

## Revisit Trigger

- **Security:** if `collaborators_only` is ever found unset on one of these repos (e.g. after a repo
  recreation), or if a newly scaffolded golden-path service is found still on the default `all` policy —
  reapply it. Longer-term, add `pull_request_creation_policy` (or an equivalent scaffolder action) to
  `template.yaml`'s `publish` step so every future scaffolded service gets this by default instead of
  needing a manual follow-up.
- **Reliability:** if the in-cluster reporting script produces another bug that actually hangs a required
  check in production (not just a wrong count or a bad log line, but a merge genuinely blocked), the
  reliability case for Argo CD Notifications moves from "real but not urgent" to "worth the cluster-config
  cost."
