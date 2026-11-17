# Tripwire

A general-purpose web dark-pattern auditing agent. Tripwire explores a website the way a real
user would, notices manipulative interface and interaction patterns, and produces
reproducible evidence for each one: screenshots, a step-by-step trace, measured numbers and
network logs. It reports findings, never accusations.

Shops, news sites, SaaS products, booking sites and sign-up forms all run through the same
engine. What changes is the **mission** (for example `first_visit` or `sign_up_and_leave`)
and which **detectors** apply.

> **Status: Phase 0 (setup and spec).** The data contracts, fixtures and docs exist. The
> sandbox, browser layer, walkers, detectors and reports are not built yet. Nothing has been
> run against any website.

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
uv run pytest
```

```bash
uv run tripwire --version
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

## Limitations (current)

- No detector, walker or report exists yet, so there are no precision or recall numbers.
- Desktop web only.
