---
title: "PM Loop: Structured Disagreement as a Quality Mechanism for Knowledge Work"
subtitle: "Why nine AI agents that argue with each other produce better documents than one agent that agrees with itself"
author: "Kaustubh Phatak"
date: 2026-04-20
estimated_read_time: "20 min"
tags: [multi-agent, AI, product-management, quality, adversarial-review, agentic-systems]
github: "https://github.com/kphatak001/pm-loop"
---

# PM Loop: Structured Disagreement as a Quality Mechanism for Knowledge Work

*Software engineering has test suites. Knowledge work has vibes. PM Loop is an attempt to fix that — nine AI agents with opposing incentives, connected by typed feedback arcs, that converge on document quality the way automated tests converge on code correctness. The mechanism isn't better AI writing. It's a topology of disagreement.*

---

## Abstract

Software engineering solved its quality problem with automated tests: write assertions, run them, the code passes or fails. Knowledge work has no equivalent. A competitive brief, a PR/FAQ, or a strategy document is "good" if a human reads it and thinks so, which is slow, subjective, and inconsistent.

PM Loop introduces structured adversarial review with typed feedback arcs as the equivalent of a test suite for documents. Nine AI agents with opposing incentives process PM deliverables through a directed graph where edges carry quality signals and nodes disagree with each other by design. The mechanism is not better AI writing. It is a topology of disagreement that forces quality convergence through mandatory evidence, defect-aware routing, and an observer that tunes the system using the scientific method.

