"""
Conflict resolver — diagnoses replay failures via a single Claude call.

Classifies failures as:
- test_failure:  implementation outdated, intent still valid → regenerate
- system_failure:  system doesn't satisfy intent → investigate regression
- environment_failure:  transient/config issue → fix environment, re-run
"""

import base64
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import anthropic

from .replay import ReplayStepError

log = logging.getLogger(__name__)

MODEL = os.environ.get("UI_TEST_MODEL", "claude-sonnet-4-6")

DIAGNOSIS_PROMPT = """\
You are a test failure analyst for a UI testing framework.

You will receive:
1. An INTENT — an immutable description of what a feature should do.
2. An IMPLEMENTATION — a deterministic Playwright test script generated from that intent.
3. A FAILURE — which step failed, the error message, and screenshots.

Classify this failure into exactly one category:

- **test_failure**: The implementation no longer matches the current system \
(e.g., a button was renamed, DOM structure changed, a selector is stale). \
The intent is still valid — the feature still works, but the test can't find it. \
Recommended action: regenerate the implementation from the intent.

- **system_failure**: The system genuinely does not satisfy the intent. \
This is a real regression — the feature is broken. \
Recommended action: investigate and fix the system.

- **environment_failure**: The test environment is misconfigured — missing test data, \
wrong instance, container not running, transient network error. \
Recommended action: fix the environment and re-run.

Respond with ONLY a JSON object (no markdown, no code fences):
{"category": "test_failure|system_failure|environment_failure", \
"explanation": "why this happened", \
"recommended_action": "what to do", \
"confidence": 0.0-1.0}\
"""


@dataclass
class ConflictDiagnosis:
    category: Literal["test_failure", "system_failure", "environment_failure"]
    explanation: str
    recommended_action: str
    confidence: float


class ConflictResolver:
    """Diagnose replay failures with a single Claude call."""

    def __init__(self):
        self.client = anthropic.Anthropic()

    def diagnose(
        self,
        intent_path: Path,
        impl_path: Path,
        error: ReplayStepError,
    ) -> ConflictDiagnosis:
        """Classify a replay failure."""
        intent_text = intent_path.read_text()
        impl_text = impl_path.read_text()
        sha = self._git_sha()

        # Build the user message with failure context.
        failure_info = (
            f"STEP {error.step.number}: {error.step.action}({error.step.detail})\n"
            f"ERROR: {error.step.error}\n"
            f"SYSTEM VERSION: {sha}"
        )

        content = [
            {"type": "text", "text": (
                f"## INTENT\n```yaml\n{intent_text}```\n\n"
                f"## IMPLEMENTATION\n```python\n{impl_text}```\n\n"
                f"## FAILURE\n{failure_info}"
            )},
        ]

        # Attach the failure screenshot if available.
        if error.step.screenshot:
            screenshot_path = Path(error.step.screenshot)
            if screenshot_path.exists():
                img_b64 = base64.standard_b64encode(
                    screenshot_path.read_bytes()
                ).decode()
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_b64,
                    },
                })

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=DIAGNOSIS_PROMPT,
            messages=[{"role": "user", "content": content}],
        )

        # Parse the JSON response.
        text = "".join(b.text for b in response.content if b.type == "text")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            log.error("Failed to parse diagnosis response: %s", text[:500])
            return ConflictDiagnosis(
                category="environment_failure",
                explanation=f"Could not parse diagnosis: {text[:200]}",
                recommended_action="Re-run diagnosis or inspect manually",
                confidence=0.0,
            )

        return ConflictDiagnosis(
            category=data.get("category", "environment_failure"),
            explanation=data.get("explanation", ""),
            recommended_action=data.get("recommended_action", ""),
            confidence=float(data.get("confidence", 0.5)),
        )

    @staticmethod
    def _git_sha() -> str:
        try:
            return subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=Path(__file__).parents[2],
                text=True,
            ).strip()
        except Exception:
            return "unknown"
