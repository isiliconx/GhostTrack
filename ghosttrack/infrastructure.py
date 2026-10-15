"""Passive public DNS inspection and a single-request HTTPS status check."""

import ipaddress
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlsplit, urlunsplit

from .http import HttpClient, LookupFailure, get_json
from .services import result

RECORD_TYPES = ("A", "AAAA", "MX", "NS", "TXT", "CAA")


def normalize_domain(value):
    value = value.strip().rstrip(".")
    try:
        value = value.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise LookupFailure("Invalid internationalized domain name.") from exc
    if (
        len(value) > 253
        or "." not in value
        or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in value.split("."))
    ):
        raise LookupFailure("Enter a domain such as example.com, without a scheme, port or path.")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    raise LookupFailure("Use the ip command for IP addresses.")


def domain_lookup(domain, *, client=None, offline=False):
    domain = normalize_domain(domain)
    if offline:
        return result(
            "domain",
            domain,
            "local",
            {"ascii_domain": domain, "note": "Domain syntax normalized locally; DNS was not queried."},
            "IDNA (offline)",
        )
    client = client or HttpClient()

    def query(record_type):
        url = f"https://dns.google/resolve?name={quote(domain, safe='')}&type={record_type}"
        item = {"type": record_type, "source": url}
        try:
            body = get_json(client, url)
            if not isinstance(body, dict) or type(body.get("Status")) is not int:
                raise LookupFailure("DNS provider returned an invalid response.")
            answers = body.get("Answer", [])
            if not isinstance(answers, list) or any(not isinstance(a, dict) for a in answers):
                raise LookupFailure("DNS provider returned invalid answer records.")
            return dict(
                item,
                status="ok" if body["Status"] == 0 else "not_found" if body["Status"] == 3 else "error",
                dns_status=body["Status"],
                dnssec_authenticated=body.get("AD", False),
                answers=[{k: a.get(k) for k in ("name", "type", "TTL", "data")} for a in answers],
            )
        except LookupFailure as exc:
            return dict(item, status="error", error=str(exc))

    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(query, RECORD_TYPES))
    status = (
        "partial"
        if any(r["status"] == "error" for r in records)
        else "not_found"
        if all(r["status"] == "not_found" for r in records)
        else "ok"
    )
    return result(
        "domain",
        domain,
        status,
        {
            "records": records,
            "note": "Public DNS via Google DNS-over-HTTPS. Empty answers differ from NXDOMAIN; DNS does not establish ownership.",
        },
        "https://dns.google/resolve",
    )


def website_lookup(value, *, client=None, offline=False):
    value = value.strip()
    if "://" not in value:
        value = "https://" + value
    try:
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.port not in (None, 443)
        ):
            raise ValueError
        host = normalize_domain(parts.hostname)
    except (ValueError, LookupFailure) as exc:
        raise LookupFailure("Enter a public HTTPS domain URL without credentials or a custom port.") from exc
    url = urlunsplit(("https", host, parts.path or "/", parts.query, ""))
    if offline:
        return result(
            "website",
            url,
            "local",
            {"url": url, "note": "URL syntax checked locally; website was not contacted."},
            "URL parser (offline)",
        )
    response = (client or HttpClient()).get(url)
    headers = {k.lower(): v for k, v in response.headers.items()}
    status = (
        "ok"
        if 200 <= response.status < 300
        else "redirect"
        if 300 <= response.status < 400
        else "blocked"
        if response.status in (401, 403, 429)
        else "not_found"
        if response.status in (404, 410)
        else "error"
    )
    return result(
        "website",
        url,
        status,
        {
            "http_status": response.status,
            "content_type": headers.get("content-type"),
            "redirect_to": headers.get("location"),
            "note": "One HTTPS GET; redirects are reported without being followed. Status does not prove site safety or availability from other networks.",
        },
        url,
    )