We describe the architecture, present results from three production tasks, and analyze the defect-catch patterns that emerge from adversarial topology versus single-pass review. The full source code is [available on GitHub](https://github.com/kphatak001/pm-loop).

## 1. The Quality Gap in Knowledge Work

Software engineers write tests. When a function returns the wrong value, the test fails, the engineer fixes it, and the test passes. The feedback loop is tight, objective, and automated. Quality is a property of the system, not of the engineer's mood on a given morning.

Product managers write documents. When a competitive brief misses a key competitor, or a PR/FAQ buries the customer problem in paragraph three, or a status report omits the one metric the VP will ask about, there is no test that fails. The feedback loop is a human reading the document days later and saying "this doesn't work." By then, the meeting has happened, the decision has been made, or the stakeholder has lost confidence.

AI writing tools make this worse, not better. They produce fluent first drafts quickly, which creates the illusion of quality. The PM skims the output, sees that it reads well, and ships it. The structural problems — missing evidence, wrong audience framing, buried insight — survive because fluency masks them. A well-written bad document is harder to catch than a poorly-written bad document.

The problem is not drafting. The problem is judgment. Specifically: who checks the work, what they check for, and what happens when they find a problem.

## 2. The Core Idea: Topology of Disagreement

PM Loop's contribution is not "AI agents write documents." It is a specific arrangement of agents with opposing objectives, connected by typed feedback arcs that route defects to the agent responsible for fixing them.

This is distinct from three common multi-agent patterns:

**Chain-of-thought** uses one agent reasoning sequentially. There is no disagreement. The agent that writes the draft is the same agent that evaluates it, which means it has no incentive to find its own flaws.

**Ensemble methods** use multiple agents on the same task and vote on the output. There is disagreement, but it is undirected. The agents don't know *why* they disagree, and the resolution mechanism (majority vote, best-of-N) discards the signal in the disagreement.

**Hierarchical delegation** uses a manager agent that assigns subtasks to workers. The manager evaluates the output, but the evaluation is one-dimensional: did the worker do what I asked? There is no adversarial tension.

PM Loop uses a fourth pattern: **adversarial topology**. Agents are arranged in a directed graph where specific pairs have opposing incentives. Lisa wants to produce a complete spec. Sideshow Bob wants to find gaps in it. Homer wants to produce a polished document. Patty wants to find weaknesses. Comic Book Guy wants to find confusion.

> **Why Simpsons characters?**[^1] Because "Bob rejected it" is instantly memorable in a way that "the adversarial spec reviewer rejected the document" is not. When you're debugging a pipeline at 11 PM and Homer and Patty are stuck in a feedback loop, you want names that carry personality. Names create intuition. Intuition creates faster debugging. And frankly, "Comic Book Guy blocked the brief because the VP would be confused" is a sentence that writes itself.

[^1]: The naming convention comes from the Grandpa Loop architecture (Samuel, 2025), which introduced adversarial multi-agent orchestration with observer-based tuning. Each character was chosen to match their personality in the show: Lisa is meticulous and thorough (spec writing), Sideshow Bob is adversarial by nature, Homer is the everyman who does the work, Patty is judgmental and unimpressed, and Comic Book Guy has *impossibly* high standards for the things he cares about. Grandpa watches everything, complains constantly, and occasionally says something genuinely wise.

The critical design element is the feedback arcs. When Bob rejects a spec, the work routes back to Lisa, not to Homer. This encodes the insight that a spec defect cannot be fixed by better drafting. When Patty rejects a draft, the work routes back to Homer, not to Lisa. This encodes the insight that a drafting defect does not mean the spec was wrong. The routing carries information about defect origin.

Six typed arcs form the topology:

| Arc | From → To | What it encodes |
|-----|-----------|-----------------|
| `spec_revision` | Bob → Lisa | Spec defect. Fix the blueprint, not the building. |
| `draft_fix` | Patty → Homer | Execution defect. The plan was fine, the output wasn't. |
| `ux_fix` | Comic Book Guy → Homer | Experience defect. Technically correct but confusing. |
| `ux_triage` | Comic Book Guy → Marge | Scope defect. New work discovered, not a fix. |
| `human_rework` | Human → Homer | Strategic defect. Human judgment overrides automated review. |
| `human_respec` | Human → Lisa | Requirements defect. The spec itself was wrong. |

In code, the feedback arcs are a simple dictionary. The routing logic is the Lissajous curve — non-linear, with crossings that create convergence pressure:

```python
# The Lissajous curve in code — feedback arcs are just a routing table
FEEDBACK_ARCS = {
    "spec_revision":  {"from": Stage.ADVERSARIAL, "to": Stage.SPEC,   "reason": "Spec gaps found"},
    "draft_fix":      {"from": Stage.REVIEW,      "to": Stage.DRAFT,  "reason": "Quality below bar"},
    "ux_fix":         {"from": Stage.UX_CHECK,     "to": Stage.DRAFT,  "reason": "Stakeholder flow broken"},
    "ux_triage":      {"from": Stage.UX_CHECK,     "to": Stage.INTAKE, "reason": "New work discovered"},
    "human_rework":   {"from": Stage.HUMAN_GATE,   "to": Stage.DRAFT,  "reason": "Human requested changes"},
    "human_respec":   {"from": Stage.HUMAN_GATE,   "to": Stage.SPEC,   "reason": "Human changed requirements"},
}
```

Work doesn't just "go back and try again." It goes back to the specific point where the defect originated, with the specific signal about what went wrong. The `advance_task` function is the entire routing engine:

```python
def advance_task(task: Task, verdict: str, evidence_details: str,
                 feedback_arc: str = None) -> Task:
    """Advance a task to the next stage, or route through a feedback arc.

    This is the core routing logic — the Lissajous curve in code.
    """
    agent = STAGE_AGENTS.get(task.stage, "system")
    task.iterations += 1

    if feedback_arc and feedback_arc in FEEDBACK_ARCS:
        arc = FEEDBACK_ARCS[feedback_arc]
        task.record_feedback(feedback_arc, arc["reason"])
        task.add_evidence(task.stage, agent, "rejected", evidence_details)
        task.stage = arc["to"]
    elif verdict == "blocked":
        task.add_evidence(task.stage, agent, "blocked", evidence_details)
        task.stage = Stage.BLOCKED
    else:
        task.add_evidence(task.stage, agent, "passed", evidence_details)
        task.stage = next_stage(task.stage, task.task_type)

    task.save()
    return task
```

That's it. Twenty lines of routing logic, and the entire adversarial topology falls out of the data structures.

## 3. The Architecture

Here's the full pipeline. The forward path flows left-to-right across the top, then right-to-left across the bottom. The feedback arcs cross back to earlier stages. Grandpa watches everything and, like his namesake, complains constantly.

```
  ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
  │ MARGE  │───▶│ NELSON │───▶│  LISA  │───▶│  BOB   │───▶│ HOMER  │
  │ Intake │    │ Enrich │    │  Spec  │    │Adversar│    │ Draft  │
  └────────┘    └────────┘    └───▲────┘    └────┬───┘    └───┬────┘
                                  │              │            │
                                  │   ╔══════════╝            │
                                  │   ║ spec_revision         │
                                  ╚═══╝                       │
                                                              ▼
  ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
  │ MAGGIE │◀───│  YOU   │◀───│  CBG   │◀───│ PATTY  │◀───┤        │
  │Publish │    │  Gate  │    │UX Check│    │ Review │    │        │
  └────────┘    └───┬────┘    └───┬────┘    └───┬────┘    │        │
                    │             │              │         │        │
                    │   ╔═════════╝    ╔═════════╝         │        │
                    │   ║ ux_fix       ║ draft_fix         │        │
                    │   ╚══════════════╩══════════════════▶│ HOMER  │
                    │                                      └────────┘
             ╔══════╩══════╗
             ║ human_rework║  (you send Homer back to the drawing board)
             ║ human_respec║  (you tell Lisa the requirements were wrong)
             ╚═════════════╝

  👴 GRANDPA (Observer) — Watches the pipeline, not the deliverables
     • Counts tasks by stage (where are they piling up?)
     • Tracks feedback arcs (converging or oscillating?)
     • Detects stuck tasks (3+ iterations → escalate to human)
     • Tunes config one variable at a time, observes for two cycles
     • Complains constantly ("Lisa and Bob have been arguing all day.")
```

The key insight: Marge, Nelson, Lisa, Bob, Homer, Patty, Comic Book Guy (CBG), and Maggie process tasks. You (the human) approve or reject at the gate. Grandpa watches the whole system and tunes it. Nine agents + one observer + one human = the full topology.

Shorter pipelines skip the middle:

```
  Full 8-stage:  Marge → Nelson → Lisa → Bob → Homer → Patty → CBG → You → Maggie
  6-stage:       Marge → Nelson → Homer → Patty → CBG → You → Maggie
  4-stage:       Marge → Nelson → Homer → Patty → You → Maggie
```

In code, pipeline selection is a one-line dictionary lookup:

```python
TASK_PIPELINES = {
    "prfaq":              _FULL,        # Full 8-stage — VP audience, needs adversarial review
    "competitive_brief":  _FULL,        # Claims need rigorous evidence
    "decision_doc":       _FULL,        # High-stakes — worth the full topology
    "status_report":      _SIX_STAGE,   # Standardized format, skip spec+adversarial
    "meeting_prep":       _SIX_STAGE,   # Lighter pipeline
    "ticket_response":    _FOUR_STAGE,  # Quick-turn, skip adversarial + UX
    "email_draft":        _FOUR_STAGE,  # Just draft, review, gate
}
```

## 4. Backpressure: The Enforcement Mechanism

A topology of disagreement is useless if agents can pass work downstream without evidence. "Looks good" from a reviewer is not a quality signal. It is the absence of one.

PM Loop enforces backpressure at every node. Each agent must produce structured evidence, not just a verdict. Every agent returns the same JSON contract:

```python
{
    "verdict": "pass|reject|blocked",
    "evidence": "what you checked/found (with source URLs)",
    "output": { ... },  # The agent's deliverable for this stage
    "feedback_arc": null,  # or "arc_name" if rejecting
    "confidence": 0.0-1.0
}
```

The evidence chain makes the system auditable. Here's how each agent enforces it — straight from their prompt definitions:

- **Marge** (intake): *"You must cite the source of the request (email, meeting, Slack) as evidence. No phantom tasks."*
- **Nelson** (enrichment): *"Every piece of context must have a source URL or reference. No 'I believe' or 'generally speaking.' Facts with citations only."*
- **Lisa** (spec): *"Every AC must map to a verifiable check in the spec."*
- **Sideshow Bob** (adversarial): *"You must list every check you performed, even the ones that passed. 'Looks good' is not evidence. Enumerate what you verified."* — Bob takes genuine pleasure in finding flaws. His prompt says so explicitly.
- **Homer** (draft): *"For each acceptance criterion, note where in the draft it's satisfied. Map AC → section/paragraph. If an AC can't be met, explain why and flag for human."*
- **Patty** (review): Scores across seven dimensions. *The overall score is the minimum, not the average.* A document scoring 0.95 on six dimensions and 0.3 on evidence is a 0.3 document. Patty has zero patience and impossibly high standards — exactly what you want in a reviewer.
- **Comic Book Guy** (stakeholder sim): Must walk a six-step stakeholder journey. *"Don't just say 'stakeholder would be confused.' Say WHERE and WHY."* CBG can block on vibes — if the deliverable technically meets all criteria but would confuse a VP reading it at 7am, that's a valid rejection. *Worst. Deliverable. Ever.* (Unless it's actually good.)

