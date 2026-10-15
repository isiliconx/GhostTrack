import json
import threading
import time

import pytest

from ghosttrack.http import LookupFailure, Response
from ghosttrack.infrastructure import domain_lookup, normalize_domain, website_lookup
from ghosttrack.services import ip_lookup, my_ip, phone_lookup, username_lookup
from ghosttrack.sites import SITES, Site


class Client:
    def __init__(self, status=200, body=None, headers=None):
        self.calls = []
        self.status = status
        self.body = json.dumps(body) if not isinstance(body, str) else body
        self.headers = headers or {}

    def get(self, url):
        self.calls.append(url)
        if isinstance(self.status, Exception):
            raise self.status
        return Response(self.status, url, self.body, self.headers)


@pytest.mark.parametrize(
    "address,scope",
    [
        ("127.0.0.1", "loopback"),
        ("192.168.1.1", "private"),
        ("::1", "loopback"),
        ("224.0.0.1", "multicast"),
        ("169.254.1.1", "link-local"),
        ("0.0.0.0", "unspecified"),
        ("2001:db8::1", "private"),
    ],
)
def test_non_public_ip_never_contacts_provider(address, scope):
    client = Client(status=LookupFailure("must not call"))
    record = ip_lookup(address, client=client)
    assert record["status"] == "local"
    assert record["data"]["scope"] == scope
    assert not client.calls


def test_ip_preserves_precision_and_handles_missing_nested_fields():
    client = Client(
        body={
            "success": True,
            "ip": "1.1.1.1",
            "latitude": -6.208763,
            "longitude": 106.845599,
            "timezone": None,
        }
    )
    data = ip_lookup("1.1.1.1", client=client)["data"]
    assert "-6.208763%2C106.845599" in data["map_url"]
    assert data["timezone"]["current_time"] is None
    assert client.calls == ["https://ipwho.is/1.1.1.1"]


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"success": False},
        {"success": True, "ip": "8.8.8.8"},
        {"success": True, "ip": "1.1.1.1", "connection": []},
    ],
)
def test_ip_rejects_bad_provider_response(body):
    with pytest.raises(LookupFailure):
        ip_lookup("1.1.1.1", client=Client(body=body))


@pytest.mark.parametrize("value", ["", "host.example", "1.1.1.1/path", "999.1.1.1"])
def test_invalid_ip(value):
    with pytest.raises(LookupFailure):
        ip_lookup(value)


def test_public_ip_offline():
    assert ip_lookup("8.8.8.8", offline=True)["status"] == "local"


@pytest.mark.parametrize("body", [[], None, {"ip": "nope"}])
def test_my_ip_rejects_invalid_json_shape(body):
    with pytest.raises(LookupFailure):
        my_ip(client=Client(body=body))


def test_my_ip():
    assert my_ip(client=Client(body={"ip": "2001:4860:4860::8888"}))["data"]["ip"] == "2001:4860:4860::8888"


def test_phone_international_and_national_agree():
    international = phone_lookup("+1 202-555-0123")
    national = phone_lookup("2025550123", region="us")
    assert international["target"] == national["target"] == "+12025550123"
    assert international["data"]["valid"]


@pytest.mark.parametrize(
    "number,region",
    [("2025550123", None), ("+12025550123", "XX"), ("abc", "US"), ("", "US"), ("+1<script>", None)],
)
def test_phone_input_errors(number, region):
    with pytest.raises(LookupFailure):
        phone_lookup(number, region=region)


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (200, {"login": "OctoCat"}, "found"),
        (200, {"login": "other"}, "unknown"),
        (200, "<html>sign in</html>", "error"),
        (200, [], "unknown"),
        (404, {}, "not_found"),
        (410, {}, "not_found"),
        (403, {}, "blocked"),
        (429, {}, "blocked"),
        (302, {}, "unknown"),
        (500, {}, "error"),
        (LookupFailure("Request timed out."), {}, "error"),
    ],
)
def test_username_evidence(status, body, expected):
    result = username_lookup("octocat", sites=["GitHub"], client=Client(status, body))
    assert result["data"]["checks"][0]["status"] == expected


