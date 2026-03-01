"""
Data-driven UI test runner with intent-based architecture.

Discovers YAML intent files in tests/ui/intents/ and runs each one.  If a
generated implementation exists in tests/ui/implementations/, the test uses
deterministic replay (zero Claude calls).  Otherwise, falls back to the Claude
Vision harness.

    # Normal run — uses implementations where available ($0)
    uv run pytest tests/ui/ -v --instance ui-test

    # Generate a specific implementation (~$0.15)
    uv run pytest tests/ui/ --generate <name> --instance ui-test

    # Generate all missing implementations (~$4 one-time)
    uv run pytest tests/ui/ --generate-missing --instance ui-test

    # Diagnose failures (~$0.05 per failure)
    uv run pytest tests/ui/ -v --instance ui-test --diagnose
"""

import importlib.util
import logging
from pathlib import Path

import pytest
import yaml

from .harness import UIHarness
from .replay import ReplayHarness, ReplayStepError

log = logging.getLogger(__name__)

INTENTS_DIR = Path(__file__).parent / "intents"
IMPLEMENTATIONS_DIR = Path(__file__).parent / "implementations"


def discover_tests():
    """Yield (name, intent_path, impl_path_or_none) for every intent."""
    if not INTENTS_DIR.exists():
        return
    for f in sorted(INTENTS_DIR.rglob("*.yaml")):
        name = f.stem
        # Mirror directory structure: intents/recents/foo.yaml → implementations/recents/foo.py
        rel = f.relative_to(INTENTS_DIR).with_suffix(".py")
        impl = IMPLEMENTATIONS_DIR / rel
        yield name, f, impl if impl.exists() else None


def _load_implementation(impl_path: Path):
    """Dynamically load a generated implementation module and return its steps function."""
    spec = importlib.util.spec_from_file_location(
        f"ui_impl.{impl_path.stem}", impl_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.steps


# ── Parametrized test ──────────────────────────────────────────────────

_tests = list(discover_tests())


@pytest.mark.parametrize(
    "intent_name,intent_path,impl_path",
    _tests,
    ids=[name for name, _, _ in _tests],
)
def test_scenario(intent_name, intent_path, impl_path, base_url, page, screenshot_dir, request):
    config = request.config

    generate_name = config.getoption("--generate")
    generate_missing = config.getoption("--generate-missing")
    regenerate_name = config.getoption("--regenerate")
    regenerate_all = config.getoption("--regenerate-all")
    diagnose = config.getoption("--diagnose")
    intents_only = config.getoption("--intents-only")

    # ── Generation mode ────────────────────────────────────────────

    if generate_name and generate_name == intent_name:
        from .generator import generate
        impl_path = generate(intent_path, page, base_url, screenshot_dir)
        log.info("Generated: %s", impl_path)
        return

    if regenerate_name and regenerate_name == intent_name:
        from .generator import generate
        impl_path = generate(intent_path, page, base_url, screenshot_dir)
        log.info("Regenerated: %s", impl_path)
        return

    if regenerate_all:
        from .generator import generate
        impl_path = generate(intent_path, page, base_url, screenshot_dir)
        log.info("Regenerated: %s", impl_path)
        return

    if generate_missing and impl_path is None:
        from .generator import generate
        impl_path = generate(intent_path, page, base_url, screenshot_dir)
        log.info("Generated (was missing): %s", impl_path)
        return

    # ── Skip non-matching when --generate/--regenerate targets a specific intent
    if generate_name and generate_name != intent_name:
        pytest.skip(f"Not generating: {intent_name} (--generate {generate_name})")

    if regenerate_name and regenerate_name != intent_name:
        pytest.skip(f"Not regenerating: {intent_name} (--regenerate {regenerate_name})")

    # ── Replay mode (default when implementation exists) ───────────

    if impl_path and not intents_only:
        log.info("[%s] Running deterministic replay", intent_name)
        steps_fn = _load_implementation(impl_path)
        harness = ReplayHarness(page, base_url, screenshot_dir, intent_name)

        # Auto-accept JS dialogs.
        def _handle_dialog(dialog):
            if dialog.type == "prompt":
                dialog.accept(dialog.default_value or "Test View")
            else:
                dialog.accept()
        page.on("dialog", _handle_dialog)

        # Navigate to start page from hints (mirrors UIHarness.run behavior).
        # The UIHarness always navigates before recording, so generated
        # implementations never include an initial navigate() call.
        from .generator import _load_hints
        replay_hints = _load_hints(intent_path)
        start = (replay_hints.get("start_page") if replay_hints else None) or "/"
        harness.navigate(start)

        try:
            steps_fn(harness)
        except ReplayStepError as e:
            if diagnose:
                _run_diagnosis(intent_name, intent_path, impl_path, e, screenshot_dir)
            raise AssertionError(
                f"Replay failed at step {e.step.number} "
                f"({e.step.action}: {e.step.detail}): {e.step.error}"
            ) from e
        return

    # ── Harness mode (fallback when no implementation exists) ──────

    if not impl_path:
        log.warning(
            "[%s] No implementation found — running Claude harness (expensive). "
            "Generate with: --generate %s",
            intent_name, intent_name,
        )

    intent = yaml.safe_load(intent_path.read_text())
    from .generator import _load_hints
    hints = _load_hints(intent_path)
    harness = UIHarness(page, base_url, screenshot_dir, intent_name, hints=hints)
    result = harness.run(intent["description"])

    assert result["status"] == "done", (
        f"Scenario failed: {result.get('reason', 'unknown')}\n"
        f"Steps taken: {result['steps']}"
    )


def _run_diagnosis(intent_name, intent_path, impl_path, error, screenshot_dir):
    """Run the conflict resolver and print the diagnosis."""
    try:
        from .resolver import ConflictResolver
        resolver = ConflictResolver()
        diagnosis = resolver.diagnose(intent_path, impl_path, error)
        log.warning(
            "\n╔══ CONFLICT DIAGNOSIS: %s ══╗\n"
            "║ Category: %s\n"
            "║ Confidence: %.0f%%\n"
            "║ Explanation: %s\n"
            "║ Recommended: %s\n"
            "╚══════════════════════════════╝",
            intent_name,
            diagnosis.category,
            diagnosis.confidence * 100,
            diagnosis.explanation,
            diagnosis.recommended_action,
        )
    except Exception as diag_err:
        log.error("Diagnosis failed: %s", diag_err)