And then there's **Maggie** — the publisher. *"You don't say much. You just get it done."* She takes the approved deliverable and routes it to the right destination. No opinions. No feedback. Just delivery.

This creates a traceable evidence chain from raw input to published deliverable. For any claim in the final document, you can trace: which source Nelson found it in, whether Bob verified the spec required it, whether Patty checked it, and what score it received.

## 5. The Observer: Scientific Method for Pipeline Tuning

The tenth agent, Grandpa, does not process tasks. He watches the pipeline and tunes it. Like his namesake, he's been around long enough to know when something's off — and he's not shy about saying so.

Every cycle, Grandpa measures: tasks by stage (where are they piling up?), feedback arc frequency (which disagreements fire most?), convergence rate (does a rejected task pass on the next attempt, or oscillate?), and stuck tasks (same stage for 3+ iterations).

```python
class Observer:
    """Grandpa: watches the loop, tunes it, complains constantly."""

    def observe(self, tasks: list[Task]) -> dict:
        # ... measurement logic ...

        # Grandpa's complaints (the best part)
        if report["by_stage"].get(Stage.BLOCKED, 0) > 2:
            report["complaints"].append(
                "Back in my day, we didn't have three tasks blocked at once. "
                "Someone fix this.")
        if all_arcs.get("spec_revision", 0) > 5:
            report["complaints"].append(
                "Lisa and Bob have been arguing all day. "
                "Maybe the requirements are just bad.")
        if not tasks:
            report["complaints"].append(
                "Nothing in the queue. I'm going back to sleep.")
```

