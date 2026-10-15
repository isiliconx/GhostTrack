"""Bounded HTTPS transport. Sessions are isolated between worker threads."""

import json
import math
from dataclasses import dataclass, field

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

MAX_BYTES = 1_048_576


def reject_nonfinite(value):
    raise LookupFailure("JSON contains a non-finite numeric constant.")


class LookupFailure(ValueError):
    """An expected lookup failure that can be shown without a traceback."""


@dataclass(frozen=True)
class Response:
    status: int
    url: str
    body: str
    headers: dict = field(default_factory=dict)

    def json(self):
        try:
            return json.loads(self.body, parse_constant=reject_nonfinite)
        except ValueError as exc:
            raise LookupFailure("Service returned invalid JSON.") from exc


class HttpClient:
    def __init__(self, timeout=8.0, retries=1):
        if not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise LookupFailure("Timeout must be greater than 0 and at most 60 seconds.")
        if retries not in (0, 1, 2):
            raise LookupFailure("Retries must be 0, 1, or 2.")
        self.timeout = timeout
        self.retries = retries

    def get(self, url):
        if not url.startswith("https://"):
            raise LookupFailure("Only HTTPS requests are supported.")
        retry = Retry(
            total=self.retries,
            connect=self.retries,
            read=0,
            status=0,
            redirect=0,
            backoff_factor=0.25,
            respect_retry_after_header=False,
            allowed_methods={"GET"},
        )
        try:
            with requests.Session() as session:
                session.headers.update(
                    {
                        "User-Agent": "GhostTrack-Collective/3.0 (public lookup)",
                        "Accept": "application/json,text/html;q=0.9,*/*;q=0.5",
                    }
                )
                session.mount("https://", HTTPAdapter(max_retries=retry))
                with session.get(
                    url, timeout=(min(5, self.timeout), self.timeout), allow_redirects=False, stream=True
                ) as response:
                    chunks, size = [], 0
                    for chunk in response.iter_content(16384):
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise LookupFailure("Response exceeded the 1 MiB limit.")
                        chunks.append(chunk)
                    body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
                    return Response(response.status_code, response.url, body, dict(response.headers))
        except requests.Timeout as exc:
            raise LookupFailure("Request timed out.") from exc
        except requests.RequestException as exc:
            raise LookupFailure(f"Network request failed ({type(exc).__name__}).") from exc


def get_json(client, url):
    response = client.get(url)
    if response.status != 200:
        raise LookupFailure(f"Service returned HTTP {response.status}.")
    return response.json()
