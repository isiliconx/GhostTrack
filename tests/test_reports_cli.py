import csv
import io
import json
from copy import deepcopy

import pytest

from ghosttrack import cli
from ghosttrack.http import LookupFailure
from ghosttrack.reports import compare_reports, make_report, read_report, render
from ghosttrack.services import ip_lookup, result, username_lookup


def test_json_roundtrip(tmp_path):
    report = make_report([ip_lookup("127.0.0.1")])
    path = tmp_path / "report.json"
    path.write_text(render(report, "json"), encoding="utf-8")
    assert read_report(path) == report


@pytest.mark.parametrize(
    "bad",
    [
        [],
        {},
        {"schema_version": 2, "results": []},
        {"schema_version": 1, "results": [None]},
        {"schema_version": 1, "results": [], "created_at": 3},
    ],
)
def test_report_validation(tmp_path, bad):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(LookupFailure):
        read_report(path)


def test_invalid_username_evidence_in_import(tmp_path):
    report = make_report([result("username", "alice", "ok", {"checks": [None]}, "local")])
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(LookupFailure):
        read_report(path)


def test_diff_ignores_timestamps_dns_ttls_and_order():
    first = make_report(
        [
            result(
                "domain",
                "example.com",
                "ok",
                {"records": [{"name": "a", "TTL": 100}, {"name": "b", "TTL": 200}], "current_time": "then"},
                "provider",
            )
        ]
    )
    second = deepcopy(first)
    second["created_at"] = "later"
    second["results"][0]["checked_at"] = "later"
    second["results"][0]["data"]["current_time"] = "later"
    second["results"][0]["data"]["records"] = [{"name": "b", "TTL": 3}, {"name": "a", "TTL": 2}]
    assert compare_reports(first, second)["results"][0]["data"]["summary"] == {
        "added": 0,
        "removed": 0,
        "changed": 0,
    }


def test_diff_detects_added_removed_and_changed():
    before = make_report([ip_lookup("127.0.0.1"), ip_lookup("192.168.1.1")])
    after = make_report([ip_lookup("127.0.0.1"), ip_lookup("::1")])
    after["results"][0]["data"]["scope"] = "changed"
    assert compare_reports(before, after)["results"][0]["data"]["summary"] == {
        "added": 1,
        "removed": 1,
        "changed": 1,
    }


def test_html_escapes_imported_content_and_url_attributes():
    payload = '<img src=x onerror="alert(1)">'
    report = make_report(
        [
            result(
                "username",
                payload,
                "ok",
                {
                    "checks": [
                        {
                            "site": payload,
                            "status": "unknown",
                            "url": 'https://example.com/" onmouseover="alert(1)',
                            "evidence": payload,
                            "probe_url": "javascript:alert(1)",
                        }
                    ]
                },
                payload,
            )
        ]
    )
    html = render(report, "html")
    assert payload not in html
    assert "&lt;img" in html
    assert 'href="javascript:' not in html
    assert 'href="https://example.com/&quot; onmouseover=&quot;alert(1)"' in html
    assert "default-src 'none'" in html


def test_csv_is_flat_and_neutralizes_formula_injection():
    report = make_report([result("phone", "+12025550123", "ok", {"note": "=1+1"}, "local")])
    row = next(csv.DictReader(io.StringIO(render(report, "csv"))))
    assert row["target"] == "'+12025550123"
    assert row["evidence"] == "'=1+1"


def test_terminal_control_characters_are_removed():
    text = render(make_report([result("ip", "\x1b[31m", "ok", {"note": "\x1b[2J"}, "local")]))
    assert "\x1b" not in text


def test_batch_error_isolation_and_normalized_deduplication(tmp_path, capsys):
    path = tmp_path / "targets.txt"
    path.write_text("ip invalid\nip 127.0.0.1\nip 127.0.0.1\nphone +1 202-555-0123\nphone +12025550123\n")
    assert cli.main(["batch", str(path), "--offline", "--format", "json"]) == 1
    results = json.loads(capsys.readouterr().out)["results"]
    assert len(results) == 3
    assert results[0]["status"] == "error"
    assert results[1]["status"] == "local"
    assert results[2]["status"] == "ok"


@pytest.mark.parametrize("content", ["", "# comment\n", "unknown target", "ip"])
def test_bad_batch_file_fails_before_requests(tmp_path, capsys, content):
    path = tmp_path / "targets.txt"
    path.write_text(content)
    assert cli.main(["batch", str(path), "--offline"]) == 2
    assert "Error:" in capsys.readouterr().err


def test_batch_limit(tmp_path):
    path = tmp_path / "targets.txt"
    path.write_text("\n".join(f"username user{i}" for i in range(101)))
    with pytest.raises(LookupFailure):
        cli.read_targets(path)


def test_cli_json_stdout_and_output_notice_stderr(tmp_path, capsys):
    out = tmp_path / "output.json"
    assert cli.main(["ip", "127.0.0.1", "--format", "json", "-o", str(out)]) == 0
    streams = capsys.readouterr()
    assert streams.out == ""
    assert "Saved json" in streams.err
    assert json.loads(out.read_text())["schema_version"] == 1


@pytest.mark.parametrize("args", [["ip", "bad"], ["phone", "2025550123"], ["my-ip", "--offline"]])
def test_cli_lookup_errors_are_structured(args, capsys):
    assert cli.main(args + ["--format", "json"]) == 1
    assert json.loads(capsys.readouterr().out)["results"][0]["status"] == "error"


@pytest.mark.parametrize("value", ["nan", "inf", "0", "-1", "61"])
def test_cli_invalid_timeout(value, capsys):
    assert cli.main(["ip", "127.0.0.1", "--timeout", value]) == 2
    assert "Timeout" in capsys.readouterr().err


def test_report_render_does_not_contact_network(tmp_path, capsys):
    path = tmp_path / "saved.json"
    path.write_text(render(make_report([username_lookup("octocat", offline=True)]), "json"))
    assert cli.main(["report", str(path), "--format", "html"]) == 0
    assert "<html" in capsys.readouterr().out


def test_iterative_menu_survives_many_invalid_options(monkeypatch, capsys):
    answers = iter(["invalid"] * 1100 + ["0"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert cli.interactive() == 0
    assert "Choose an option" in capsys.readouterr().out


def test_interactive_target_cannot_inject_cli_flags(monkeypatch, capsys):
    answers = iter(["1", "--version", "0"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert cli.interactive() == 0
    assert "valid IPv4" in capsys.readouterr().err
