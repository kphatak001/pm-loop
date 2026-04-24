#!/usr/bin/env python3
"""
PM Loop Orchestrator — Adversarial multi-agent pipeline for PM deliverables.

Architecture: Grandpa Loop (adversarial topology, feedback arcs, observer pattern,
backpressure) + composable stage routing for different document types.

The PM Loop treats knowledge work quality like software testing:
- Tasks are PM deliverables (PRFAQs, status reports, competitive briefs, specs)
- "Tests pass" = evidence-based quality gates with structured scoring
- The Observer tunes the pipeline based on iteration metrics
- Human gates at strategic decision points, not execution steps
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum

BASE = Path(__file__).parent
QUEUE_DIR = BASE / "queue"
EVIDENCE_DIR = BASE / "evidence"
OBSERVER_DIR = BASE / "observer-reports"


class Stage(str, Enum):
    """Pipeline stages — ordered but with feedback arcs (Lissajous, not linear)."""
    INTAKE = "intake"           # Marge: curate raw idea into structured task
    ENRICH = "enrich"           # Nelson: scout context (market data, docs, web)
    SPEC = "spec"               # Lisa: write detailed spec with acceptance criteria
    ADVERSARIAL = "adversarial" # Sideshow Bob: poke holes, reject if gaps found
    DRAFT = "draft"             # Homer: produce the deliverable
    REVIEW = "review"           # Patty: check quality against standards
    UX_CHECK = "ux_check"       # Comic Book Guy: does this work for stakeholders?
    HUMAN_GATE = "human_gate"   # Human reviews and approves or sends back
    PUBLISH = "publish"         # Maggie: deliver to destination
    DONE = "done"

    # Terminal/feedback states
    BLOCKED = "blocked"
    REVISION = "revision"       # Feedback arc: Bob → Lisa (spec revision loop)
    REWORK = "rework"           # Feedback arc: Patty/CBG → Homer (quality fix loop)


# ═══════════════════════════════════════════════════════════════════════════════
# FEEDBACK ARCS — the Lissajous crossings
# These are the core of the adversarial topology. Each arc routes rejected
# work back to the specific agent responsible for the defect class.
# ═══════════════════════════════════════════════════════════════════════════════

FEEDBACK_ARCS = {
    "spec_revision":  {"from": Stage.ADVERSARIAL, "to": Stage.SPEC,   "reason": "Spec gaps found"},
    "draft_fix":      {"from": Stage.REVIEW,      "to": Stage.DRAFT,  "reason": "Quality below bar"},
    "ux_fix":         {"from": Stage.UX_CHECK,     "to": Stage.DRAFT,  "reason": "Stakeholder flow broken"},
    "ux_triage":      {"from": Stage.UX_CHECK,     "to": Stage.INTAKE, "reason": "New work discovered"},
    "human_rework":   {"from": Stage.HUMAN_GATE,   "to": Stage.DRAFT,  "reason": "Human requested changes"},
    "human_respec":   {"from": Stage.HUMAN_GATE,   "to": Stage.SPEC,   "reason": "Human changed requirements"},
}

# Stage → agent mapping
STAGE_AGENTS = {
    Stage.INTAKE:      "marge",
    Stage.ENRICH:      "nelson",
    Stage.SPEC:        "lisa",
    Stage.ADVERSARIAL: "sideshow_bob",
    Stage.DRAFT:       "homer",
    Stage.REVIEW:      "patty",
    Stage.UX_CHECK:    "comic_book_guy",
    Stage.PUBLISH:     "maggie",
}


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE VARIANTS — composable depth for different document types
# ═══════════════════════════════════════════════════════════════════════════════

_FULL = [Stage.INTAKE, Stage.ENRICH, Stage.SPEC, Stage.ADVERSARIAL,
         Stage.DRAFT, Stage.REVIEW, Stage.UX_CHECK, Stage.HUMAN_GATE,
         Stage.PUBLISH, Stage.DONE]

_SIX_STAGE = [Stage.INTAKE, Stage.ENRICH, Stage.DRAFT, Stage.REVIEW,
              Stage.UX_CHECK, Stage.HUMAN_GATE, Stage.PUBLISH, Stage.DONE]

_FOUR_STAGE = [Stage.INTAKE, Stage.ENRICH, Stage.DRAFT, Stage.REVIEW,
               Stage.HUMAN_GATE, Stage.PUBLISH, Stage.DONE]

TASK_PIPELINES = {
    # Full 8-stage — high-stakes deliverables
    "prfaq":              _FULL,
    "competitive_brief":  _FULL,
    "roadmap_plan":       _FULL,
    "launch_checklist":   _FULL,
    "one_pager":          _FULL,
    "decision_doc":       _FULL,
    "post_mortem":        _FULL,
    "customer_experience": _FULL,
    # 6-stage — standardized formats
    "status_report":      _SIX_STAGE,
    "meeting_prep":       _SIX_STAGE,
    "weekly_digest":      _SIX_STAGE,
    # 4-stage — quick-turn outputs
    "ticket_response":    _FOUR_STAGE,
    "email_draft":        _FOUR_STAGE,
}

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG-DRIVEN OVERRIDES — loop_config.json task_types overlay
# ═══════════════════════════════════════════════════════════════════════════════

_CONFIG_PATH = BASE / "loop_config.json"
_LOOP_CONFIG = json.loads(_CONFIG_PATH.read_text()) if _CONFIG_PATH.exists() else {}
_CONFIG_TASK_TYPES = _LOOP_CONFIG.get("task_types", {})

# Override pipelines and register new task types from config
for _tt, _cfg in _CONFIG_TASK_TYPES.items():
    if "stages" in _cfg:
        TASK_PIPELINES[_tt] = [Stage(s) for s in _cfg["stages"]] + [Stage.DONE]


def quality_threshold_for(task_type: str) -> float:
    """Per-type quality threshold from config, falling back to global default."""
    tt_cfg = _CONFIG_TASK_TYPES.get(task_type, {})
    return tt_cfg.get("quality_threshold", _LOOP_CONFIG.get("quality_threshold", 0.7))


# Publish destinations per task type (customize for your setup)
PUBLISH_ROUTES = {
    "prfaq":              {"primary": "docs", "notify": "chat"},
    "competitive_brief":  {"primary": "docs", "secondary": "notes", "notify": "chat"},
    "roadmap_plan":       {"primary": "docs", "notify": "chat"},
    "launch_checklist":   {"primary": "docs", "notify": "chat"},
    "status_report":      {"primary": "chat", "secondary": "notes"},
    "one_pager":          {"primary": "docs", "notify": "chat"},
    "decision_doc":       {"primary": "docs", "notify": "chat"},
    "post_mortem":        {"primary": "docs", "notify": "chat"},
    "meeting_prep":       {"primary": "chat", "secondary": "notes"},
    "weekly_digest":      {"primary": "chat", "secondary": "notes"},
    "ticket_response":    {"primary": "ticket", "notify": "chat"},
    "email_draft":        {"primary": "notes", "notify": "chat"},
    "customer_experience": {"primary": "docs", "notify": "chat"},
}


# ═══════════════════════════════════════════════════════════════════════════════
# TASK MODEL — JSON file-based state machine
# ═══════════════════════════════════════════════════════════════════════════════

class Task:
    """A PM task flowing through the pipeline."""

    def __init__(self, id: str, title: str, task_type: str, raw_input: str,
                 stage: str = Stage.INTAKE, metadata: dict = None):
        self.id = id
        self.title = title
        self.task_type = task_type
        self.raw_input = raw_input
        self.stage = stage
        self.metadata = metadata or {}
        self.evidence = []         # Backpressure: every stage must add evidence
        self.iterations = 0
        self.feedback_history = [] # Track all feedback arcs taken
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at

    def to_dict(self):
        return {
            "id": self.id, "title": self.title, "task_type": self.task_type,
            "raw_input": self.raw_input, "stage": self.stage,
            "metadata": self.metadata, "evidence": self.evidence,
            "iterations": self.iterations, "feedback_history": self.feedback_history,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d):
        stage = d.get("stage", Stage.INTAKE)
        if isinstance(stage, str) and not isinstance(stage, Stage):
            stage = Stage(stage)
        t = cls(d["id"], d["title"], d["task_type"], d["raw_input"],
                stage, d.get("metadata", {}))
        t.evidence = d.get("evidence", [])
        t.iterations = d.get("iterations", 0)
        t.feedback_history = d.get("feedback_history", [])
        t.created_at = d.get("created_at", t.created_at)
        t.updated_at = d.get("updated_at", t.updated_at)
        return t

    def save(self):
        self.updated_at = datetime.now(timezone.utc).isoformat()
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        path = QUEUE_DIR / f"{self.id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2))
        tmp.replace(path)

    def add_evidence(self, stage: str, agent: str, verdict: str, details: str):
        """Backpressure: no stage passes without evidence."""
        self.evidence.append({
            "stage": stage, "agent": agent, "verdict": verdict,
            "details": details, "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def record_feedback(self, arc_name: str, reason: str):
        self.feedback_history.append({
            "arc": arc_name, "reason": reason, "iteration": self.iterations,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


def load_tasks(stage_filter: str = None) -> list[Task]:
    """Load all tasks, optionally filtered by stage."""
    if stage_filter is not None and isinstance(stage_filter, str) and not isinstance(stage_filter, Stage):
        stage_filter = Stage(stage_filter)
    tasks = []
    for f in QUEUE_DIR.glob("*.json"):
        try:
            t = Task.from_dict(json.loads(f.read_text()))
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"  ⚠️  Skipping malformed task file {f.name}: {e}", file=__import__('sys').stderr)
            continue
        if stage_filter is None or t.stage == stage_filter:
            tasks.append(t)
    return tasks


def next_stage(current: str, task_type: str = None) -> str:
    """Happy path progression, respecting per-type pipeline routing."""
    if isinstance(current, str) and not isinstance(current, Stage):
        current = Stage(current)
    order = TASK_PIPELINES.get(task_type, _FULL)
    try:
        idx = order.index(current)
        if idx + 1 >= len(order):
            return Stage.DONE
        return order[idx + 1]
    except ValueError:
        return order[0]


# ═══════════════════════════════════════════════════════════════════════════════
# OBSERVER — Grandpa: watches, tunes, complains
# ═══════════════════════════════════════════════════════════════════════════════

class Observer:
    """Grandpa: watches the loop, tunes it, complains constantly.

    Tracks iteration counts, feedback patterns, cycle times per task type.
    Makes one minimal change at a time based on evidence across 2+ iterations.
    """

    def __init__(self):
        self.report_path = OBSERVER_DIR / "latest.json"
        self.history_path = OBSERVER_DIR / "history.jsonl"
        self.config_path = BASE / "loop_config.json"
        self.config = self._load_config()

    def _load_config(self) -> dict:
        if self.config_path.exists():
            return json.loads(self.config_path.read_text())
        defaults = {
            "max_spec_revisions": 3,
            "max_draft_reworks": 3,
            "max_total_iterations": 10,
            "quality_threshold": 0.7,
            "auto_publish": False,
            "parallel_docs": True,
        }
        self.config_path.write_text(json.dumps(defaults, indent=2))
        return defaults

    def observe(self, tasks: list[Task]) -> dict:
        """Run observation pass. Returns report with findings and any config changes."""
        now = datetime.now(timezone.utc).isoformat()
        report = {
            "timestamp": now,
            "total_tasks": len(tasks),
            "by_stage": {},
            "stuck_tasks": [],
            "feedback_patterns": {},
            "config_changes": [],
            "complaints": [],
        }

        # Count by stage
        for t in tasks:
            report["by_stage"].setdefault(t.stage, 0)
            report["by_stage"][t.stage] += 1

        # Find stuck tasks (too many iterations or repeated feedback arcs)
        for t in tasks:
            if t.stage == Stage.DONE:
                continue
            spec_revisions = sum(1 for f in t.feedback_history if f["arc"] == "spec_revision")
            draft_reworks = sum(1 for f in t.feedback_history if f["arc"] in ("draft_fix", "ux_fix"))

            if spec_revisions >= self.config["max_spec_revisions"]:
                report["stuck_tasks"].append({
                    "id": t.id, "reason": f"Spec revised {spec_revisions}x — Bob keeps rejecting",
                    "recommendation": "Escalate to human for spec clarification",
                })
                t.stage = Stage.HUMAN_GATE
                t.add_evidence(Stage.ADVERSARIAL, "grandpa", "escalated",
                               f"Spec revision loop hit {spec_revisions}x. Needs human input.")
                t.save()

            if draft_reworks >= self.config["max_draft_reworks"]:
                report["stuck_tasks"].append({
                    "id": t.id, "reason": f"Draft reworked {draft_reworks}x — quality not converging",
                    "recommendation": "Escalate to human or lower quality threshold",
                })
                t.stage = Stage.HUMAN_GATE
                t.add_evidence(Stage.REVIEW, "grandpa", "escalated",
                               f"Draft rework loop hit {draft_reworks}x. Not converging.")
                t.save()

        # Track feedback patterns across all tasks
        all_arcs = {}
        for t in tasks:
            for f in t.feedback_history:
                all_arcs.setdefault(f["arc"], 0)
                all_arcs[f["arc"]] += 1
        report["feedback_patterns"] = all_arcs

        # Grandpa's complaints (the best part)
        if report["by_stage"].get(Stage.BLOCKED, 0) > 2:
            report["complaints"].append(
                "Back in my day, we didn't have three tasks blocked at once. Someone fix this.")
        if all_arcs.get("spec_revision", 0) > 5:
            report["complaints"].append(
                "Lisa and Bob have been arguing all day. Maybe the requirements are just bad.")
        if not tasks:
            report["complaints"].append(
                "Nothing in the queue. I'm going back to sleep.")

        # Tune config based on patterns (one change at a time, wait 2+ cycles)
        self._tune(report, all_arcs, tasks)

        # Save report
        OBSERVER_DIR.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(json.dumps(report, indent=2))
        with open(self.history_path, "a") as f:
            f.write(json.dumps(report) + "\n")

        return report

    def _tune(self, report: dict, all_arcs: dict, tasks: list):
        """Make at most one config change per observation, based on evidence.

        Rules:
        - Skip if last config change was < 2 reports ago
        - High spec_revision rate → bump max_spec_revisions
        - High draft_fix/ux_fix rate → lower quality_threshold by 0.05
        - Zero rejections across all tasks → raise quality_threshold by 0.05
        """
        history = self._load_history()
        # Don't tune if we changed config recently (wait 2+ cycles)
        recent_changes = [h for h in history[-2:] if h.get("config_changes")]
        if recent_changes:
            return

        active = [t for t in tasks if t.stage != Stage.DONE]
        if not active:
            return

        # High spec revision rate: > 60% of active tasks hit spec_revision
        spec_rev_tasks = sum(1 for t in active
                             if any(f["arc"] == "spec_revision" for f in t.feedback_history))
        if spec_rev_tasks > len(active) * 0.6 and self.config["max_spec_revisions"] < 6:
            old = self.config["max_spec_revisions"]
            self.config["max_spec_revisions"] = old + 1
            change = {"param": "max_spec_revisions", "old": old, "new": old + 1,
                       "reason": f"{spec_rev_tasks}/{len(active)} tasks hit spec_revision — giving Lisa more room"}
            report["config_changes"].append(change)
            report["complaints"].append(f"Bumped max_spec_revisions {old}→{old+1}. Bob's being too picky.")
            self._save_config()
            return  # One change at a time

        # High draft rework rate: > 60% of active tasks hit draft_fix or ux_fix
        rework_tasks = sum(1 for t in active
                           if any(f["arc"] in ("draft_fix", "ux_fix") for f in t.feedback_history))
        if rework_tasks > len(active) * 0.6 and self.config["quality_threshold"] > 0.4:
            old = self.config["quality_threshold"]
            new = round(old - 0.05, 2)
            self.config["quality_threshold"] = new
            change = {"param": "quality_threshold", "old": old, "new": new,
                       "reason": f"{rework_tasks}/{len(active)} tasks stuck in rework — lowering the bar slightly"}
            report["config_changes"].append(change)
            report["complaints"].append(f"Lowered quality_threshold {old}→{new}. Patty needs to relax.")
            self._save_config()
            return

        # Everything passing first try: raise the bar
        zero_rejection = all(len(t.feedback_history) == 0 for t in active)
        if zero_rejection and len(active) >= 2 and self.config["quality_threshold"] < 0.95:
            old = self.config["quality_threshold"]
            new = round(old + 0.05, 2)
            self.config["quality_threshold"] = new
            change = {"param": "quality_threshold", "old": old, "new": new,
                       "reason": f"All {len(active)} tasks passing without rejection — raising the bar"}
            report["config_changes"].append(change)
            report["complaints"].append(f"Raised quality_threshold {old}→{new}. Too easy. Suspicious.")
            self._save_config()
            return

    def _save_config(self):
        """Write config back to loop_config.json (atomic)."""
        tmp = self.config_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.config, indent=2))
        tmp.replace(self.config_path)

    def _load_history(self) -> list[dict]:
        """Load recent observer reports from history."""
        if not self.history_path.exists():
            return []
        reports = []
        for line in self.history_path.read_text().strip().splitlines()[-5:]:
            try:
                reports.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return reports


def create_task(title: str, task_type: str, raw_input: str, metadata: dict = None) -> Task:
    """Create a new task and add it to the queue."""
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    task_id = f"pm-{int(time.time())}-{os.urandom(2).hex()}"
    t = Task(task_id, title, task_type, raw_input, metadata=metadata)
    t.save()
    return t


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

    # Archive completed tasks out of the active queue
    if task.stage == Stage.DONE:
        done_dir = QUEUE_DIR / "done"
        done_dir.mkdir(parents=True, exist_ok=True)
        src = QUEUE_DIR / f"{task.id}.json"
        if src.exists():
            src.replace(done_dir / f"{task.id}.json")

    return task
