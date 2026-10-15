# GhostTrack Collective

A modernized fork of [GhostTrack by HunxByts](https://github.com/HunxByts/GhostTrack), maintained under [isiliconx/GhostTrack](https://github.com/isiliconx/GhostTrack).

Public IP information, offline phone metadata, public username evidence, domain DNS records, and HTTPS website checks — with a scriptable CLI and portable reports. Python 3.10+; Linux, macOS, Windows, and Termux.

## What changed

This edition combines selected improvements from the fork network with a new reporting workflow. The [fork review](docs/fork-review.md) records the sources, scope, and decisions; the [audit snapshot](docs/fork-audit.json) records the examined default branches.

- HTTPS requests with connect/read timeouts, limited connection retries, bounded response sizes, and isolated failures. Rate limits are reported without retrying them.
- IPv4 and IPv6 validation, offline classification for local addresses, optional IP fields, and map links that retain decimal coordinates.
- Offline phone validation, number types, formats, original-carrier metadata, and explicit country selection for national numbers.
- Concurrent username checks with per-platform syntax checks and evidence. Exact API matches, probable HTML matches, missing profiles, blocked requests, and manual links stay distinct.
- Public A, AAAA, MX, NS, TXT, and CAA records through DNS over HTTPS, plus a one-request website status checker.
- **Mixed-target batches** with deduplication and per-target error isolation.
- **Versioned JSON, flat CSV, terminal, and self-contained HTML reports.** The HTML view has search, status filters, source links, and print styles; it works offline with no external assets.
- **Report comparison** shows added, removed, and changed results while ignoring timestamps, DNS TTLs, and record ordering.
- An iterative menu, installable `ghosttrack` command, container recipe, and cross-platform CI.

## Install

```sh
git clone https://github.com/isiliconx/GhostTrack.git
cd GhostTrack
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
ghosttrack --help
```

On Windows PowerShell:

```powershell
git clone https://github.com/isiliconx/GhostTrack.git
cd GhostTrack
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install .
.\.venv\Scripts\ghosttrack --help
```

On Termux, install `git` and `python` with `pkg install git python`, then follow the installation steps above. Debian/Ubuntu may need `python3-venv` installed. Activation is optional: invoke the virtual environment's Python or command directly.

For source use, `python -m pip install -r requirements.txt` is also supported. The original entry point, `python3 GhostTR.py`, opens the menu in a terminal. Without a terminal it prints help; `ghosttrack interactive` explicitly opens the menu.

## Commands

```sh
ghosttrack ip 1.1.1.1
ghosttrack ip 2001:4860:4860::8888 --format json
ghosttrack ip 192.168.1.1                    # Local classification; no API request
ghosttrack my-ip
ghosttrack phone '+1 202-555-0123'           # Entirely offline
ghosttrack phone 2025550123 --region US
ghosttrack username octocat --sites GitHub,GitLab --workers 2
ghosttrack username octocat --offline       # Profile links only
ghosttrack sites                            # See each platform's verification method
ghosttrack domain example.com
ghosttrack website https://example.com
```

Options follow the subcommand. Network commands accept `--timeout 8`, `--retries 1`, and `--offline`. Timeouts apply to connection and read inactivity, rather than to the total run. Username workers range from 1 to 8; default 4. DNS queries use at most 3 workers. A batch runs targets sequentially while retaining concurrency within a target.

### Reports and batches

```sh
mkdir -p reports
ghosttrack batch examples/targets.txt --offline --format json -o reports/baseline.json
ghosttrack report reports/baseline.json --format html -o reports/baseline.html
ghosttrack report reports/baseline.json --format csv -o reports/baseline.csv
# After a later lookup saved as reports/later.json:
ghosttrack diff reports/baseline.json reports/later.json --format html -o reports/changes.html
```

Open the HTML file directly in a browser. Reports make no network requests; external links open only when selected. CSV formula-like cell values receive a leading apostrophe for spreadsheet safety.

Batch files contain one explicit type and target per line:

```text
# Blank lines and full-line comments are ignored.
ip 1.1.1.1
phone +1 202-555-0123
username octocat
domain example.com
website https://example.com
```

A batch accepts up to 100 unique input targets. Validate file structure before sending requests; malformed target values become individual error records and the remaining targets continue. `--region` and `--sites` apply to every corresponding batch target. `--offline` suppresses all requests; `my-ip` requires network access.

JSON goes to stdout unless `-o` is supplied. File-save notices and command errors go to stderr. No report or lookup history is saved automatically. Exit codes: `0` completed, `1` one or more lookup errors, invalid numbers, blocked websites, or partial username/DNS results, `2` command/file/configuration error, `130` interrupted. A conclusive `not_found` is a completed check, not a transport error.

### Interpreting results

| Status | Meaning |
| --- | --- |
| `found` | A public API returned the exact requested handle. |
| `likely` | Configured HTML profile markers appeared; confirm manually. |
| `not_found` | The queried endpoint returned a missing response or a missing-profile marker. |
| `unknown` | Manual link, redirect, or insufficient evidence. |
| `blocked` | Access restriction or rate limit; existence remains unknown. |
| `error` | Request, provider, or parsing failure. |
| `invalid` | Unsupported handle syntax or a number invalid in the numbering plan. |
| `local` | Local analysis only; no network lookup occurred. |
| `partial` | An aggregate lookup contains errors or blocked checks. |
| `ok` / `redirect` | Completed lookup / website redirect reported without following it. |

Of the 20 profile routes, GitHub, GitLab, and Reddit have exact-handle API checks; Telegram and SoundCloud use weaker HTML evidence. The remaining 15 are explicitly unverified manual links. These services can change or block automated access. A matching username does not identify the same person across sites.

IP geolocation is approximate network information. Phone results describe the numbering plan, not live location, ownership, current carrier after porting, or active service. Online requests disclose the supplied query to the named provider; sources are recorded in reports. Use the tool for public research and authorized checks.

## Development

```sh
python -m pip install -e '.[dev]'
ruff check .
python -m pytest -q
python -m build
```

Tests use fixtures and block live requests. CI runs tests, lint, and wheel/source builds on Linux, macOS, and Windows with Python 3.10 and 3.14. The transport and services can be used separately from the CLI. See [architecture and report format](docs/architecture.md).

Optional container:

```sh
docker build -t ghosttrack .
docker run --rm ghosttrack ip 1.1.1.1
docker run --rm -it ghosttrack interactive
```

The container runs as a non-root user. Reports can be written through a bind mount whose directory is writable by UID 10001. Docker is optional.

## Attribution

Original project and assets: [HunxByts/GhostTrack](https://github.com/HunxByts/GhostTrack). Selected community ideas and fixes are credited in [NOTICE.md](NOTICE.md) and [the fork review](docs/fork-review.md). This edition reimplements the selected ideas in one architecture; it does not merge every fork's commit history. The upstream snapshot did not include a license file, and this fork does not add a license declaration for upstream material.
