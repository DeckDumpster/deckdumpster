"""Guard: every subprocess.run in tests/ carries an explicit timeout= (db-3jcu).

A subprocess.run with no timeout blocks pytest forever when a child hangs —
the suite dies silently at whatever test was active, unnamed. This AST walk
enforces the invariant so the next hung child names itself instead.
"""
import ast
import pathlib

TESTS_ROOT = pathlib.Path(__file__).parent
# subprocess_run.py is the one file allowed to call subprocess.run directly;
# every other file must route through it or carry an explicit timeout=.
EXEMPT = frozenset(["subprocess_run.py", "test_subprocess_timeouts.py"])


def _missing_timeouts(path: pathlib.Path) -> list[int]:
    tree = ast.parse(path.read_text(), filename=str(path))
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "run"
            and isinstance(func.value, ast.Name)
            and func.value.id == "subprocess"
        ):
            if not any(kw.arg == "timeout" for kw in node.keywords):
                lines.append(node.lineno)
    return lines


def test_every_subprocess_run_has_timeout():
    violations = []
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        if path.name in EXEMPT:
            continue
        for lineno in _missing_timeouts(path):
            violations.append(f"{path.relative_to(TESTS_ROOT)}:{lineno}")

    assert not violations, (
        "subprocess.run without timeout= — add timeout= or route through "
        "tests/subprocess_run.py (db-3jcu):\n"
        + "\n".join(f"  {v}" for v in violations)
    )
