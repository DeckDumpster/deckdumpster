"""
Hand-written implementation for user_create_new_empty_collection.

Creates a new user via API, sets the cookie, and verifies the collection
page shows no cards and the user switcher displays the new user's name.
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

    # Create a new user via API
    result = _api(base, "POST", "/api/users", {"name": "freshuser"})
    assert result.get("created") == "freshuser"

    # Verify user appears in the user list
    users = _api(base, "GET", "/api/users")
    assert "freshuser" in users["users"]

    # Set cookie and navigate to collection as the new user
    harness.page.context.add_cookies([{
        "name": "mtgc_user",
        "value": "freshuser",
        "url": base,
    }])
    harness.navigate("/collection")

    # Verify empty collection
    harness.wait_for_text("No cards found")
    harness.assert_text_present("No cards found")

    # Verify user switcher shows the user name
    harness.wait_for_visible("#user-switcher-btn")
    btn_text = harness.page.locator("#user-switcher-btn").text_content().strip()
    assert "freshuser" in btn_text.lower(), f"Switcher should show 'freshuser', got '{btn_text}'"

    harness.screenshot("final_state")
