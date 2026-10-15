"""Lookup services independent of the terminal and report renderers."""

import ipaddress
import math
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from datetime import timezone as dt_timezone
from urllib.parse import quote

import phonenumbers
from phonenumbers import carrier, geocoder, timezone

from .http import HttpClient, LookupFailure, get_json
from .sites import select_sites


def now():
    return datetime.now(dt_timezone.utc).isoformat(timespec="seconds")


def result(kind, target, status, data, source):
    return {
        "kind": kind,
        "target": target,
        "status": status,
        "checked_at": now(),
        "source": source,
        "data": data,
    }


def ip_lookup(address, *, client=None, offline=False):
    try:
        ip = ipaddress.ip_address(address.strip())
    except ValueError as exc:
        raise LookupFailure("Enter a valid IPv4 or IPv6 address.") from exc
    scope = (
        "loopback"
        if ip.is_loopback
        else "multicast"
        if ip.is_multicast
        else "link-local"
        if ip.is_link_local
        else "unspecified"
        if ip.is_unspecified
        else "private"
        if ip.is_private
        else "reserved"
        if ip.is_reserved
        else "public"
        if ip.is_global
        else "shared / non-global"
    )
    data = {
        "ip": str(ip),
        "version": ip.version,
        "scope": scope,
        "globally_routable": ip.is_global and not ip.is_multicast,
        "reverse_pointer": ip.reverse_pointer,
    }
    if offline or not data["globally_routable"]:
        data["note"] = "Local address classification only; no geolocation request was sent."
        return result("ip", str(ip), "local", data, "Python ipaddress (offline)")
    url = f"https://ipwho.is/{quote(str(ip), safe=':')}"
    remote = get_json(client or HttpClient(), url)
    if not isinstance(remote, dict) or remote.get("success") is not True:
        raise LookupFailure("IP provider rejected the lookup or returned an unexpected response.")
    try:
        if ipaddress.ip_address(remote.get("ip")) != ip:
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise LookupFailure("IP provider returned a different or invalid address.") from exc
    for field in (
        "type",
        "country",
        "country_code",
        "city",
        "region",
        "region_code",
        "continent",
        "continent_code",
        "latitude",
        "longitude",
        "is_eu",
        "postal",
        "calling_code",
        "capital",
        "borders",
    ):
        data[field] = remote.get(field)
    for field, keys in {
        "connection": ("asn", "org", "isp", "domain"),
        "timezone": ("id", "abbr", "is_dst", "offset", "utc", "current_time"),
    }.items():
        obj = remote.get(field)
        if obj is None:
            obj = {}
        if not isinstance(obj, dict):
            raise LookupFailure(f"IP provider returned invalid {field} metadata.")
        data[field] = {key: obj.get(key) for key in keys}
    lat, lon = data["latitude"], data["longitude"]
    if (
        all(type(v) in (int, float) and math.isfinite(v) for v in (lat, lon))
        and -90 <= lat <= 90
        and -180 <= lon <= 180
    ):
        data["map_url"] = f"https://www.google.com/maps/search/?api=1&query={lat}%2C{lon}"
    data["note"] = "Approximate network geolocation; it does not identify a person's precise location."
    return result("ip", str(ip), "ok", data, url)


def my_ip(*, client=None):
    url = "https://api.ipify.org?format=json"
    data = get_json(client or HttpClient(), url)
    try:
        ip = ipaddress.ip_address(data.get("ip"))
    except (ValueError, TypeError, AttributeError) as exc:
        raise LookupFailure("Public IP provider returned an invalid address.") from exc
    return result(
        "my-ip",
        "self",
        "ok",
        {"ip": str(ip), "note": "Public egress address seen by ipify; a VPN or proxy may affect this."},
        url,
    )


