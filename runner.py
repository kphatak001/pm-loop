#!/usr/bin/env python3
"""
PM Loop Runner — CLI and agent orchestration layer.

Translates pipeline stages into agent execution tasks.
Each agent runs as a subagent with its prompt + task context.

Usage:
  python runner.py add "Write Q2 competitive brief" --type competitive_brief
  python runner.py run <task-id>
  python runner.py cycle                  # Advance all tasks one stage (dry run)
  python runner.py cycle --execute        # Advance all tasks (execute agents)
  python runner.py status                 # Show pipeline state
  python runner.py observe                # Run Grandpa observer
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import (
    Task, Stage, Observer, STAGE_AGENTS, FEEDBACK_ARCS, TASK_PIPELINES, PUBLISH_ROUTES,
    create_task, advance_task, load_tasks, next_stage,
    QUEUE_DIR, EVIDENCE_DIR, BASE,
)
from agents.prompts import AGENTS

# Stages where the pipeline pauses (no auto-advance)
PAUSE_STAGES = {Stage.DONE, Stage.BLOCKED, Stage.HUMAN_GATE}


def build_agent_prompt(task: Task) -> str:
    """Build the full prompt for a task's current stage agent.

    This is the integration point with your LLM orchestrator. The prompt
    includes the agent's instructions + full task context as JSON.
    Adapt the output format to match your agent framework.
    """
    agent_key = STAGE_AGENTS.get(task.stage)
    if not agent_key:
        return None
    agent = AGENTS[agent_key]
    task_json = json.dumps(task.to_dict(), indent=2)

    prompt = f"""{agent['prompt']}

--- TASK CONTEXT ---
{task_json}
--- END TASK CONTEXT ---

"""
    if task.stage == Stage.PUBLISH:
        routes = PUBLISH_ROUTES.get(task.task_type, {})
        prompt += f"""--- PUBLISH ROUTES ---
{json.dumps(routes, indent=2)}
--- END PUBLISH ROUTES ---

"""

    prompt += f"""Process this task through the {task.stage} stage.

Use whatever tools are available to gather real data (web search, document
retrieval, API calls, etc.). Do not generate hypothetical content.

After completing your work, respond with a JSON block:
```json
{{
  "verdict": "pass|reject|blocked",
  "evidence": "what you checked/found (with source URLs)",
  "output": {{...your structured output for this stage...}},
  "feedback_arc": null or "arc_name if rejecting",
  "confidence": 0.0-1.0
}}
```

