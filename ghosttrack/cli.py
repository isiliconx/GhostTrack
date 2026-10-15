"""Command line and iterative interactive menu for GhostTrack Collective."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .http import HttpClient, LookupFailure
from .infrastructure import domain_lookup, website_lookup
from .reports import compare_reports, make_report, read_report, render
from .services import ip_lookup, my_ip, phone_lookup, result, username_lookup
from .sites import SITES, select_sites


def parser():
    p = argparse.ArgumentParser(description="GhostTrack Collective — public IP, phone and username lookups.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--format", choices=("text", "json", "csv", "html"), default="text")
    common.add_argument("-o", "--output", type=Path, help="Write a report; no files are saved by default")
    common.add_argument(
        "--timeout", type=float, default=8, help="Connect/read timeout in seconds (0 < n <= 60)"
    )
    common.add_argument(
        "--retries",
        type=int,
        choices=(0, 1, 2),
        default=1,
        help="Connection retries; rate limits are never retried",
    )
    common.add_argument("--offline", action="store_true", help="Disable all network requests")
    ip = sub.add_parser("ip", parents=[common], help="IPv4/IPv6 metadata and approximate public geolocation")
    ip.add_argument("target")
    for command, help_text in (
        ("domain", "Public DNS records over HTTPS"),
        ("website", "Single-request HTTPS website status"),
    ):
        entry = sub.add_parser(command, parents=[common], help=help_text)
        entry.add_argument("target")
    sub.add_parser("my-ip", parents=[common], help="Show the public egress IP seen by ipify")
    phone = sub.add_parser("phone", parents=[common], help="Offline phone numbering-plan metadata")
    phone.add_argument("target")
    phone.add_argument("--region", help="Country code for a national number, for example ID or US")
    username = sub.add_parser("username", parents=[common], help="Public profile evidence and manual links")
    username.add_argument("target")
    username.add_argument("--sites", help="Comma-separated platform names; see the sites command")
    username.add_argument("--workers", type=int, default=4, help="Concurrent checks, 1–8")
    batch = sub.add_parser(
        "batch", parents=[common], help="Look up a mixed target file, with per-target error isolation"
    )
    batch.add_argument("input", type=Path)
    batch.add_argument("--region")
    batch.add_argument("--sites")
    batch.add_argument("--workers", type=int, default=4)
    sub.add_parser("sites", help="List supported platforms and verification methods")
    diff = sub.add_parser("diff", help="Compare saved JSON reports; ignore collection timestamps")
    diff.add_argument("before", type=Path)
    diff.add_argument("after", type=Path)
    diff.add_argument("--format", choices=("text", "json", "csv", "html"), default="text")
    diff.add_argument("-o", "--output", type=Path)
    export = sub.add_parser("report", help="Render a saved JSON report without repeating lookups")
    export.add_argument("input", type=Path)
    export.add_argument("--format", choices=("text", "json", "csv", "html"), default="html")
    export.add_argument("-o", "--output", type=Path)
    sub.add_parser("interactive", help="Open the original-style menu")
    return p


def _site_names(args):
    value = getattr(args, "sites", None)
    return value.split(",") if value else None


def lookup(kind, target, args, client):
    if kind == "domain":
        return domain_lookup(target, client=client, offline=args.offline)
    if kind == "website":
        return website_lookup(target, client=client, offline=args.offline)
    if kind == "ip":
        return ip_lookup(target, client=client, offline=args.offline)
    if kind == "phone":
        return phone_lookup(target, region=getattr(args, "region", None))
    if kind == "username":
        return username_lookup(
            target,
            client=client,
            offline=args.offline,
            sites=_site_names(args),
            workers=getattr(args, "workers", 4),
        )
    if args.offline:
        raise LookupFailure("my-ip requires a network request and cannot run offline.")
    return my_ip(client=client)


def read_targets(path):
    if path.stat().st_size > 1_048_576:
        raise LookupFailure("Batch file exceeds 1 MiB.")
    tasks, seen = [], set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or parts[0] not in {"ip", "phone", "username", "domain", "website"}:
            raise LookupFailure(
                f"Line {line_number}: expected a type (ip, phone, username, domain, website), a space, and a target."
            )
        key = tuple(parts)
        if key not in seen:
            tasks.append(key)
            seen.add(key)
        if len(tasks) > 100:
            raise LookupFailure("A batch can contain at most 100 unique targets.")
    if not tasks:
        raise LookupFailure("Batch file contains no targets.")
    return tasks


def emit(report, args):
    content = render(report, args.format)
    if args.output:
        args.output.write_text(content, encoding="utf-8")
        print(f"Saved {args.format} report to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(content)


def exit_status(report):
    return (
        1 if any(r["status"] in {"error", "invalid", "partial", "blocked"} for r in report["results"]) else 0
    )


def interactive():
    print(f"\nGhostTrack Collective {__version__}\nOriginal by HunxByts · Fork by isiliconx")
    while True:
        try:
            print(
                "\n[1] IP lookup  [2] My IP  [3] Phone metadata  [4] Username lookup\n[5] Domain DNS  [6] Website status  [0] Exit"
            )
            choice = input("Select option: ").strip()
            if choice == "0":
                return 0
            kind = {
                "1": "ip",
                "2": "my-ip",
                "3": "phone",
                "4": "username",
                "5": "domain",
                "6": "website",
            }.get(choice)
            if not kind:
                print("Choose an option from 0 through 6.")
                continue
            target = "self"
            if kind != "my-ip":
                target = input(
                    {
                        "ip": "IP address: ",
                        "phone": "Phone number: ",
                        "username": "Username: ",
                        "domain": "Domain: ",
                        "website": "HTTPS URL: ",
                    }[kind]
                ).strip()
            region = None
            if kind == "phone" and not target.startswith("+"):
                region = input("Two-letter country code (for example ID): ").strip()
            args = argparse.Namespace(offline=False, region=region, sites=None, workers=4)
            item = lookup(kind, target, args, HttpClient())
            print(render(make_report([item])))
            destination = input("Save HTML report to a path (Enter to skip): ").strip()
            if destination:
                Path(destination).write_text(render(make_report([item]), "html"), encoding="utf-8")
                print(f"Saved report to {destination}")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return 0
        except (LookupFailure, OSError, UnicodeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    try:
        if args.command in (None, "interactive"):
            if args.command is None and not sys.stdin.isatty():
                p.print_help()
                return 0
            return interactive()
        if args.command == "sites":
            print("Platform       Verification")
            for site in SITES:
                mode = (
                    "exact-handle public API"
                    if site.detector in {"github", "gitlab", "reddit"}
                    else "HTML markers (likely only)"
                    if site.detector == "html"
                    else "manual link (unverified)"
                )
                print(f"{site.name:<14} {mode}")
            return 0
        if args.command == "diff":
            report = compare_reports(read_report(args.before), read_report(args.after))
        elif args.command == "report":
            report = read_report(args.input)
        else:
            client = HttpClient(args.timeout, args.retries)
            if args.command == "batch":
                select_sites(_site_names(args))
                if not 1 <= args.workers <= 8:
                    raise LookupFailure("Workers must be between 1 and 8.")
                tasks = read_targets(args.input)
            else:
                tasks = [(args.command, getattr(args, "target", "self"))]
            results, seen = [], set()
            for kind, target in tasks:
                try:
                    item = lookup(kind, target, args, client)
                except LookupFailure as exc:
                    item = result(
                        kind, target, "error", {"error": str(exc)}, "Input validation or lookup service"
                    )
                key = item["kind"], item["target"]
                if key not in seen:
                    results.append(item)
                    seen.add(key)
            report = make_report(results)
        emit(report, args)
        return exit_status(report)
    except BrokenPipeError:
        return 0
    except (LookupFailure, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
