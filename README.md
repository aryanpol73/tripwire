# Tripwire

A general-purpose web dark-pattern auditing agent. Tripwire explores a website the way a real
user would, notices manipulative interface and interaction patterns, and produces
reproducible evidence for each one: screenshots, a step-by-step trace, measured numbers and
network logs. It reports findings, never accusations.

Shops, news sites, SaaS products, booking sites and sign-up forms all run through the same
engine. What changes is the **mission** (for example `first_visit` or `sign_up_and_leave`)
and which **detectors** apply.

> **Phase 4 backend.** The scripted walker records evidence for three sandbox missions.
> The v2 hold-out scored **100% Tier A precision and 87.50% recall** on its first run.
> The v1 first run scored 95.24% precision and 83.33% recall.
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

Each audit also writes `report.html` in the run folder: one offline file with the findings,
annotated screenshots, reproduction steps and the measurements behind each one. Rebuild it
from a saved run with:

```bash
uv run tripwire report runs/<run id>
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

## LLM explorer (Phase 6)

For sites nobody scripted, an LLM chooses the actions and code checks each one:

```bash
uv sync --extra llm      # Anthropic; or: uv sync --extra groq
uv run tripwire audit --scenario sneaking-blatant-skin1 --walker llm
uv run tripwire eval --walker llm --record-dir runs/llm-decisions
uv run tripwire eval --walker llm --replay-dir runs/llm-decisions
```

Set `TRIPWIRE_PROVIDER` (anthropic or groq), `TRIPWIRE_MODEL` and that provider's API key in
`.env` first (see `.env.example`). The model must have a price in `src/tripwire/llm/prices.toml`. Each run
stops before a model call that could take its spend past `TRIPWIRE_MAX_LLM_USD` (default
US$0.50). Every decision is recorded in the run folder, so a run can be replayed offline.

## Limitations

Desktop sandbox measurements cover the scripted English-language missions. The real-site
pilot is pending. The report records evidence; it is not a legal verdict.
