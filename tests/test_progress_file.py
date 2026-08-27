"""The pytest progress file is per-checkout (de-bj7)."""

import os

from tests.conftest import _PROGRESS_PATH, _default_progress_path

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def test_distinct_checkouts_get_distinct_paths():
    a = _default_progress_path("/workspaces/gt/deckdumpster/polecats/furiosa/deckdumpster")
    b = _default_progress_path("/workspaces/gt/deckdumpster/polecats/nux/deckdumpster")
    assert a != b


def test_path_lives_inside_the_checkout_that_produced_it():
    root = "/workspaces/gt/deckdumpster/polecats/glory/deckdumpster"
    assert _default_progress_path(root).startswith(root + os.sep)


def test_path_is_the_one_a_monitor_can_name_without_reading_the_run():
    assert _default_progress_path("/checkout") == "/checkout/.pytest_cache/progress.jsonl"


def test_this_run_is_writing_where_it_says_it_is():
    assert _PROGRESS_PATH == os.environ.get(
        "PYTEST_PROGRESS_FILE", _default_progress_path(_REPO_ROOT)
    )
    assert os.path.exists(_PROGRESS_PATH)


def test_the_progress_directory_is_ignored_by_git():
    """Nothing this writes may show up in `git status` — polecats commit from here."""
    marker = os.path.join(_REPO_ROOT, ".pytest_cache", ".gitignore")
    assert os.path.exists(marker), "pytest's cache dir lost its self-ignoring .gitignore"