The complaints are a joke, but the tuning is not. Grandpa makes one configuration change at a time and waits two cycles to observe the effect. This is the scientific method applied to system tuning: observe, hypothesize, change one variable, measure. Changing multiple variables simultaneously makes it impossible to attribute outcomes to causes.

The configuration file Grandpa tunes is deliberately small:

```json
{
  "max_spec_revisions": 3,
  "max_draft_reworks": 3,
  "max_total_iterations": 10,
  "quality_threshold": 0.7,
  "auto_publish": false,
  "parallel_docs": true
}
```

When a task exceeds `max_spec_revisions`, Grandpa escalates it to the human gate — "Bob keeps rejecting. This needs human input." When tasks converge in 2 attempts, he might lower the limit from 3 to save cycles. When one agent's rejections never lead to improvement, he flags the prompt as noise.

## 6. Composable Depth

Not every document needs the full adversarial topology. A PR/FAQ benefits from spec review and stakeholder simulation. A ticket response does not.

PM Loop supports 13 task types across three pipeline variants:

| Pipeline | Stages | Task Types | Quality Bar |
|----------|--------|------------|-------------|
| Full 8-stage | Intake → Enrich → Spec → Adversarial → Draft → Review → UX → Gate | PR/FAQs, competitive briefs, roadmap plans, decision docs | 0.8 |
| 6-stage | Intake → Enrich → Draft → Review → UX → Gate | Status reports, meeting prep, weekly digests | 0.6 |
| 4-stage | Intake → Enrich → Draft → Review → Gate | Ticket responses, email drafts | 0.5 |

The routing is a single dictionary mapping task type to stage sequence. Adding a new type requires one line. This composability means the system applies proportional rigor: full adversarial topology for documents that justify it, lighter pipelines for documents that don't.

## 7. How It Works in Practice: A Competitive Brief

