"""
Hand-written implementation for user_switching_different_collections.

Creates users via API to trigger multi-user mode, then switches between
the default user (with demo data) and a new empty user to verify
collection isolation.
"""

import json
import ssl
import urllib.request


def _api(base_url, method, path, data=None):
    """Make an API call to the test instance."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    url = f"{base_url}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.loads(resp.read())


def steps(harness):
    base = harness.base_url

    # Create a user to trigger multi-user migration (creates "default" too)
    _api(base, "POST", "/api/users", {"name": "switchtest"})

    # Navigate to collection as "default" user (has demo data)
    harness.page.context.add_cookies([{
        "name": "mtgc_user",
        "value": "default",
        "url": base,
    }])
    harness.navigate("/collection")

    # Wait for collection to load — default user should have cards
    harness.wait_for_text("entries")
    harness.assert_text_present("entries")
    harness.screenshot("default_user_collection")

    # Verify default user has cards by checking status text contains "entries"
    status = harness.page.locator("#status").text_content()
    assert "entries" in status, f"Default user should have entries, got: {status}"

    # Switch to the new empty user
    harness.page.context.add_cookies([{
        "name": "mtgc_user",
        "value": "switchtest",
        "url": base,
    }])
    harness.navigate("/collection")

    # Wait for empty state
    harness.wait_for_text("No cards found")
    harness.assert_text_present("No cards found")

    harness.screenshot("final_state")
