# Fork review and integration decisions

Review date: **2026-10-15**. Upstream baseline: [`HunxByts/GhostTrack@a5cb8ad`](https://github.com/HunxByts/GhostTrack/commit/a5cb8ad).

## Scope and evidence

The GitHub fork API returned 2,650 metadata records, representing 2,649 unique repositories. Default-branch queries resolved **2,556** forks; 93 listed repositories could not be resolved by the follow-up queries. The [audit snapshot](fork-audit.json) records the accessible groups and unresolved names. This is a snapshot, not a claim to have inspected every branch or inaccessible repository.

Of the accessible forks, **2,464** had the identical `GhostTR.py` blob as upstream. There were **43 distinct root-script versions**, including the upstream version; another four forks renamed or replaced that file. We fetched those 43 script versions, compared structure and additions, and performed focused review of feature-heavy versions. All 53 returned upstream pull requests were triaged by title; file diffs were inspected for 20 substantive pull requests. [Pull-request evidence](reviewed-pull-requests.json) records the exact source heads and which file diffs were reviewed. Root blob hashes do not detect every change in nested modules; expanded fork trees and relevant PR files were reviewed separately.

The resulting package reimplements compatible ideas in one architecture. It does not indiscriminately merge branches or adopt every feature. The upstream Git history and assets remain in this fork.

## Selected community improvements

| Source | Useful contribution | Implementation in this fork |
| --- | --- | --- |
| [Yaohua-Leo, PR #175](https://github.com/HunxByts/GhostTrack/pull/175), [Pm620, #139](https://github.com/HunxByts/GhostTrack/pull/139), [Urten, #39](https://github.com/HunxByts/GhostTrack/pull/39) | Per-site network failures and bounded requests | Isolated errors, connect/read timeouts, limited connection retries; no retries of rate limits. |
| [CengSin, #174](https://github.com/HunxByts/GhostTrack/pull/174) | HTTPS IP lookup | All outbound requests use HTTPS. |
| [A220man, #162](https://github.com/HunxByts/GhostTrack/pull/162), [CarlM4606aggie](https://github.com/CarlM4606aggie/GhostTrack) | Map coordinate precision | Decimal coordinates preserved and range checked. |
| [SayanDey322, #103](https://github.com/HunxByts/GhostTrack/pull/103), [Mabroukimohamedyassine, #119](https://github.com/HunxByts/GhostTrack/pull/119), [hafilrazz, #131](https://github.com/HunxByts/GhostTrack/pull/131), [lfarssi, #129](https://github.com/HunxByts/GhostTrack/pull/129) | Optional timezone fields | Missing nested fields represented as unavailable instead of crashing or fabricating time values. |
| [Souvik-Dey-2029, #108](https://github.com/HunxByts/GhostTrack/pull/108), [imuday984, #67](https://github.com/HunxByts/GhostTrack/pull/67), [orstro, #124](https://github.com/HunxByts/GhostTrack/pull/124) | Menu/input resilience and duplicate removal | Iterative menu, EOF/interrupt handling, validation, no duplicate platforms. |
| [lixelv, #44](https://github.com/HunxByts/GhostTrack/pull/44), [seilorjunior, #72](https://github.com/HunxByts/GhostTrack/pull/72) | Faster username scanning and structure | Deterministic platform order, bounded thread pool, shared service layer. |
| [Real3dn, #170](https://github.com/HunxByts/GhostTrack/pull/170) | Platform syntax, API probes, soft 404 and HTML evidence | Exact API handle verification, missing markers, weaker `likely` HTML matches, and inconclusive redirects. Avoided the source rule that treats every HTTP 200 as missing on Telegram and the overly broad Pinterest redirect-prefix check. |
| [jimskin03, #165](https://github.com/HunxByts/GhostTrack/pull/165) | Modular services, honest profile results, CLI, tests and containers | Modular package, exact matching, explicit manual links, local metadata, container recipe, regression suite. |
| [Rintu-chowdory, #145](https://github.com/HunxByts/GhostTrack/pull/145), [jmeiracorbal, #56](https://github.com/HunxByts/GhostTrack/pull/56) | Packaging and CI | Installable console command, wheel/source builds, Linux/macOS/Windows CI on Python 3.10/3.14. |
| [NomadUmbra, #114](https://github.com/HunxByts/GhostTrack/pull/114), [aymanbouanouj, #166](https://github.com/HunxByts/GhostTrack/pull/166) | Windows setup | PowerShell instructions and cross-platform tests. |
| [Kryptographer, #65](https://github.com/HunxByts/GhostTrack/pull/65), [djpapzin/Okae](https://github.com/djpapzin/Okae) | More approachable graphical results | Searchable, filterable, printable, self-contained HTML reports. This is a report viewer, not a port of the Electron app or hosted Flask service. |
| [J0S3HDZ](https://github.com/J0S3HDZ/GhostTrack), [reno777](https://github.com/reno777/GhostTrack) | Domain/DNS tools | A/AAAA/MX/NS/TXT/CAA through HTTPS JSON DNS, IDNA validation, per-type errors and DNSSEC evidence. |
| [krataratha, #97](https://github.com/HunxByts/GhostTrack/pull/97) | Website status checking | Validated HTTPS target, one GET, redirects reported without following them. |

Rows that reference only a triaged PR or fork name were corroborated by the reviewed default-branch script or related reviewed diffs; the JSON evidence distinguishes directly retrieved PR file diffs from title triage.

## New work in this edition

1. Mixed-target batches with explicit types, normalization, deduplication, input limits, and recoverable individual failures.
2. A common versioned result envelope with source, collection time, outcome, and evidence.
3. Flat CSV export, JSON re-rendering, and a portable HTML report with offline search and filters.
4. Snapshot comparison that separates added, removed, and changed results, while ignoring timestamps, DNS TTL changes, and record ordering.
5. A no-network mode across lookup types, local IP classification, and no default history retention.
6. HTML escaping, CSV formula protection, terminal control-character filtering, and regression coverage for hostile imported evidence.
7. A durable fork inventory and source-to-feature decision record to make future updates reviewable.

## Considered but not selected

- **Electron and hosted admin/public dashboards:** introduce separate runtime, storage, authentication, and deployment requirements. The portable report viewer covers result browsing while the CLI remains small.
- **KaliLugu's unbounded username permutations and optional Sherlock/nmap integration:** reviewed; retained explicit handles and bounded checks for predictable runs and clearer evidence.
- **Authenticated Instagram follower/story collection and account-availability probing:** require credentials and fragile/private endpoints; excluded from this public-lookup edition.
- **Hash cracking, wordlist subdomain brute force, and bundled virtual environments:** peripheral to the lookup/report workflow and add unnecessary complexity.
- **WHOIS, EXIF extraction, reverse-IP services, and breach-provider integrations:** useful possible follow-ups, but add provider/dependency requirements. This edition includes public DNS and source-backed reporting first.
- **Naive HTTP-200 match rules, plaintext HTTP fallbacks, stale profile routes, swallowed errors, and renamed author banners:** replaced with explicit evidence and preserved attribution.

## Validation

The regression suite blocks live network calls and checks transport limits, IP response validation, precision, offline operation, phone regions, exact username matching, redirects/soft 404s, bounded concurrency, per-site and per-target failures, IDNA domains, DNS status codes, reports, comparison, escaping, and menu behavior. Packaging and a separate small set of live smoke requests validate the entry points and current provider connectivity. Live provider availability is reported separately from deterministic test results.