Abstract architecture means nothing until you see it run. Here's what actually happens when a competitive brief goes through the full 8-stage pipeline.

**The ask:** *"Write a competitive brief on a competitor's agentic web strategy."*

**Stage 1 — Marge (Intake).** Marge classifies the task as `competitive_brief`, assigns the full 8-stage pipeline, sets the quality bar at 0.8, and creates the task file. This takes under a second. It's routing, not reasoning. Marge is the responsible parent of the pipeline — she makes sure everything starts in order.

**Stage 2 — Nelson (Enrichment).** Nelson scouts the landscape. He spawns parallel enrichment subagents — one searching for recent product announcements, another for IETF working group activity, another for competitive positioning statements. Nelson consolidates the results and attaches source URLs to every fact. No URL, no fact. He returns a structured context package with 14 sourced claims. *"Ha ha!"* — Nelson finds the data whether you like it or not.

**Stage 3 — Lisa (Spec).** Lisa reads Nelson's context and writes acceptance criteria for the brief. "Section on agent identification standards with ≥3 cited sources." "Comparison table covering ≥4 competitors." "Executive summary ≤200 words with clear recommendation." Each criterion maps to a verification method (word count check, source count, section presence). Lisa produces 11 acceptance criteria. Meticulous, thorough, exactly like her namesake.

**Stage 4 — Bob (Adversarial Review).** Bob reads Lisa's spec and attacks it. He runs 15 checks. He passes 12. He fails 3: the spec doesn't require a timeline of competitive moves, doesn't specify the audience's decision context, and doesn't require a "so what" recommendation. Bob sends the spec back to Lisa via `spec_revision`. Lisa adds the three missing criteria and resubmits. Bob runs his checks again, passes all 15. *"No one who speaks German could be an evil man"* — but Bob finds gaps in every spec regardless.

The spec advances.

**Stage 5 — Homer (Draft).** Homer writes the competitive brief using Lisa's spec and Nelson's sources. He maps each acceptance criterion to a section. The draft is 2,400 words with a 7-section structure. Homer is the pressure point of the system — everything flows through him. Like his namesake, he does the work. Sometimes reluctantly, but he does it.

**Stage 6 — Patty (Quality Review).** Patty scores the draft across seven dimensions: accuracy (0.90), evidence density (0.72), audience fit (0.88), structure (0.92), actionability (0.85), completeness (0.80), clarity (0.91). The overall score is the *minimum*: **0.72** (evidence density). Below the 0.8 threshold. Patty identifies the problem: Nelson's parallel enrichment returned richer, more recent data midway through — newer sources about an IETF working group and a naming standard adoption — that Homer didn't incorporate. The `draft_fix` arc fires. Patty is, as always, unimpressed.

Homer gets the feedback and redrafts, incorporating the new intel. Second pass: evidence density rises to 0.88. Minimum is now 0.85. Passes. Patty begrudgingly approves.

**Stage 7 — Comic Book Guy (Stakeholder Simulation).** *"Worst. Competitive Brief. Ever."* — or is it? CBG walks a six-step stakeholder journey, simulating a VP reading the brief before a strategy meeting. He scores 0.85 overall but flags two issues: (1) the comparison table buries the most important differentiator in the last column, and (2) the "so what" section uses internal jargon the VP audience won't parse. These are *experience* defects, not factual errors. Patty's rubric wouldn't catch them. CBG files the two issues as new tasks via `ux_triage` (non-blocking improvements) and passes the document.

**Stage 8 — You (Human Gate).** You see the brief, the evidence chain, Patty's scores, CBG's journey report, and the full feedback history (Bob rejected the spec once, Patty sent the draft back once). You approve.

**Stage 9 — Maggie (Publish).** Maggie doesn't say much. She formats and delivers the final brief. Published.

**Total: 13 iterations across 8 stages.** One `spec_revision` arc fired (Bob → Lisa). One `draft_fix` arc fired (Patty → Homer). Two `ux_triage` items filed (CBG → Marge). The single-pass version of this brief would have been the one Homer produced at Stage 5 — missing the newest competitive intel and with the buried comparison table. The topology caught both.

## 8. Production Results and Defect Analysis

We ran three tasks through the pipeline and analyzed the defects caught at each stage.

