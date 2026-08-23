# Day 9: Codex-inspired Web workspace

Day 9 turns the existing CLI-first takeover workflow into a local interface that can be understood and demonstrated
without reading raw JSON. The interface is intentionally a task workspace rather than a generic analytics dashboard.

## Delivered

- A three-column layout for takeover runs, Agent activity, and source evidence.
- Neutral-gray Agent activity so verified, warning, and failed states retain their meaning.
- A repository setup form with provider selection and an explicit runtime-execution toggle.
- A complete `POST /api/v1/repositories/takeover` endpoint backed by `TakeoverCoordinator`.
- A bounded `POST /api/v1/repositories/source` endpoint for evidence line ranges.
- Overview, architecture evidence, learning path, and runtime result tabs.
- Click-through claims that load their verified source location in the inspector.
- A terminal-style runtime panel for command, output, exit code, and repository-change evidence.
- Local recent-run summaries that never persist API keys or full source reports.
- Responsive layouts for desktop, narrower workspaces, and mobile screens.

## Design boundary

The Web app is served by FastAPI with plain HTML, CSS, and JavaScript. It adds no Node build chain and keeps VibeProof a
Python-first project. Model keys stay in server environment variables. Repository and source paths remain confined to
`VIBEPROOF_WORKSPACE_ROOT`, and runtime execution remains opt-in.

The first Web release returns the completed workflow report rather than claiming synthetic per-stage live progress.
While work is in flight, the activity area states that the pipeline is running; after completion it renders the real
stage trace recorded by the coordinator.

## Run locally

```powershell
$env:VIBEPROOF_WORKSPACE_ROOT = 'D:\repositories'
uv run python -m vibeproof serve
```

Open `http://127.0.0.1:8000` and enter a repository path relative to the configured workspace root.

## Verification

- Static page and asset delivery are covered by the API tests.
- The mock-provider API test runs the full scan/index/analyze/learn/runtime-plan/report chain.
- Source evidence tests cover bounded reads and repository traversal rejection.
- Browser QA uses a real headless Edge render at 1440 × 900.
- Full pytest, Ruff, package build, and GitHub Actions remain release gates.