Write any deliverable files to {EVIDENCE_DIR}/."""
    return prompt


def build_parallel_tasks(tasks: list[Task]) -> list[dict]:
    """Group actionable tasks into parallel execution batches."""
    actionable = [t for t in tasks if t.stage not in PAUSE_STAGES]
    batch = []
    for t in actionable:
        prompt = build_agent_prompt(t)
        if prompt:
            batch.append({"task_id": t.id, "stage": t.stage, "prompt": prompt})
    return batch


def cmd_add(args):
    """Add a new task to the queue."""
    metadata = {}
    if args.stakeholders:
        metadata["stakeholders"] = args.stakeholders
    if args.deadline:
        metadata["deadline"] = args.deadline
    task = create_task(args.title, args.type, args.title, metadata)
    pipeline = [s.value for s in TASK_PIPELINES.get(args.type, [])]
    print(f"Created task {task.id}: {task.title}")
    print(f"  Type: {task.task_type} | Pipeline: {' → '.join(pipeline)}")
    print(f"  File: {QUEUE_DIR / f'{task.id}.json'}")


def cmd_status(args):
    """Show pipeline status."""
    tasks = load_tasks()
    if not tasks:
        print("Queue empty. Grandpa is napping.")
        return

    by_stage = {}
    for t in tasks:
        by_stage.setdefault(t.stage, [])
        by_stage[t.stage].append(t)

    print(f"\n{'='*60}")
    print(f"  PM LOOP STATUS — {len(tasks)} tasks in pipeline")
    print(f"{'='*60}\n")

    for stage in [s.value for s in Stage]:
        stage_tasks = by_stage.get(stage, [])
        if not stage_tasks:
            continue
        agent = STAGE_AGENTS.get(stage, "system")
        agent_name = AGENTS.get(agent, {}).get("name", stage)
        print(f"  [{stage.upper()}] {agent_name} — {len(stage_tasks)} task(s)")
        for t in stage_tasks:
            arcs = len(t.feedback_history)
            arc_str = f" (↩ {arcs} arcs)" if arcs else ""
            print(f"    • {t.id}: {t.title} [iter:{t.iterations}]{arc_str}")
        print()


def cmd_cycle(args):
    """Advance all actionable tasks one stage."""
    batch = build_parallel_tasks(load_tasks())
    if not batch:
        print("No actionable tasks. Pipeline idle.")
        return

    print(f"Pipeline cycle: {len(batch)} task(s) to process\n")

    if args.dry_run:
        for item in batch:
            agent_key = STAGE_AGENTS.get(item["stage"], "?")
            print(f"  [DRY RUN] {item['task_id']} [{item['stage']}] → {agent_key} ({len(item['prompt'])} chars)")
        print(f"\nRun with --execute to process {len(batch)} task(s).")
        return

    # Execute mode: output prompts for your agent orchestrator
    for item in batch:
        print(f"--- AGENT TASK: {item['task_id']} [{item['stage']}] ---")
        print(item["prompt"])
        print(f"--- END AGENT TASK ---\n")


def cmd_run(args):
    """Generate prompt for a single task's current stage."""
    task_file = QUEUE_DIR / f"{args.task_id}.json"
    if not task_file.exists():
        matches = list(QUEUE_DIR.glob(f"*{args.task_id}*.json"))
        if len(matches) == 1:
            task_file = matches[0]
        else:
            print(f"Task not found: {args.task_id}")
            return

    task = Task.from_dict(json.loads(task_file.read_text()))
    if task.stage in PAUSE_STAGES:
        print(f"Task {task.id} is at {task.stage} — cannot auto-advance.")
        return

    prompt = build_agent_prompt(task)
    if not prompt:
        print(f"No agent for stage {task.stage}")
        return

    agent_key = STAGE_AGENTS.get(task.stage)
    print(f"Task: {task.id} [{task.stage}] → {agent_key}")
    print("--- AGENT PROMPT ---")
    print(prompt)
    print("--- END AGENT PROMPT ---")


def cmd_observe(args):
    """Run Grandpa observer."""
    tasks = load_tasks()
    observer = Observer()
    report = observer.observe(tasks)

    print(f"\n{'='*60}")
    print(f"  👴 GRANDPA'S OBSERVER REPORT")
    print(f"{'='*60}\n")
    print(f"  Tasks: {report['total_tasks']}")
    print(f"  By stage: {json.dumps(report['by_stage'], indent=4)}")

    if report["stuck_tasks"]:
        print(f"\n  ⚠️  STUCK:")
        for s in report["stuck_tasks"]:
            print(f"    • {s['id']}: {s['reason']}")

    if report["feedback_patterns"]:
        print(f"\n  ↩ Feedback: {json.dumps(report['feedback_patterns'])}")

    if report["complaints"]:
        print(f"\n  💬 Grandpa:")
        for c in report["complaints"]:
            print(f"    \"{c}\"")


def main():
    parser = argparse.ArgumentParser(description="PM Loop Runner")
    sub = parser.add_subparsers(dest="command")

    p_add = sub.add_parser("add", help="Add task")
    p_add.add_argument("title")
    p_add.add_argument("--type", default="prfaq",
                       choices=list(TASK_PIPELINES.keys()))
    p_add.add_argument("--stakeholders")
    p_add.add_argument("--deadline")

    sub.add_parser("status", help="Pipeline status")

    p_cycle = sub.add_parser("cycle", help="Advance all tasks one stage")
    p_cycle.add_argument("--dry-run", action="store_true", default=True)
    p_cycle.add_argument("--execute", action="store_true", dest="execute")

    p_run = sub.add_parser("run", help="Generate prompt for single task")
    p_run.add_argument("task_id")

    sub.add_parser("observe", help="Run Grandpa observer")

    args = parser.parse_args()
    if hasattr(args, "execute") and args.execute:
        args.dry_run = False

    cmds = {"add": cmd_add, "status": cmd_status, "cycle": cmd_cycle,
            "run": cmd_run, "observe": cmd_observe}
    if args.command in cmds:
        cmds[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
