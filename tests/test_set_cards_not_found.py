"""Scryfall answers 404 not_found to a search matching nothing: an empty set, not a failure."""
import pytest
import requests

from mtg_collector.services.bulk_import import ScryfallBulkClient


class Resp:
    def __init__(self, status, body, headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.url = "https://api.scryfall.com/cards/search"
        self.content = b"{}"

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} Client Error")


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}
        self.calls = 0

    def request(self, *a, **k):
        self.calls += 1
        return self.responses.pop(0)


@pytest.fixture
def client(monkeypatch):
    class Run:
        def land_bytes(self, **_):
            pass

    monkeypatch.setattr("mtg_collector.services.bulk_import.current_run", lambda: Run())
    monkeypatch.setattr("mtg_collector.services.bulk_import.time.sleep", lambda s: None)
    c = ScryfallBulkClient()
    return c


NOT_FOUND = {"object": "error", "code": "not_found", "status": 404, "details": "no cards"}


def test_not_found_is_an_empty_set(client):
    client.session = Session([Resp(404, NOT_FOUND)])
    assert client.get_set_cards("rfin") == []
    assert client.empty_sets == {"rfin"}


def test_other_404_body_fails(client):
    client.session = Session([Resp(404, {"object": "error", "code": "bad_request"})])
    with pytest.raises(RuntimeError, match="rfin"):
        client.get_set_cards("rfin")


def test_404_without_json_fails(client):
    client.session = Session([Resp(404, ValueError("html"))])
    with pytest.raises(RuntimeError):
        client.get_set_cards("rfin")


def test_429_retries(client):
    client.session = Session([
        Resp(429, {}, {"Retry-After": "0"}),
        Resp(200, {"object": "list", "data": [{"id": "a"}], "has_more": False}),
    ])
    assert client.get_set_cards("abc") == [{"id": "a"}]
    assert client.session.calls == 2
