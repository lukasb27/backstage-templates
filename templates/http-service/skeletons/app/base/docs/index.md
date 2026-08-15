# ${{ values.name }}

${{ values.description }}

This is a long-running HTTP service, scaffolded from the `http-service` golden-path
template (`goldenpath.lukasb27/template-version: ${{ values.template_version }}`).

## What you get

- CI (unit tests, lint, Conventional Commit validation) on every PR
- A Docker build (app image + a separate integration-test image) on every push
- A per-PR ephemeral Argo CD environment, torn down when the PR closes
- A persistent environment on `main`, managed in
  [application-argocd-control](https://github.com/lukasb27/application-argocd-control)
- This page, via TechDocs

## Local development

See [Architecture](architecture.md) for how the pieces fit together, and the repo's
`README.md` for exact local-run commands.
