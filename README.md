# PM Loop — Structured Disagreement as a Quality Mechanism for Knowledge Work

> Software engineering has test suites. Knowledge work has vibes.
> PM Loop is nine AI agents that argue with each other until your documents are good.

[![License: Non-Commercial](https://img.shields.io/badge/License-Non--Commercial-red.svg)]
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

## What is this?

PM Loop is a multi-agent pipeline that processes PM deliverables (PR/FAQs, competitive briefs, status reports, etc.) through a directed graph of AI agents with **opposing incentives**. The key insight is not "AI writes documents" — it's that a **topology of disagreement** forces quality convergence through:

- **Adversarial review** — agents that want to find problems, not approve them
- **Typed feedback arcs** — rejected work routes back to the *origin* of the defect, not just "try again"
- **Backpressure** — every agent must produce structured evidence, not just a verdict
- **An observer** — Grandpa watches the pipeline and tunes it using the scientific method

📖 **Read the full paper:** [PM Loop: Structured Disagreement as a Quality Mechanism for Knowledge Work](PAPER.md)

## Architecture

```
  ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
  │ MARGE  │───▶│ NELSON │───▶│  LISA  │───▶│  BOB   │───▶│ HOMER  │
  │ Intake │    │ Enrich │    │  Spec  │    │Adversar│    │ Draft  │
  └────────┘    └────────┘    └───▲────┘    └────┬───┘    └───┬────┘
                                  │              │            │
                                  │   spec_revision           │
                                  └──────────────┘            │
                                                              ▼
  ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
  │ MAGGIE │◀───│  YOU   │◀───│  CBG   │◀───│ PATTY  │◀───┤        │
  │Publish │    │  Gate  │    │UX Check│    │ Review │    │        │
  └────────┘    └───┬────┘    └───┬────┘    └───┬────┘    │        │
                    │         ux_fix  │    draft_fix │     │        │
                    │   ┌─────────────┘    ┌────────┘     │        │
                    │   └──────────────────┴─────────────▶│ HOMER  │
                    │                                      └────────┘
             human_rework → Homer
             human_respec → Lisa

  👴 GRANDPA (Observer) — watches, tunes, complains
```

**Why Simpsons characters?** Because "Bob rejected it" is instantly memorable. Each character was chosen to match their TV personality: Lisa is meticulous (spec writing), Sideshow Bob is adversarial by nature, Homer does the work, Patty has impossibly high standards, Comic Book Guy can block on vibes, and Grandpa watches everything and complains constantly.

## Quick Start

### Prerequisites

- Python 3.10+
- An LLM API (Claude, GPT-4, Llama, etc.) — the agents are prompt-based, so any capable model works

### Install

```bash
git clone https://github.com/kphatak001/pm-loop.git
cd pm-loop
```

No dependencies beyond Python stdlib. Install optional LLM backends as needed:

```bash
pip install anthropic   # for Claude
pip install openai      # for GPT-4, etc.
```

### Usage

```bash
# Add a task to the pipeline
python runner.py add "Write Q2 competitive brief on a competitor's agentic strategy" \
  --type competitive_brief --stakeholders "VP leadership" --deadline "2026-04-15"

# See pipeline status
python runner.py status

# Run one cycle (dry run — shows what would execute)
python runner.py cycle

# Run one cycle (execute with auto-detected LLM backend)
python runner.py cycle --execute

# Run one cycle with a specific backend
python runner.py cycle --execute --backend anthropic
python runner.py cycle --execute --backend openai
python runner.py cycle --execute --backend echo      # testing — auto-passes everything

# Generate prompt for a single task (without executing)
python runner.py run <task-id>

# Feed agent results back into the pipeline
python runner.py advance <task-id> --verdict pass --evidence "All ACs met, 5 sources cited"
python runner.py advance <task-id> --verdict reject --evidence "Missing competitor data" --arc draft_fix

# Run Grandpa's observer (detects stuck tasks, tunes config)
python runner.py observe
```

### LLM Backend

`cycle --execute` calls your LLM and feeds results back automatically. The backend is auto-detected from environment variables:

| Env var | Backend |
|---------|---------|
| `ANTHROPIC_API_KEY` | Claude (default model: claude-sonnet-4-20250514) |
| `OPENAI_API_KEY` | GPT-4o |

Or specify explicitly with `--backend`. For custom backends, subclass `Executor` in `executor.py`.

### Example Output

```
============================================================
  PM LOOP STATUS — 3 tasks in pipeline
============================================================

  [DRAFT] Homer — 1 task(s)
    • pm-1234-ab12: Q2 Competitive Brief [iter:5] (↩ 1 arcs)

  [REVIEW] Patty — 1 task(s)
    • pm-5678-cd34: Weekly Digest [iter:3]

  [HUMAN_GATE] You — 1 task(s)
    • pm-9012-ef56: Launch PRFAQ [iter:8] (↩ 2 arcs)
```

## Task Types & Pipeline Variants

| Pipeline | Stages | Task Types | Quality Bar |
|----------|--------|------------|-------------|
| **Full 8-stage** | Intake → Enrich → Spec → Adversarial → Draft → Review → UX → Gate | `prfaq`, `competitive_brief`, `roadmap_plan`, `decision_doc`, `one_pager`, `post_mortem`, `customer_experience`, `launch_checklist` | 0.8 |
| **6-stage** | Intake → Enrich → Draft → Review → UX → Gate | `status_report`, `meeting_prep`, `weekly_digest` | 0.6 |
| **4-stage** | Intake → Enrich → Draft → Review → Gate | `ticket_response`, `email_draft` | 0.5 |

Adding a new task type: add an entry to `task_types` in `loop_config.json` with stages and quality threshold. No code changes needed.

## Feedback Arcs

| Arc | From → To | What it encodes |
|-----|-----------|-----------------|
| `spec_revision` | Bob → Lisa | Spec defect. Fix the blueprint, not the building. |
| `draft_fix` | Patty → Homer | Execution defect. The plan was fine, the output wasn't. |
| `ux_fix` | CBG → Homer | Experience defect. Technically correct but confusing. |
| `ux_triage` | CBG → Marge | Scope defect. New work discovered, not a fix. |
| `human_rework` | You → Homer | Strategic defect. Human judgment overrides. |
| `human_respec` | You → Lisa | Requirements defect. The spec was wrong. |

## Project Structure

```
pm-loop/
├── orchestrator.py      # Task model, Stage enum, feedback arcs, advance_task(), Observer
├── runner.py            # CLI: add, run, cycle, advance, status, observe
├── executor.py          # Pluggable LLM backends (Anthropic, OpenAI, Echo)
├── loop_config.json     # Grandpa's tunable config (pipelines, thresholds, publish routes)
├── pyproject.toml       # Python 3.10+, optional deps, entry point
├── agents/
│   ├── __init__.py
│   └── prompts.py       # 9 agent prompt definitions (the actual agent logic)
├── queue/               # Active task JSON files (one per task, state machine)
│   └── done/            # Auto-archived completed tasks
├── evidence/            # Agent output artifacts (drafts, reviews, scores)
├── observer-reports/    # Grandpa's observation history
├── PAPER.md             # Full paper: architecture, results, analysis
└── LICENSE
```

The core is ~500 lines of Python across three files. The agents are LLM prompts with structured JSON output schemas. The state is JSON files. No framework, no database, no infrastructure beyond "Python + an LLM API."

## How It Works

1. **You add a task** — Marge classifies it, selects the pipeline variant, creates the task file
2. **Nelson enriches** — gathers context, sources, data. Every fact needs a URL.
3. **Lisa writes the spec** — acceptance criteria, structure, quality bar, anti-patterns
4. **Bob attacks the spec** — finds gaps. Rejects back to Lisa via `spec_revision` until it's airtight
5. **Homer drafts** — follows the spec exactly, maps every AC to a section
6. **Patty reviews** — scores 7 dimensions, minimum score = overall score. Below threshold? `draft_fix` back to Homer
7. **CBG simulates the stakeholder** — walks a 6-step journey. Can block on vibes. Files non-blocking issues via `ux_triage`
8. **You approve at the gate** — see the brief, evidence chain, scores, feedback history
9. **Maggie publishes** — routes to the right destination

**Grandpa watches everything** — counts tasks by stage, tracks which feedback arcs fire, detects stuck loops, makes one config tweak at a time, waits two cycles to measure the effect.

## Configuration

Grandpa tunes `loop_config.json` — and now he actually writes changes back:

```json
{
  "max_spec_revisions": 3,
  "max_draft_reworks": 3,
  "max_total_iterations": 10,
  "quality_threshold": 0.7,
  "auto_publish": false,
  "parallel_docs": true,
  "task_types": {
    "prfaq": {
      "stages": ["intake", "enrich", "spec", "adversarial", "draft", "review", "ux_check", "human_gate", "publish"],
      "quality_threshold": 0.8,
      "publish": {"primary": "docs", "notify": "chat"}
    },
    "ticket_response": {
      "stages": ["intake", "enrich", "draft", "review", "human_gate", "publish"],
      "quality_threshold": 0.5
    }
  }
}
```

Per-type overrides in `task_types` take precedence over the global defaults. The Observer auto-tunes:

| Signal | Action | Guard |
|--------|--------|-------|
| All tasks passing first try | Raise `quality_threshold` +0.05 | Cap at 0.95 |
| >60% tasks stuck in draft rework | Lower `quality_threshold` -0.05 | Floor at 0.4 |
| >60% tasks hitting spec_revision | Bump `max_spec_revisions` +1 | Cap at 6 |

One change at a time. Two-cycle cooldown between changes. Every tweak is logged in `observer-reports/`.

## Cost & Performance

- **Full pipeline:** 8–15 LLM calls per task, $0.50–$2.00 at current model pricing
- **Wall clock:** 3–8 minutes for full pipeline, <1 min for 4-stage
- **Composable depth** keeps costs proportional — don't use 8 stages for a 3-line email

## Acknowledgments

PM Loop draws from the **Grandpa Loop** (Joshua Samuel, 2025) — adversarial multi-agent orchestration with observer-based tuning — and the **AI SDLC** methodology — composable stage routing and scheduled factory model.

## License

see [LICENSE](LICENSE).

---

*If you build something with this pattern, I'd love to hear about it. The topology of disagreement is the interesting part — the specific agents are just one instantiation.*
