"""
Pluggable LLM executor for PM Loop.

Provides a simple interface: execute(prompt) -> dict with verdict/evidence/output.
Auto-detects backend from environment variables, or use --backend flag.

Supported backends:
  - anthropic: Uses ANTHROPIC_API_KEY (Claude)
  - openai:    Uses OPENAI_API_KEY (GPT-4, etc.)
  - echo:      Returns prompt as-is (testing/debugging)

Custom backends: subclass Executor and implement execute(prompt) -> dict.
"""

import json
import os
import re


class Executor:
    """Base class. Subclass and implement execute() for custom backends."""

    def execute(self, prompt: str) -> dict:
        """Call LLM with prompt, return parsed JSON response.

        Must return dict with at minimum:
          verdict: "pass" | "reject" | "blocked"
          evidence: str
          output: dict (stage-specific deliverable)
          feedback_arc: str | None
          confidence: float
        """
        raise NotImplementedError


class AnthropicExecutor(Executor):
    def __init__(self, model="claude-sonnet-4-20250514"):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model = model

    def execute(self, prompt: str) -> dict:
        response = self.client.messages.create(
            model=self.model, max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_json_response(response.content[0].text)


class OpenAIExecutor(Executor):
    def __init__(self, model="gpt-4o"):
        import openai
        self.client = openai.OpenAI()
        self.model = model

    def execute(self, prompt: str) -> dict:
        response = self.client.chat.completions.create(
            model=self.model, max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_json_response(response.choices[0].message.content)


class EchoExecutor(Executor):
    """Testing backend — auto-passes every stage."""

    def execute(self, prompt: str) -> dict:
        return {
            "verdict": "pass",
            "evidence": "Echo executor — auto-pass for testing",
            "output": {},
            "feedback_arc": None,
            "confidence": 1.0,
        }


def _parse_json_response(text: str) -> dict:
    """Extract JSON block from LLM response text."""
    # Try fenced code block first
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # Try raw JSON object
    m = re.search(r"\{[^{}]*\"verdict\"[^{}]*\}", text, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"No JSON block found in response:\n{text[:500]}")


BACKENDS = {
    "anthropic": AnthropicExecutor,
    "openai": OpenAIExecutor,
    "echo": EchoExecutor,
}


def get_executor(backend: str = None) -> Executor:
    """Get executor by name, or auto-detect from environment."""
    if backend:
        return BACKENDS[backend]()
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicExecutor()
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAIExecutor()
    raise RuntimeError(
        "No LLM backend configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY, "
        "or use --backend echo for testing."
    )
