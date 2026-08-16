# Claude-Powered Issue Triage and PR Review

## Status
Accepted

## Context

The skeleton's [README](https://github.com/lukasb27/backstage-templates/blob/main/templates/http-service/skeletons/app/base/README.md)
has documented `ANTHROPIC_API_KEY` as a required one-time secret, for
`pr-review.yml` and `claude-issue-triage.yml`, since the template's first
version — but neither file actually existed. Every scaffolded service has
been telling its owner to set a secret with no workflow that uses it. This
surfaced while checking a plan item ("confirm the Claude GitHub App's
installation scope covers new repos") that turned out to be unanswerable:
there was no workflow to check that scope against.

Two pieces of prior art shaped the fix:

- [`language-teacher`](https://github.com/lukasb27/language-tutor)'s
  `claude-issue-triage.yml` is a proven, live-tested implementation, with
  its own incident history recorded in
  [`docs/github-issue-triage.md`](https://github.com/lukasb27/language-tutor/blob/main/docs/github-issue-triage.md).
  Real, paid runs there found three distinct configuration traps in
  `anthropics/claude-code-action`, all silent or misleading rather than
  erroring clearly:
  1. `max_turns` and `allowed_tools` are **not valid top-level inputs** —
     silently ignored, and an early run defaulted to Opus with no cap,
     costing $0.87 for one issue (23 turns). The model and turn cap have to
     go through `claude_args: "--model X --max-turns N"` instead.
  2. A custom `prompt` puts the action in "automation mode," which posts
     **no comment at all** unless `track_progress: true` is also set —
     tested across four separate attempts, all failed silently or burned
     through the turn cap for nothing.
  3. Once the official [Claude GitHub App](https://github.com/apps/claude)
     is installed, the action authenticates via an OpenID Connect (OIDC)
     token exchange, which requires `id-token: write` in the job's
     `permissions` block — without it, every run fails immediately with
     "Could not fetch an OIDC token."
- The implementation plan's §8 spec for `pr-review.yml`: advisory only,
  never a required check, applying the same three lessons. No prior
  implementation existed to copy from.

## Decision

Built both files into the skeleton
([`backstage-templates` PR #13](https://github.com/lukasb27/backstage-templates/pull/13)),
then revised `pr-review.yml` twice more based on what was actually observed
running it live, not just what was planned:

**`claude-issue-triage.yml`** is copied near-verbatim from `language-teacher`'s
proven version — label-triggered (`needs-triage`/`-sonnet`/`-opus` picks the
model tier), the label removed automatically once a run starts so re-labeling
doesn't re-fire it, `--max-turns 20` as a cost ceiling. This has always been
opt-in per issue, not fired on every `issues: opened` event, to keep spend
predictable — unchanged from the proven design.

**`pr-review.yml`** went through two live revisions after the initial PR
merged:

1. **Automatic → label-triggered**
   ([PR #14](https://github.com/lukasb27/backstage-templates/pull/14)).
   The first version fired on every `opened`/`synchronize`/`ready_for_review`
   event. A cost concern raised immediately after merge — reviewing on every
   push to an actively-iterated PR adds up for no reason if most reviews go
   unread — led to redesigning it to mirror `claude-issue-triage.yml`
   exactly: a `needs-review` label (`-sonnet`/`-opus` for model tier),
   removed once the run starts.
2. **Let Claude find the diff → embed it in the prompt**
   ([PR #15](https://github.com/lukasb27/backstage-templates/pull/15)). The
   real trace from the first live run (a trivial 2-line README change)
   showed the action's own system prompt already lists changed files and
   +/- line counts before any tool call, but not the diff *content* — Claude
   read the whole file just to reconstruct a 2-line change. Reasoned that
   for a larger diff in a bigger file, the same pattern means reading an
   entire file to spot a few changed lines, which is more expensive, not
   less — then verified that reasoning live rather than trusting it. Added
   a step computing `git diff base...head`, truncated to 8000 characters as
   a safety cap against one huge diff blowing up cost the other way, and
   embedded directly in the prompt. Lowered `--max-turns` from 20 to 8 to
   match the smaller expected turn budget.

**Both are advisory only** — `continue-on-error: true`, and deliberately
**not** added to
[`template.yaml`](https://github.com/lukasb27/backstage-templates/blob/main/templates/http-service/template.yaml)'s
`protect-branch` step's `requiredStatusCheckContexts` (which stays `[ci,
docker]`). A check designed to soft-pass on quota, rate limits, and a
missing secret, then made a required check anyway, is a green tick on every
merge's critical path that carries no information.

## Consequences

**Positive:** scaffolded services now actually get the automation the
README always claimed. Confirmed live, not just planned:

- The Claude GitHub App does cover freshly-scaffolded repos — it
  authenticated and posted successfully on a repo created minutes earlier.
- Cost is small and bounded: real runs against a throwaway scaffold
  (`lukas-test-claude-workflows-verify`) came in at $0.045 (6 turns, a
  trivial 2-line diff) and $0.062 (3 turns, a genuinely substantial diff)
  for PR review; $0.087 (22 turns, hit the cap) for a real issue
  investigation.
- The diff-embedding change is a genuine improvement, not just reasoning:
  the same trivial diff took 6 turns before, and a much larger diff with
  four real, deliberately-planted bugs took only 3 turns after — fewer
  turns despite reviewing far more content.
- Review quality holds up: that 3-turn run caught 3 of 4 planted issues
  (mutable default argument, bare `except`, double JSON-encoding) with
  exact file:line references and correct fixes, one independently
  corroborated by `flake8` catching the same bare-except in the same run's
  `ci` job.

**Negative / debt:**

- `claude-issue-triage.yml`'s 20-turn cap was hit on a real investigation
  (22 turns needed) — it still produced a genuinely useful finding via
  `track_progress`'s partial-progress posting, but a more complex issue
  could plausibly get cut off with less to show for it. Accepted as the
  same cost/thoroughness tradeoff `language-teacher` already made, not
  re-litigated here.
- Six labels (`needs-triage`, `-sonnet`, `-opus`, `needs-review`, `-sonnet`,
  `-opus`) are now one-time manual setup per scaffolded repo, on top of the
  three secrets already documented in the README.
- `pr-review.yml`'s diff truncates at 8000 characters. Only tested against
  diffs well under that limit — genuinely large PRs getting a partial diff,
  and what that does to review quality, is unobserved.
- Not independently verified whether `track_progress`'s tracking comment
  gets reused across multiple review runs on the same PR (e.g. re-labeling
  after a later push) or whether each run posts its own — flagged directly
  in `pr-review.yml`'s own comments, unresolved.

## Revisit Trigger

- If the Claude GitHub App's installation is ever found **not** covering a
  new scaffold, that's the moment to check whether it's actually in
  "selected repositories" mode on the `lukasb27` account (this session
  confirmed live that it currently *does* cover new repos, not what its
  underlying configuration is) — see
  [github.com/settings/installations](https://github.com/settings/installations).
- If a real PR's diff is ever observed getting meaningfully truncated at
  8000 characters, or review quality is observed degrading on a large PR,
  reconsider the cap or move to a smarter strategy (e.g. per-file
  summaries instead of one flat diff).
- If `track_progress` is ever observed posting duplicate comments across
  multiple label-triggered runs on the same PR, apply the same
  find-and-update fix already flagged (not yet applied) for
  `post_report_to_pr.py`'s duplicate-comment issue in
  `integration_tests/`.