def phone_lookup(number, *, region=None):
    number = number.strip()
    if region:
        region = region.upper().strip()
        if region not in phonenumbers.SUPPORTED_REGIONS:
            raise LookupFailure("Use a supported two-letter region, such as ID, GB, or US.")
    if not number.startswith("+") and not region:
        raise LookupFailure("Include a +country code or pass --region for a national number.")
    if not re.fullmatch(r"\+?[0-9().\s-]{2,40}", number):
        raise LookupFailure("Enter a phone number using digits and optional formatting.")
    try:
        parsed = phonenumbers.parse(number, region)
    except phonenumbers.NumberParseException as exc:
        raise LookupFailure(f"Could not parse phone number: {exc}") from exc
    data = {
        "region": phonenumbers.region_code_for_number(parsed),
        "country_code": parsed.country_code,
        "valid": phonenumbers.is_valid_number(parsed),
        "possible": phonenumbers.is_possible_number(parsed),
        "type": phonenumbers.PhoneNumberType.to_string(phonenumbers.number_type(parsed)),
        "area_description": geocoder.description_for_number(parsed, "en"),
        "original_carrier": carrier.name_for_number(parsed, "en"),
        "timezones": list(timezone.time_zones_for_number(parsed)),
    }
    for key, fmt in (
        ("e164", phonenumbers.PhoneNumberFormat.E164),
        ("international", phonenumbers.PhoneNumberFormat.INTERNATIONAL),
        ("national", phonenumbers.PhoneNumberFormat.NATIONAL),
    ):
        data[key] = phonenumbers.format_number(parsed, fmt)
    data["note"] = (
        "Offline numbering-plan metadata; no live location, ownership, active-service or current-carrier verification."
    )
    return result(
        "phone",
        data["e164"],
        "ok" if data["valid"] else "invalid",
        data,
        f"phonenumbers {phonenumbers.__version__} (offline)",
    )


def check_site(site, username, client, offline=False):
    encoded = quote(username, safe="")
    url = site.url.format(u=encoded)
    probe = (site.probe or site.url).format(u=encoded)
    item = {
        "site": site.name,
        "url": url,
        "probe_url": None,
        "status": "unknown",
        "evidence": "Manual profile link; existence has not been checked.",
        "http_status": None,
    }
    if not re.fullmatch(site.pattern, username):
        return dict(item, status="invalid", evidence="Handle does not match this platform's syntax.")
    if offline or site.detector == "manual":
        return item
    item["probe_url"] = probe
    try:
        response = client.get(probe)
        code = response.status
        item["http_status"] = code
        if code in (401, 403, 429, 999):
            return dict(item, status="blocked", evidence=f"Access restricted or rate limited (HTTP {code}).")
        if code in (404, 410):
            return dict(item, status="not_found", evidence=f"Profile endpoint returned HTTP {code}.")
        if 300 <= code < 400:
            return dict(item, evidence="Redirect; a login or landing page cannot confirm a profile.")
        if code != 200:
            return dict(item, status="error", evidence=f"Unexpected HTTP {code}.")
        if site.detector == "html":
            if any(marker.casefold() in response.body.casefold() for marker in site.missing):
                return dict(
                    item, status="not_found", evidence="Page contains a configured missing-profile marker."
                )
            if site.present and all(marker in response.body for marker in site.present):
                return dict(
                    item,
                    status="likely",
                    evidence="Profile page markers present; manual confirmation required.",
                )
            return dict(
                item, evidence="HTTP 200 without profile evidence; could be a soft 404 or login wall."
            )
        body = response.json()
        if site.detector == "github":
            handle = body.get("login") if isinstance(body, dict) else None
        elif site.detector == "gitlab":
            if isinstance(body, list) and not body:
                return dict(
                    item, status="not_found", evidence="Exact-handle API query returned no public users."
                )
            handle = (
                next(
                    (
                        u.get("username")
                        for u in body
                        if isinstance(u, dict)
                        and str(u.get("username", "")).casefold() == username.casefold()
                    ),
                    None,
                )
                if isinstance(body, list)
                else None
            )
        else:
            obj = body.get("data") if isinstance(body, dict) else None
            handle = obj.get("name") if isinstance(obj, dict) else None
        if isinstance(handle, str) and handle.casefold() == username.casefold():
            return dict(item, status="found", evidence="Public API returned an exact matching handle.")
        return dict(item, evidence="API did not provide a matching handle; result is inconclusive.")
    except LookupFailure as exc:
        return dict(item, status="error", evidence=str(exc))


def username_lookup(username, *, client=None, sites=None, workers=4, offline=False):
    username = username.strip().removeprefix("@")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", username):
        raise LookupFailure("Username must be 1–64 letters, digits, dots, underscores or hyphens.")
    if not 1 <= workers <= 8:
        raise LookupFailure("Workers must be between 1 and 8.")
    selected = select_sites(sites)
    client = client or HttpClient()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        checks = list(pool.map(lambda site: check_site(site, username, client, offline), selected))
    counts = dict(Counter(c["status"] for c in checks))
    return result(
        "username",
        username,
        "partial" if counts.get("error") or counts.get("blocked") else "ok",
        {
            "checks": checks,
            "summary": counts,
            "note": "Matching handles do not establish shared identity. Unknown and blocked results are inconclusive.",
        },
        "Public profile endpoints; see per-site evidence",
    )
