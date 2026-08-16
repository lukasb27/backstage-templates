# Golden Path Architecture

How a service scaffolded from the `http-service` template actually works end to
end — not the code you write, but the platform machinery underneath it: what
happens on every push, and which repo owns which piece.

## Repositories

| Repo | Holds |
| --- | --- |
| A scaffolded service (this template's output) | Application code, Dockerfile, `k8s/` base, CI |
| [application-argocd-control](https://github.com/lukasb27/application-argocd-control) | The persistent Argo CD `Application` for `main`, and one per open PR, for every scaffolded service |
| This repo (`backstage-templates`) | The `http-service` template itself, and the `ephemeral-env.yml` reusable workflow every scaffolded service's CI calls by version (`@v1`) |

## Request path

A push to a PR branch in a scaffolded service builds and pushes two images to
GHCR (the app image and a test image), then asks the referenced
`ephemeral-env.yml` workflow (this repo, called by version) to render and push
an Argo CD `Application` manifest into the control repo. Argo CD picks that up,
creates a namespace, deploys the app, and runs the integration-test Job as a
`PostSync` hook — only once the Deployment is actually healthy, not racing its
startup.

The integration-test Job talks to the app over its in-cluster Service DNS name,
not through the Ingress — that's real bug surface (the Service `selector` has to
actually match the Deployment's pod labels), and it's the only path a database or
a sibling API could be reached over too.

The `%%{init: ...}%%` block below forces a specific dark theme rather than
relying on the rendering addon's light/dark auto-detection, which renders this
diagram's text unreadable (dark-on-dark) in this instance regardless of the
Backstage UI's own theme.

```mermaid
%%{init: {
  "theme": "base",
  "themeVariables": {
    "background": "#1e1e1e",
    "primaryColor": "#2d3748",
    "primaryTextColor": "#f7fafc",
    "primaryBorderColor": "#718096",
    "lineColor": "#cbd5e0",
    "textColor": "#f7fafc",
    "actorTextColor": "#f7fafc",
    "actorLineColor": "#cbd5e0",
    "signalColor": "#f7fafc",
    "signalTextColor": "#f7fafc",
    "labelBoxBkgColor": "#2d3748",
    "labelBoxBorderColor": "#718096",
    "labelTextColor": "#f7fafc",
    "loopTextColor": "#f7fafc",
    "noteBkgColor": "#4a5568",
    "noteTextColor": "#f7fafc",
    "noteBorderColor": "#718096",
    "activationBkgColor": "#4a5568",
    "activationBorderColor": "#718096"
  }
}}%%
sequenceDiagram
    participant Dev
    participant Svc as Scaffolded service (PR branch)
    participant GHCR
    participant Env as ephemeral-env.yml (@v1, this repo)
    participant Control as application-argocd-control
    participant Argo as Argo CD
    participant K8s as Ephemeral namespace

    Dev->>Svc: push
    Svc->>GHCR: build + push app image, test image
    Svc->>Env: call (needs: ci)
    Env->>Svc: post "pending" status
    Env-->>GHCR: poll until both images exist
    Env->>Control: commit + push rendered Application manifest directly to main
    Control->>Argo: selfHeal picks up the change
    Argo->>K8s: create namespace, deploy app
    K8s-->>Argo: Deployment becomes healthy
    Argo->>K8s: run integ-test Job (PostSync hook)
    K8s->>Svc: post real pass/fail status + PR comment
```
