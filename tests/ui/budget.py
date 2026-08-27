"""Timeout budgets for the UI harness, measured in app time rather than wall clock.

The UI suite's 500 ms interaction budget is a statement about *the app*: after
you click, the page has half a second to answer, and the collection-payload work
exists to keep it there. Playwright can only enforce that as wall clock, and
wall clock on a shared box measures the box.

That is not theoretical. On the deployment box — 4 CPUs, shared with every other
agent's test suite — a `tests/ui -k sets_` run at load average 61-85 produced 14
failures, of which **14 were Playwright timeouts and 0 were assertion failures**
(de-6q2). One of them, `sets_binder_breadcrumb_back_to_the_set_list`, has a
Playwright call log showing the click succeeded and the page navigated: the
behaviour under test held, and the harness raised anyway. A suite that reds
without a single assertion firing is not measuring the app.

So a budget is normalized by how oversubscribed the box is. `host_contention()`
is runnable tasks per CPU, floored at 1.0, which means:

* On a quiet box the factor is 1.0 and every timeout is **byte-identical to what
  it was before** — 500 ms still means 500 ms, and a payload regression still
  reds. Nothing here relaxes the budget on the machine where you measure.
* On a box oversubscribed 8x, 8 x 500 ms of wall clock is 500 ms of app time.
  The budget still measures the app; it just stops charging the app for the
  other seven tenants.

`TIMEOUT_CEILING_MS` is Playwright's own default action timeout, and it is the
line between "slow" and "broken": past the point where Playwright itself would
have given up, no amount of host contention explains it. It caps the inflation
only — it never shrinks a timeout a caller asked for outright.

Two base budgets, because there are two kinds of wait and they cost differently:

* `INTERACTION_BUDGET_MS` — the app's answer to an interaction on a page that is
  already loaded. This is the UX budget.
* `ROUND_TRIP_BUDGET_MS` — anything that includes a server round trip: a page
  load, a text assertion backed by a fetch, and **any action that might
  navigate**. `page.click` blocks until a navigation the click started commits,
  so a 500 ms click timeout was a navigation budget wearing an interaction
  budget's clothes — which is exactly how a successful click failed a test.

**Every timeout-bearing Playwright call in `tests/ui/` must pass one of these,
including the ones that look like they do not need a timeout.** Omitting it does
not mean "no deadline" — it inherits Playwright's 30 s, unscaled and unreadable
at the call site. `tests/test_ui_budget.py` fails the build on either mistake.
"""

import os

#: The app's answer to an interaction on an already-loaded page.
INTERACTION_BUDGET_MS = 500

#: Anything that crosses the network to the server and back.
ROUND_TRIP_BUDGET_MS = 5_000

#: Playwright's own default action timeout — where slow becomes broken.
TIMEOUT_CEILING_MS = 30_000


def host_contention() -> float:
    """Runnable tasks per CPU on this box, floored at 1.0.

    Read from the 1-minute load average, which lags: a box that just went quiet
    still reads busy for a while. That direction is the safe one — it spends
    patience, never a false failure. A box that just got busy reads low, but the
    contention that causes these failures is a whole test suite deep and lasts
    for minutes, not seconds.
    """
    return max(1.0, os.getloadavg()[0] / (os.cpu_count() or 1))


def budget_ms(base_ms: int, contention: float | None = None) -> int:
    """Scale a budget by host contention, capped at the ceiling.

    `contention` is a parameter so a caller can sample it once and hold it for a
    whole scenario: timeouts that drift step to step inside one test make a
    failure impossible to reproduce from its own log.
    """
    if contention is None:
        contention = host_contention()
    return int(min(base_ms * contention, max(base_ms, TIMEOUT_CEILING_MS)))
