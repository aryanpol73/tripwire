# Tripwire

A general-purpose web dark-pattern auditing agent. Tripwire explores a website the way a real
user would, notices manipulative interface and interaction patterns, and produces
reproducible evidence for each one: screenshots, a step-by-step trace, measured numbers and
network logs. It reports findings, never accusations.

Shops, news sites, SaaS products, booking sites and sign-up forms all run through the same
engine. What changes is the **mission** (for example `first_visit` or `sign_up_and_leave`)
and which **detectors** apply.

> **Phase 4 backend.** The scripted walker records evidence for three sandbox missions.
> Eleven rules evaluate the traces and write findings. The independent hold-out is pending.
> Live audits remain limited to the local sandbox.

## How it works

```
Mission  ->  Walker  ->  Trace  ->  Detectors  ->  Findings  ->  Report
(YAML)      (browser)    (JSON)    (pure code)    (JSON)        (static HTML)
```

v1 pattern families: **consent and choice asymmetry**, **sneaking and hidden extras**,
**obstruction**. See [docs/SPEC.md](docs/SPEC.md).

## Quickstart (Phase 0)

Needs [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/aryanpol73/tripwire.git
```

```bash
cd tripwire && uv sync
```

```bash
uv run playwright install chromium
```

```bash
uv run pytest
```

On Windows, keep the checkout path short (for example `C:\code\tripwire`): very long paths stop
Playwright from loading one of its DLLs.

```bash
uv run tripwire --version
```

Browse the sandbox (see [sandbox/evilweb](sandbox/evilweb/README.md)):

```bash
uv run evilweb list
```

```bash
uv run evilweb serve consent_asymmetry-blatant-skin1
```

Run a mission on a sandbox scenario, then read the saved trace back without a browser:

```bash
uv run tripwire audit --scenario obstruction-blatant-skin1
```

```bash
uv run tripwire replay runs/<run id>
```

Optional, for contributors:

```bash
uv run pre-commit install
```

## Docs

- [SPEC](docs/SPEC.md): missions, walker, trace, detectors, findings, and the v1 rules
- [ETHICS](docs/ETHICS.md): safety rules, where each is enforced, responsible disclosure
- [DECISIONS](docs/DECISIONS.md): every design decision and its alternatives
- [NOTEBOOK](docs/NOTEBOOK.md): per-phase notes, risks and interview Q&A

## Evaluate the detectors

```bash
uv run tripwire eval
uv run tripwire eval --repeat 3 --jobs 4
```

The first command scores all 36 labeled scenarios. The second compares findings across
three independent runs per scenario. Each audit writes `findings.json` alongside its trace.
The independent fixture format and the measured development results are in
[the Phase 4 notebook](docs/NOTEBOOK.md#phase-4-backend--detectors-and-evaluation).

## Limitations

Desktop sandbox measurements cover the scripted English-language missions. The independent
hold-out, evidence report, and real-site pilot are pending.
