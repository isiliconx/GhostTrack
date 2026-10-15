import pytest
import requests

from ghosttrack.http import MAX_BYTES, HttpClient, LookupFailure, Response


@pytest.mark.parametrize("body", ["not json", "NaN", '{"value":Infinity}'])
def test_bad_json(body):
    with pytest.raises(LookupFailure):
        Response(200, "https://example.com", body).json()


def test_https_only():
    with pytest.raises(LookupFailure):
        HttpClient().get("http://example.com")


def test_transport_has_timeouts_no_redirects_and_body_limit(monkeypatch):
    class FakeResponse:
        status_code = 200
        url = "https://example.com/"
        encoding = "utf-8"
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def iter_content(self, size):
            yield b"x" * (MAX_BYTES + 1)

    def get(session, url, **kwargs):
        assert kwargs["timeout"] == (3, 3)
        assert kwargs["allow_redirects"] is False
        assert kwargs["stream"] is True
        retry = session.get_adapter(url).max_retries
        assert retry.status == 0
        assert retry.respect_retry_after_header is False
        return FakeResponse()

    monkeypatch.setattr(requests.Session, "get", get)
    with pytest.raises(LookupFailure, match="1 MiB"):
        HttpClient(timeout=3).get("https://example.com/")


@pytest.mark.parametrize(
    "error", [requests.Timeout(), requests.ConnectionError(), requests.exceptions.SSLError()]
)
def test_transport_errors_are_recoverable(monkeypatch, error):
    def get(*args, **kwargs):
        raise error

    monkeypatch.setattr(requests.Session, "get", get)
    with pytest.raises(LookupFailure):
        HttpClient().get("https://example.com")