### Task 1: Competitive Brief (full 8-stage, 13 iterations, 1 feedback arc)

The walkthrough above. Nelson gathered competitive intelligence. When parallel enrichment returned richer data, the `draft_fix` arc fired. Homer redrafted with the new intel.

**Defect caught by the topology:** The v1 draft was built on incomplete research. A single-pass system would have published it. The feedback arc caught the gap because Patty's evidence-density check flagged that newer, higher-quality sources existed but weren't incorporated. The typed routing sent the work back to Homer (execution defect), not to Lisa (the spec was fine).

Comic Book Guy's stakeholder simulation scored 0.85 and filed 2 improvement suggestions as new tasks via `ux_triage`. These were non-blocking UX issues that would have surfaced as stakeholder feedback weeks later.

### Task 2: Ticket Triage Report (6-stage, 7 iterations, 0 feedback arcs)

Nelson pulled 25 open tickets and 40 resolved tickets. Homer produced a triage report with priority-coded sections and paste-ready customer responses. The human immediately used one paste-ready response to approve a billing waiver and post it to the ticket system.

**Defect caught by the topology:** Comic Book Guy identified that tickets marked "auto-resolve" in internal notes were placed in the "Needs Response" section, creating a contradictory signal for the reader. He also flagged missing queue health context (is 92% SLA breach rate normal or a crisis?). These are *experience* defects, not factual errors. A rubric-based review (Patty) would not catch them. A stakeholder simulation (Comic Book Guy) did. *Worst. Triage Report. Ever.* But then he fixed it.

### Task 3: Research Response (4-stage, 4 iterations, 0 feedback arcs)

A ticket requesting confirmation of an attack pattern for a customer with unexpected charges. Homer produced a dual-outcome template covering both "confirmed" and "not confirmed" paths.

**Defect caught by the topology:** Patty scored 0.82, noting that three acceptance criteria (requiring actual investigation data) were correctly templated rather than fabricated. This is a subtle quality signal. A less rigorous system might have hallucinated findings to satisfy the criteria. The backpressure rule (map each AC to where it's satisfied, or explain why it can't be) forced Homer to acknowledge the gap explicitly rather than fill it with plausible fiction.

### Defect Summary

| Defect Type | Caught By | Would Single-Pass Catch It? |
|---|---|---|
| Incomplete research (newer sources available) | Patty → `draft_fix` arc | Unlikely. Requires comparing source freshness. |
| Contradictory section labeling | Comic Book Guy | No. Factually correct, experientially wrong. |
| Missing contextual baseline | Comic Book Guy | No. Requires reader perspective, not rubric. |
| Hallucination pressure on unanswerable criteria | Patty + backpressure | Unlikely. Single-pass incentivizes completion over honesty. |
| Non-blocking UX improvements | Comic Book Guy → `ux_triage` | No. Would surface as stakeholder feedback weeks later. |

The pattern: the adversarial topology catches defects that are invisible to single-pass review because they require either opposing incentives (Bob vs Lisa), different evaluation lenses (Patty's rubric vs Comic Book Guy's journey), or structural enforcement (backpressure preventing "looks good").

## 9. Limitations

**Agent calibration.** Agents self-report quality scores. Patty says 0.85, but we have no ground truth. The next step is a human scorecard at the gate stage, comparing agent scores to human scores over 20+ tasks to detect calibration drift.

**Sample size.** Three tasks demonstrate the mechanism but do not prove it. A meaningful evaluation requires 50+ tasks with controlled comparison: the same PM producing the same deliverable types with and without the pipeline, blind-scored by a colleague.

**Creative ceiling.** The topology catches defects in execution. It does not generate strategic insight. A clever framing or a novel analogy came from the human, not the pipeline. PM Loop is a production line, not an inventor. Homer can build what Lisa specifies, but neither of them will have the flash of insight that changes the argument.

**Cost.** Each task through the full 8-stage pipeline makes 8–15 LLM calls (more if feedback arcs fire). At current model pricing, that's roughly $0.50–$2.00 per task. Cheaper than a human reviewer, but not free — and the cost scales linearly with task volume. The composable depth helps: a 4-stage email draft costs a fraction of a full PR/FAQ pipeline run.

