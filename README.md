<p align="center">
  <img src="docs/images/title.gif" alt="MotionProof replaying a real 1000-assembly experiment: each virtual assembly lands on a backlash versus direction-error plot, failures in red, while the pass rate and its 95 % interval settle" width="100%">
</p>

<p align="center">
  <b>What happens to your mechanism's motion when the parts come off the machine slightly wrong?</b>
</p>

<p align="center">
  <a href="LICENSE"><img alt="MIT licence" src="https://img.shields.io/badge/licence-MIT-2f6f4f"></a>
  <img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-3b5b92">
  <img alt="MuJoCo 3.14" src="https://img.shields.io/badge/physics-MuJoCo%203.14-555">
  <img alt="tests" src="https://img.shields.io/badge/tests-300%20%2B%2014%20e2e-2f6f4f">
  <img alt="benchmarks" src="https://img.shields.io/badge/benchmarks-13%2F14%20pass-2f6f4f">
</p>

MotionProof builds **virtual as-manufactured copies** of a CAD assembly from its tolerance
specification, simulates each one on MuJoCo with a drive train that has backlash, stiffness and
friction, and tells you **which copies fail, how often, and which tolerances are to blame**.

| 1 | 2 | 3 | 4 |
|:--|:--|:--|:--|
| **Import** a STEP, STL, URDF or MJCF model | **Specify** limits, distributions and fits | **Simulate** hundreds to thousands of variants | **Rank** the tolerances that drive failures, then find the cheapest set that still passes |

> [!NOTE]
> Results are model predictions, conditional on the geometry, tolerances and drive-train values you
> supply, not a certification. Every value is marked `specified`, `assumed` or `measured`. No
> physical measurement has been made yet; see [verification](docs/verification.md).

## A real run

<p align="center"><img src="docs/images/results.png" alt="Results of a 1000-assembly reversal experiment: scatter of backlash against direction error with failures in red, input sensitivity ranking, and the error distribution against its 2 mm limit" width="100%"></p>

The reference elbow (a NEMA 17 motor and a two-stage 33:1 planetary gearbox), 1000 virtual
assemblies reversing the joint:

* **73.9 % pass** (95 % interval 71.1 to 76.5 %); 261 miss a requirement.
* Almost all failures (259 of 261) are a direction error above 2 mm.
* Output friction and the stage 2 planet bearing clearance drive the error most.

## How it works

```mermaid
flowchart LR
    A[CAD / URDF / MJCF] --> B[Model<br/>features, datums,<br/>tolerances, fits, gears]
    B --> C[Sampling<br/>Monte Carlo, LHS, Sobol,<br/>copula correlations]
    C --> D[Virtual assemblies<br/>fits, radial play, tilt,<br/>planetary backlash]
    D --> E[MuJoCo + drive train<br/>motor, dead band,<br/>stiffness, friction]
    E --> F[Statistics<br/>pass rate, intervals,<br/>sensitivity, worst case]
    F --> G[Optimise<br/>least-cost tolerances,<br/>verified reliability]
    S[3D scans /<br/>measured parts] -.-> D
    H[Hardware rig] -.-> F
```

## The app

<p align="center"><img src="docs/images/workflow-tour.gif" alt="Tour of the MotionProof application: project, assembly workbench, tolerances, virtual assemblies, robustness, sensitivity, model trust and benchmarks" width="860"></p>

29 screens, a REST API, a CLI and a [Python SDK](docs/python-sdk.md). Dark and light themes.
Accounts keep their own workspaces. [All features](docs/features.md).

## Quick start

With [Docker](https://docs.docker.com/get-docker/), no Python or Node needed:

```bash
docker run --rm -p 127.0.0.1:8000:8000 -e MOTIONPROOF_LOCAL=1 -v motionproof-data:/data ghcr.io/capedcrusader77/motionproof
```

Then open http://127.0.0.1:8000. (To build the image yourself: `docker build -t motionproof .`)

Keep the `127.0.0.1:` in front of the port: with `MOTIONPROOF_LOCAL=1` there is no sign-in.

Or from source: Python 3.12 with [`uv`](https://docs.astral.sh/uv/), Node 24 for the web app.

```bash
uv sync
cd frontend && npm ci && npm run build && cd ..
uv run motionproof serve --home workspace
```

Open http://127.0.0.1:8000. There is no sign-in on your own computer, and a **Demo** project is
made on the first start: the reference design and a 64-scenario experiment, computed on your
machine in about a minute. Open **Robustness** to see which virtual assemblies fail. From the command line:
`uv run motionproof reference create demo`.

## Limitations

* **No physical measurement yet.** The reference design is synthetic and several of its values
  are assumed. The rig procedure, with predictions recorded before measuring, is in
  [docs/rig-build-and-test.md](docs/rig-build-and-test.md); it has not been carried out.
* **External validation is mixed.** Against public data from other robots: 3 pass, 2 fail, 1
  with too little data ([results](EXTERNAL_VALIDATION_RESULTS.md)). X1, X4 and X5 are revised
  protocols written after their first versions failed, each adding one physical effect the
  residuals showed missing; they are not blind. X1 and X4 now pass, X5 still fails. A further, non-blind check against a published
  3D-printed planetary gearbox also fails: the model predicts 1.4 to 5.5 mrad of backlash where
  10.3 mrad was measured (X7).
* **Reduced-order physics.** Rigid bodies and a drive train with backlash, stiffness and
  friction; no gear-tooth or bearing contact, deformation, heat or wear.
* **Narrower than a CAD tool.** Only revolute joints can be driven; geometric tolerances are
  scalar deviations, not full GD&T zones.

All of them: [engineering limitations](docs/engineering-limitations.md),
[development status](docs/development-status.md).

## Go deeper

| | |
|:--|:--|
| [Features](docs/features.md) | Everything the tool does, by area |
| [Python SDK](docs/python-sdk.md) | The same experiment from Python |
| [Verification](docs/verification.md) | Benchmarks, tests, external validation, what is not proven |
| [Project report](docs/project-report.md) | The whole system in one document |
| [Architecture](docs/architecture.md) | Packages and design decisions |
| [Getting started](docs/getting-started.md) | A guided first session |
| [Development](docs/development.md) · [Contributing](CONTRIBUTING.md) | Lint, types, tests, e2e |
| [Hosting](docs/hosting.md) | Where to run it and how to run it safely |
| [Security](SECURITY.md) · [Changelog](CHANGELOG.md) | Accounts and sessions; release notes |

[MIT licence](LICENSE).
