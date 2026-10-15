# Architecture and report format

`GhostTR.py`, `python -m ghosttrack`, and the installed `ghosttrack` command enter the same CLI. No module executes a lookup on import.

- `http.py`: HTTPS transport, isolated sessions, connection retries, read/connect timeouts, no automatic redirects, a 1 MiB decompressed body limit, and recoverable failures. It preserves system proxy and TLS trust settings.
- `services.py`: local/public IP, public egress IP, offline phone metadata, and bounded concurrent profile checks.
- `sites.py`: typed platform registry. Add an endpoint, handle syntax, detector, and regression fixture here. A platform without a detector remains a manual link.
- `infrastructure.py`: IDNA domain validation, bounded public DNS-over-HTTPS queries, and one-request HTTPS website checks.
- `reports.py`: report validation, JSON/CSV/text/HTML rendering, and comparisons. Imported strings are escaped for HTML, terminal control characters are removed from text, and CSV formula prefixes are neutralized.
- `cli.py`: explicit command arguments, loop-based menu, batch parsing, file I/O, and exit codes.

## JSON schema version 1

```json
{
  "schema_version": 1,
  "tool": "GhostTrack Collective",
  "tool_version": "3.0.0",
  "created_at": "2026-10-15T00:00:00+00:00",
  "results": [
    {
      "kind": "ip",
      "target": "127.0.0.1",
      "status": "local",
      "checked_at": "2026-10-15T00:00:00+00:00",
      "source": "Python ipaddress (offline)",
      "data": {"scope": "loopback"}
    }
  ]
}
```

A result's `(kind, target)` is its identity. Batch output deduplicates normalized identities. Username `data.checks` records `site`, `url`, `probe_url`, `status`, `evidence`, and `http_status`. The parent result includes a summary of per-platform statuses. DNS `data.records` retains per-type status, source, DNS status, DNSSEC authentication flag, and answer records.

Comparison reads two schema-1 reports, indexes identities, and compares status and data. It omits collection timestamps, provider `current_time`, DNS cache `TTL`, and dictionary-record ordering. Source strings outside `data` are not compared. Account-availability changes are observations, not proof of deletion. Changing the set of selected platforms changes the report and is intentionally visible in a comparison.

JSON report imports are limited to 10 MiB. Batch inputs are limited to 1 MiB and 100 unique targets. No server, database, credentials, or default history store is required.

## Provider references

- [ipwho.is documentation](https://ipwhois.io/documentation): public IP metadata.
- [GitHub user API](https://docs.github.com/en/rest/users/users#get-a-user): exact `login` evidence.
- [GitLab users API](https://docs.gitlab.com/api/users/#list-users): public `username` query, exact match verified locally.
- [Google DNS JSON API](https://developers.google.com/speed/public-dns/docs/doh/json): DNS response codes and answer records.
- [python-phonenumbers](https://github.com/daviddrysdale/python-phonenumbers): offline numbering-plan metadata.

Provider availability, response schemas, and rate limits can change. Unit tests isolate behavior from service availability; live smoke checks are separate from CI.
