"""Versioned reports, portable exports and timestamp-independent comparisons."""

import csv
import io
import json
from html import escape
from pathlib import Path

from . import __version__
from .http import LookupFailure, reject_nonfinite
from .services import now, result


def make_report(results):
    return {
        "schema_version": 1,
        "tool": "GhostTrack Collective",
        "tool_version": __version__,
        "created_at": now(),
        "results": results,
    }


def read_report(path):
    try:
        if Path(path).stat().st_size > 10_485_760:
            raise LookupFailure("Report exceeds the 10 MiB limit.")
        report = json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject_nonfinite)
    except (OSError, ValueError) as exc:
        raise LookupFailure(f"Could not read JSON report: {exc}") from exc
    if (
        not isinstance(report, dict)
        or report.get("schema_version") != 1
        or not isinstance(report.get("results"), list)
    ):
        raise LookupFailure("Expected a GhostTrack JSON report with schema_version 1.")
    seen = set()
    if any(k in report and not isinstance(report[k], str) for k in ("tool_version", "created_at")):
        raise LookupFailure("Report contains invalid collection metadata.")
    for item in report["results"]:
        if (
            not isinstance(item, dict)
            or not all(isinstance(item.get(k), str) for k in ("kind", "target", "status"))
            or not isinstance(item.get("data"), dict)
        ):
            raise LookupFailure("Report contains an invalid result record.")
        key = item["kind"], item["target"]
        if key in seen:
            raise LookupFailure("Report contains duplicate result identities.")
        seen.add(key)
        if any(k in item and not isinstance(item[k], str) for k in ("checked_at", "source")):
            raise LookupFailure("Report contains invalid source metadata.")
        checks = item["data"].get("checks", [])
        if not isinstance(checks, list) or any(
            not isinstance(c, dict)
            or not all(isinstance(c.get(k), str) for k in ("site", "url", "status", "evidence"))
            for c in checks
        ):
            raise LookupFailure("Report contains invalid username evidence.")
    return report


def _stable(value):
    if isinstance(value, dict):
        return {
            k: _stable(v)
            for k, v in value.items()
            if k not in {"checked_at", "created_at", "current_time", "TTL"}
        }
    if isinstance(value, list):
        items = [_stable(v) for v in value]
        if items and all(isinstance(v, dict) for v in items):
            return sorted(items, key=lambda v: json.dumps(v, sort_keys=True))
        return items
    return value


def compare_reports(before, after):
    def index(report):
        return {
            (r["kind"], r["target"]): _stable({"status": r["status"], "data": r["data"]})
            for r in report["results"]
        }

    left, right = index(before), index(after)
    added = [{"kind": k[0], "target": k[1], "after": right[k]} for k in sorted(right.keys() - left.keys())]
    removed = [{"kind": k[0], "target": k[1], "before": left[k]} for k in sorted(left.keys() - right.keys())]
    changed = [
        {"kind": k[0], "target": k[1], "before": left[k], "after": right[k]}
        for k in sorted(left.keys() & right.keys())
        if left[k] != right[k]
    ]
    return make_report(
        [
            result(
                "diff",
                "report comparison",
                "ok",
                {
                    "added": added,
                    "removed": removed,
                    "changed": changed,
                    "summary": {"added": len(added), "removed": len(removed), "changed": len(changed)},
                    "note": "Timestamps, provider current_time, DNS TTLs and record ordering are excluded. A change in availability does not prove account deletion.",
                },
                "Two local GhostTrack JSON reports",
            )
        ]
    )


def rows(report):
    for item in report["results"]:
        base = {k: item.get(k, "") for k in ("kind", "target", "status", "source", "checked_at")}
        checks = item["data"].get("checks")
        if checks:
            for check in checks:
                yield dict(
                    base,
                    status=check["status"],
                    site=check["site"],
                    url=check["url"],
                    evidence=check["evidence"],
                    data="",
                )
        else:
            yield dict(
                base,
                site="",
                url="",
                evidence=item["data"].get("note", ""),
                data=json.dumps(item["data"], ensure_ascii=False, sort_keys=True),
            )


def _csv_value(value):
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text


