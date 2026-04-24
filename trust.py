"""
Trust Tracker — Epistemic context learning for agent reliability.

Tracks whether each agent's verdicts predict downstream outcomes.
Key signal pairs:
  - Bob rejects spec → did Patty later reject the draft? (Bob was right)
  - Bob rejects spec → did Patty pass the draft first try? (Bob was wrong)
  - Bob passes spec → did Patty reject the draft? (Bob missed something)

Trust score = correct_predictions / total_predictions per agent.
Persisted as JSON alongside observer reports.

Based on: "Epistemic Context Learning: Building Trust the Right Way
in LLM-Based Multi-Agent Systems" (arXiv 2604)
"""

from __future__ import annotations
import json
from pathlib import Path
from dataclasses import dataclass, field


TRUST_PATH = Path(__file__).parent / "observer-reports" / "trust.json"

# Which agent pairs form epistemic links (upstream → downstream).
# If upstream passes and downstream rejects, upstream missed something.
# If upstream rejects and downstream passes, upstream was too strict.
EPISTEMIC_PAIRS = [
    ("sideshow_bob", "patty"),      # Bob reviews spec → Patty reviews draft
    ("sideshow_bob", "comic_book_guy"),  # Bob reviews spec → CBG checks UX
    ("patty", "comic_book_guy"),    # Patty reviews draft → CBG checks UX
]


@dataclass
class AgentRecord:
    """Tracks one agent's prediction accuracy."""
    correct: int = 0       # verdict aligned with downstream outcome
    incorrect: int = 0     # verdict contradicted by downstream
    total: int = 0

    @property
    def trust_score(self) -> float:
        if self.total == 0:
            return 1.0  # no data yet — assume trustworthy
        return self.correct / self.total

    def to_dict(self) -> dict:
        return {"correct": self.correct, "incorrect": self.incorrect,
                "total": self.total, "trust_score": round(self.trust_score, 3)}


class TrustTracker:
    def __init__(self):
        self.agents: dict[str, AgentRecord] = {}
        self._load()

    def _load(self):
        if TRUST_PATH.exists():
            data = json.loads(TRUST_PATH.read_text())
            for name, rec in data.items():
                self.agents[name] = AgentRecord(
                    correct=rec.get("correct", 0),
                    incorrect=rec.get("incorrect", 0),
                    total=rec.get("total", 0),
                )

    def save(self):
        TRUST_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {name: rec.to_dict() for name, rec in self.agents.items()}
        tmp = TRUST_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(TRUST_PATH)

    def record_outcome(self, task_evidence: list[dict]):
        """Analyze a task's full evidence trail and update trust scores.

        Called when a task completes (reaches DONE or HUMAN_GATE).
        Walks the evidence list to find epistemic pairs and score them.
        """
        # Build per-agent verdict map from evidence
        verdicts: dict[str, str] = {}  # agent → last verdict
        for ev in task_evidence:
            agent = ev.get("agent", "")
            verdict = ev.get("verdict", "")
            if agent and verdict:
                verdicts[agent] = verdict

        for upstream, downstream in EPISTEMIC_PAIRS:
            up_v = verdicts.get(upstream)
            down_v = verdicts.get(downstream)
            if up_v is None or down_v is None:
                continue  # pair didn't both run on this task

            rec = self.agents.setdefault(upstream, AgentRecord())
            rec.total += 1

            if up_v == "rejected" and down_v == "passed":
                # Upstream rejected but downstream passed → upstream was too strict
                rec.incorrect += 1
            elif up_v == "passed" and down_v == "rejected":
                # Upstream passed but downstream rejected → upstream missed something
                rec.incorrect += 1
            else:
                # Both agreed (both passed or both rejected) → upstream was right
                rec.correct += 1

    def get_score(self, agent: str) -> float:
        rec = self.agents.get(agent)
        return rec.trust_score if rec else 1.0

    def summary(self) -> dict:
        return {name: rec.to_dict() for name, rec in self.agents.items()}
