# backstage-templates

Backstage Software Templates for the golden path. Currently ships one template:

- **[http-service](../templates/http-service/template.yaml)** — a long-running
  HTTP service with CI, Docker build, and per-PR ephemeral Argo CD environments
  wired in from the start.

See [Architecture](architecture.md) for how a scaffolded service actually works
end to end — the platform machinery underneath the code you write. See
[Platform Overview](platform-overview.md) for how this repo fits into the wider
system — all five repos involved, and why there are two separate Argo CD
control repos.