@pytest.mark.parametrize(
    "body,expected",
    [
        ([], "not_found"),
        ([{"username": "OCTOCAT"}], "found"),
        ([{"username": "other"}], "unknown"),
        ({}, "unknown"),
    ],
)
def test_gitlab_exact_match(body, expected):
    data = username_lookup("octocat", sites=["GitLab"], client=Client(body=body))["data"]
    assert data["checks"][0]["status"] == expected


def test_reddit_exact_match():
    data = username_lookup("octocat", sites=["Reddit"], client=Client(body={"data": {"name": "octocat"}}))[
        "data"
    ]
    assert data["checks"][0]["status"] == "found"


@pytest.mark.parametrize(
    "body,expected",
    [
        ("<html>Sign in</html>", "unknown"),
        ('"hydratable":"user"', "likely"),
        ("We can’t find that user.", "not_found"),
    ],
)
def test_html_never_confirms_on_status_alone(body, expected):
    data = username_lookup("octocat", sites=["SoundCloud"], client=Client(body=body))["data"]
    assert data["checks"][0]["status"] == expected


def test_manual_links_and_offline_never_send_requests():
    client = Client(status=LookupFailure("must not call"))
    assert username_lookup("octocat", sites=["Instagram"], client=client)["data"]["summary"] == {"unknown": 1}
    assert username_lookup("octocat", client=client, offline=True)["data"]["checks"]
    assert not client.calls


@pytest.mark.parametrize("value", ["", "../../etc", "alice?query=x", "a b", "<script>", "a" * 65])
def test_bad_usernames(value):
    with pytest.raises(LookupFailure):
        username_lookup(value, offline=True)


def test_platform_syntax_and_site_selection():
    client = Client()
    data = username_lookup("a_b", sites=["github"], client=client)["data"]
    assert data["checks"][0]["status"] == "invalid"
    assert not client.calls
    with pytest.raises(LookupFailure):
        username_lookup("octocat", sites=["typo"])


def test_site_errors_are_isolated_and_workers_are_bounded(monkeypatch):
    import ghosttrack.services as services

    lock = threading.Lock()
    active = peak = 0

    class ConcurrentClient:
        def get(self, url):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.01)
            with lock:
                active -= 1
            if url.endswith("0"):
                raise LookupFailure("Connection failed")
            return Response(200, url, '{"login":"octocat"}')

    sites = tuple(Site(str(i), f"https://example.com/{i}", detector="github") for i in range(6))
    monkeypatch.setattr(services, "select_sites", lambda names: sites)
    result = username_lookup("octocat", workers=2, client=ConcurrentClient())
    assert len(result["data"]["checks"]) == 6
    assert result["status"] == "partial"
    assert peak <= 2
    assert result["data"]["checks"][1]["status"] == "found"


def test_no_duplicate_platforms():
    assert len({s.name.casefold() for s in SITES}) == len(SITES)


@pytest.mark.parametrize(
    "value", ["http://example.com", "example.com/path", "foo..com", "-foo.com", "1.1.1.1", "localhost"]
)
def test_bad_domain(value):
    with pytest.raises(LookupFailure):
        normalize_domain(value)


def test_idna_domain():
    assert normalize_domain("BÜCHER.de.") == "xn--bcher-kva.de"


@pytest.mark.parametrize("status,expected", [(0, "ok"), (3, "not_found"), (2, "partial")])
def test_dns_status_distinguishes_nxdomain_and_servfail(status, expected):
    client = Client(body={"Status": status, "AD": True})
    record = domain_lookup("example.com", client=client)
    assert record["status"] == expected
    assert len(record["data"]["records"]) == 6
    assert all(url.startswith("https://dns.google/") for url in client.calls)


def test_domain_offline():
    assert domain_lookup("example.com", offline=True)["status"] == "local"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:pass@example.com",
        "https://example.com:444",
        "https://localhost",
        "https://127.0.0.1",
    ],
)
def test_bad_website_url(url):
    with pytest.raises(LookupFailure):
        website_lookup(url)


def test_website_reports_redirect_without_following():
    client = Client(302, "", {"Location": "https://elsewhere.example/"})
    record = website_lookup("example.com", client=client)
    assert record["status"] == "redirect"
    assert record["data"]["redirect_to"] == "https://elsewhere.example/"
    assert len(client.calls) == 1