def render(report, fmt="text"):
    if fmt == "json":
        return json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if fmt == "csv":
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "kind",
                "target",
                "status",
                "site",
                "url",
                "evidence",
                "source",
                "checked_at",
                "data",
            ],
        )
        writer.writeheader()
        writer.writerows({k: _csv_value(v) for k, v in row.items()} for row in rows(report))
        return stream.getvalue()
    if fmt == "html":
        return render_html(report)
    if fmt != "text":
        raise LookupFailure(f"Unknown output format: {fmt}")
    lines = [f"GhostTrack Collective {report.get('tool_version', '')} · {report.get('created_at', '')}"]
    for item in report["results"]:
        lines += [
            "",
            f"{item['kind'].upper()} · {item['target']} [{item['status']}]",
            f"Source: {item.get('source', '')}",
        ]
        for key, value in item["data"].items():
            if key == "checks":
                for check in value:
                    lines.append(f"  {check['site']:<14} {check['status']:<10} {check['url']}")
                    lines.append(f"    {check['evidence']}")
            else:
                display = (
                    json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
                )
                lines.append(f"  {key}: {display}")
    # Prevent terminal control characters from remote metadata and imported reports.
    return "".join(
        c for c in "\n".join(lines) + "\n" if c in "\n\t" or ord(c) >= 32 and not 127 <= ord(c) <= 159
    )


def _link(url, label=None):
    if not isinstance(url, str) or not url.startswith("https://"):
        return escape(str(label or url))
    return f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{escape(label or url)}</a>'


def render_html(report):
    cards = []
    for item in report["results"]:
        data = item["data"]
        checks = data.get("checks")
        if checks:
            details = '<div class="table-wrap"><table><thead><tr><th>Platform</th><th>Result</th><th>Evidence</th></tr></thead><tbody>'
            for c in checks:
                details += (
                    f'<tr data-status="{escape(c["status"], quote=True)}"><td>{_link(c["url"], c["site"])}</td>'
                    f'<td><span class="badge">{escape(c["status"])}</span></td><td>{escape(c["evidence"])}'
                    + (
                        f"<small>{_link(c['probe_url'], 'Evidence endpoint')}</small>"
                        if c.get("probe_url")
                        else ""
                    )
                    + "</td></tr>"
                )
            details += "</tbody></table></div>"
        else:
            details = "<dl>"
            for key, value in data.items():
                if key == "note":
                    continue
                text = (
                    json.dumps(value, ensure_ascii=False, indent=2)
                    if isinstance(value, (dict, list))
                    else str(value)
                )
                display = _link(text) if key == "map_url" else escape(text)
                details += f"<div><dt>{escape(key.replace('_', ' '))}</dt><dd>{display}</dd></div>"
            details += "</dl>"
        cards.append(
            f'<article data-status="{escape(item["status"], quote=True)}"><div class="card-head"><div><p class="eyebrow">{escape(item["kind"])}</p>'
            f'<h2>{escape(item["target"])}</h2></div><span class="badge">{escape(item["status"])}</span></div>'
            f'<p class="provenance">{escape(item.get("checked_at", ""))} · {escape(item.get("source", ""))}</p>'
            f'{details}<p class="note">{escape(str(data.get("note", "")))}</p></article>'
        )
    count = len(report["results"])
    statuses = sorted({r["status"] for r in rows(report)})
    options = "".join(
        f'<option value="{escape(s, quote=True)}">{escape(s.replace("_", " "))}</option>' for s in statuses
    )
    return (
        HTML.replace("{{CREATED}}", escape(report.get("created_at", "")))
        .replace("{{COUNT}}", str(count))
        .replace("{{OPTIONS}}", options)
        .replace("{{CARDS}}", "".join(cards))
    )


HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>GhostTrack · Field report</title><style>
:root{color-scheme:dark;--bg:#0e1219;--panel:#171e29;--line:#2c3748;--muted:#a3b0c4;--text:#edf3fa;--accent:#80e8cb}*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:48px 24px 80px}
a{color:var(--accent);text-underline-offset:4px;overflow-wrap:anywhere}header{border-bottom:1px solid var(--line);padding-bottom:32px;margin-bottom:26px}
.eyebrow{font:12px/1.4 ui-monospace,monospace;letter-spacing:2px;text-transform:uppercase;color:var(--accent);margin:0 0 8px}h1{font-size:clamp(32px,6vw,54px);letter-spacing:-2px;line-height:1.1;margin:12px 0 20px}
h2{margin:0;font-size:24px;overflow-wrap:anywhere}.intro,.provenance,.note,small{color:var(--muted)}.intro{max-width:720px}.meta{display:flex;gap:24px;flex-wrap:wrap;font:13px ui-monospace,monospace}
.toolbar{display:flex;gap:14px;flex-wrap:wrap;margin:24px 0}.toolbar label{display:grid;gap:6px;flex:1;min-width:180px}input,select{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:12px;font:inherit;min-width:0}
input:focus,select:focus{outline:2px solid var(--accent)}article{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:26px;margin:20px 0}.card-head{display:flex;justify-content:space-between;align-items:center;gap:16px}
.badge{border:1px solid #4c6b70;color:var(--accent);font:12px ui-monospace,monospace;padding:6px 10px;border-radius:30px;white-space:nowrap}.provenance{font-size:12px;overflow-wrap:anywhere}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;text-align:left}th{font-size:12px;text-transform:uppercase;color:var(--muted);letter-spacing:1px}th,td{padding:14px 10px;border-bottom:1px solid var(--line);vertical-align:top}td:first-child{min-width:140px}td:nth-child(2){min-width:125px}small{display:block;margin-top:7px}
dl{margin:20px 0}dl>div{display:grid;grid-template-columns:minmax(130px,1fr) 3fr;gap:16px;padding:9px 0;border-bottom:1px solid var(--line)}dt{color:var(--muted)}dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;min-width:0}.note{font-size:13px;margin-bottom:0}footer{font-size:12px;color:var(--muted);margin-top:32px}[hidden]{display:none!important}
@media(max-width:600px){main{padding:28px 14px}article{padding:18px}dl>div{grid-template-columns:1fr;gap:2px}.meta{gap:12px}.badge{font-size:11px}}
@media print{:root{color-scheme:light;--bg:white;--panel:white;--text:#111;--muted:#444;--line:#ccc;--accent:#15665a}.toolbar{display:none}article{break-inside:avoid}main{padding:0}}
</style></head><body><main><header><p class="eyebrow">GhostTrack / Collective edition</p><h1>Evidence, in context.</h1>
<p class="intro">A portable field report for public lookup results. Every result keeps its source and uncertainty visible. Matching handles alone do not establish identity.</p>
<div class="meta"><span>{{COUNT}} targets</span><span>{{CREATED}}</span><span>Offline report · no external assets</span></div></header>
<div class="toolbar"><label>Search report<input id="search" type="search" placeholder="Target, platform or evidence…"></label><label>Result status<select id="status"><option value="">All results</option>{{OPTIONS}}</select></label></div>
<p id="visible" aria-live="polite"></p><section aria-label="Lookup results">{{CARDS}}</section><footer>Original project by HunxByts · Collective edition by isiliconx. This file makes no network requests; external links open only when selected.</footer></main>
<script>
const search=document.getElementById('search'),status=document.getElementById('status');
function filter(){const q=search.value.toLowerCase(),s=status.value;let count=0;document.querySelectorAll('article').forEach(card=>{const rows=[...card.querySelectorAll('tbody tr')];const target=card.querySelector('h2').textContent.toLowerCase();if(rows.length){rows.forEach(row=>row.hidden=!!((s&&row.dataset.status!==s)||(q&&!target.includes(q)&&!row.textContent.toLowerCase().includes(q))));card.hidden=rows.every(row=>row.hidden)}else{card.hidden=!!((s&&card.dataset.status!==s)||(q&&!card.textContent.toLowerCase().includes(q)))}if(!card.hidden)count++});document.getElementById('visible').textContent=count+(count===1?' target shown':' targets shown')}
search.addEventListener('input',filter);status.addEventListener('change',filter);filter();
</script></body></html>"""
