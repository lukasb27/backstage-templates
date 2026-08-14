# Contributing

## Conventional Commits

Every PR title and every commit subject must match:

```
(build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test)(\(scope\))?!?: description
```

CI validates both — a PR with a non-conforming title, or containing a commit with a
non-conforming subject, fails `ci`.

## Branching

Branch from `main`. Don't stack branches on top of other unmerged branches — rebase
onto `main` instead.

## Merging

This repo is squash-merge only (`allowMergeCommit`/`allowRebaseMerge` are disabled at
the repo level). The squash commit uses the **PR title**, not the first commit's
message — this is load-bearing for release-please, which reads the commit subject on
`main` to decide the next version and changelog entry.

## Branch protection

`requiredApprovingReviewCount: 0` and `protectEnforceAdmins: false` are deliberate, not
an oversight — see this repo's `catalog-info.yaml` template-version annotation and
[backstage-templates](https://github.com/lukasb27/backstage-templates)'s
`template.yaml` for why: with one maintainer, the GitHub default (`enforce_admins:
true` + require 1 approval) makes every PR permanently unmergeable, since GitHub won't
let you approve your own PR.