**Latency.** The full pipeline takes 3–8 minutes wall-clock time, depending on task complexity and how many feedback arcs fire. This is fine for a competitive brief you need by end-of-day. It's not fine for a Slack reply you need in 30 seconds. The right response is to not use the full pipeline for 30-second tasks — that's what the 4-stage variant is for.

**Speed tradeoff.** For trivial tasks, the pipeline overhead exceeds the value. A 3-line ticket response doesn't need 4 agents arguing about it. The composable depth helps, but the minimum viable pipeline (4 stages) is still slower than a PM typing the answer directly. Use proportional tools for proportional problems.

## 10. Conclusion

Knowledge work has lacked the tight feedback loops that make software engineering reliable. PM Loop introduces structured adversarial review with typed feedback arcs as the equivalent of a test suite for documents. The mechanism is a topology of disagreement: agents with opposing incentives connected by defect-aware routing that sends rejected work back to the point of origin, not just "back to try again."

The early evidence suggests this topology catches defects that single-pass review misses, specifically defects that require opposing incentives, different evaluation lenses, or structural enforcement against hallucination. The tradeoff is speed on simple tasks and creative ceiling on novel ones.

The real question is not whether AI can write documents. It can. The question is whether AI can reliably *judge* documents. PM Loop's answer is that no single agent can, but a topology of disagreeing agents — forced to show their evidence, forced to route defects to their origin, watched by a cranky observer who tunes the system using the scientific method — can converge on quality that no individual node would produce alone.

Or as Grandpa would put it: *"Nothing in the queue. I'm going back to sleep."*

## 11. Try It Yourself

You don't need PM Loop's specific implementation to use the pattern. The underlying mechanism is four principles you can apply with any LLM and a simple state machine:

**1. Opposing incentives.** Pair agents that want different things. A writer wants completeness; a reviewer wants to find gaps. A spec author wants precision; an adversarial reviewer wants to break assumptions. The disagreement is the feature, not a bug.

**2. Typed feedback arcs.** When a reviewer rejects work, don't just send it "back." Route it to the specific agent responsible for the defect class. Spec wrong → spec writer. Execution wrong → drafter. Scope changed → intake. The routing carries signal about *what went wrong*, not just *that something went wrong*.

**3. Backpressure with evidence.** Every agent must produce structured evidence, not just a verdict. Source URLs, mapped acceptance criteria, scored dimensions, journey steps. "Looks good" is not allowed. This makes the system auditable and prevents rubber-stamping.

**4. An observer, not a manager.** One agent watches the pipeline metrics (where are tasks piling up? which arcs fire most? are tasks converging or oscillating?) and makes one tuning change at a time. Scientific method: observe, hypothesize, change one variable, measure. And complain about how things were better in the old days.

### Minimal Implementation

The full source is [on GitHub](https://github.com/kphatak001/pm-loop), but you can build a working version from these components:

```
pm-loop/
├── orchestrator.py      # Task model, Stage enum, feedback arcs, advance_task()
├── runner.py            # CLI: add, run, cycle, status, observe
├── loop_config.json     # Grandpa's tunable config (6 parameters)
├── agents/
│   └── prompts.py       # 9 agent prompt definitions
├── queue/               # Task JSON files (one per task)
└── evidence/            # Agent output artifacts
```

The core is ~300 lines of Python. The agents are LLM prompts with structured output schemas. The state is JSON files in a directory. There is no framework, no database, no infrastructure beyond "Python + an LLM API."

The hard part isn't the code. It's designing the incentive structure — deciding which agents should disagree, what they should disagree about, and where the feedback arcs should point. Get that right, and the rest is plumbing.

---

## Acknowledgments

PM Loop draws from the Grandpa Loop (Joshua Samuel, 2025), which introduced adversarial multi-agent orchestration with observer-based tuning, and the AI SDLC methodology, which contributed composable stage routing and the scheduled factory model.

---

*If you build something with this pattern, I'd love to hear about it. The topology of disagreement is the interesting part — the specific agents are just one instantiation. Find me on [LinkedIn](https://linkedin.com/in/kphatak) or [GitHub](https://github.com/kphatak001).*
