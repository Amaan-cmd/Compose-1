import csv
import json
import re

from appscout.page import FLAT_FIELDS, build, buildability, confidence, flat_row

from conftest import make_finding

APPS_CSV = (
    "id,name,website,category,batch\n"
    "acme,Acme,acme.test,CRM and Sales,1\n"
    "globex,Globex,globex.test,CRM and Sales,1\n"
    'initech,Initech,initech.test,"Marketing, Ads, Email and Social",4\n'
)


def record(app_id="acme", name="Acme", **overrides) -> dict:
    data = make_finding().model_dump(mode="json")
    for item in data["evidence"]:
        item["check"] = "exact"
    data.update(
        id=app_id,
        name=name,
        website=f"{app_id}.test",
        category="CRM and Sales",
        batch=1,
        in_composio_catalog=False,
        composio_toolkit_slug="",
        composio_catalog_source="none",
        verification=[
            {"field": field, "result": "supported", "note": "ok"}
            for field in ("auth", "access", "api", "mcp", "composio", "verdict")
        ],
        needs_human_review=False,
        review_reasons=[],
        attempts=1,
        researched_at="2026-11-23T00:00:00+00:00",
        model="research-model",
        critic_model="critic-model",
        usage={"llm_calls": 3, "input_tokens": 1000, "output_tokens": 100, "cached_input_tokens": 0, "critic_tokens": 50, "composio_calls": 1, "composio_usd": 0.004},
        composio_log=[{"tool": "TAVILY_SEARCH", "detail": "Acme MCP server", "charged_usd": 0.004, "log_id": "log_1"}],
    )
    data.update(overrides)
    return data


def data_dir(tmp_path, records):
    (tmp_path / "apps.csv").write_text(APPS_CSV, encoding="utf-8")
    if records is not None:
        (tmp_path / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return tmp_path


def embedded(html: str) -> dict:
    match = re.search(r'<script type="application/json" id="dataset">(.*?)</script>', html, re.S)
    return json.loads(match.group(1))


def test_page_embeds_every_record_and_the_whole_app_list(tmp_path):
    out = tmp_path / "index.html"
    build(data_dir(tmp_path, [record(), record("globex", "Globex")]), out, generated_at="2026-11-23T00:00:00+00:00")
    dataset = embedded(out.read_text(encoding="utf-8"))
    assert [r["id"] for r in dataset["records"]] == ["acme", "globex"]
    assert [app["id"] for app in dataset["apps"]] == ["acme", "globex", "initech"]
    assert len(dataset["flat"]) == 2 and dataset["flat_fields"] == FLAT_FIELDS
    assert dataset["audit"] is None


def test_exports_are_written_with_the_requested_field_names(tmp_path):
    reviewed = record(needs_human_review=True, review_reasons=["auth: unsupported (reason one)", "access is unknown"])
    build(data_dir(tmp_path, [reviewed]), tmp_path / "index.html")
    with (tmp_path / "apps_flat.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == FLAT_FIELDS
    assert rows[0]["app_name"] == "Acme" and rows[0]["buildability_verdict"] == "Ready_Now"
    assert rows[0]["existing_mcp"] == "false" and rows[0]["needs_human_review"] == "true"
    assert rows[0]["verification_notes"] == "auth: unsupported (reason one); access is unknown"
    assert json.loads((tmp_path / "apps.json").read_text(encoding="utf-8"))[0]["id"] == "acme"


def test_verdict_names_are_derived_from_status_and_blocker():
    def verdict(status, blocker):
        return buildability({"verdict": {"status": status, "main_blocker": blocker}})

    assert verdict("buildable_now", "none") == "Ready_Now"
    assert verdict("buildable_with_caveats", "trial_only") == "Conditional"
    assert verdict("blocked", "no_public_api") == "Blocked_No_Public_API"
    assert verdict("blocked", "partner_gate") == "Blocked_Partner_Gated"
    assert verdict("unknown", "other") == "Unknown"


def test_flat_row_counts_only_quotes_found_on_their_pages_and_computes_confidence():
    data = record()
    data["evidence"][0]["check"] = "not_found"
    data["evidence"][1]["check"] = "exact_rendered"
    data["verification"][0]["result"] = "unsupported"
    data["verification"][1]["result"] = "unreachable"
    row = flat_row(data)
    assert (row["quotes_verified"], row["quotes_total"]) == (2, 3)
    assert row["evidence_urls"] == ["https://docs.example.com/start", "https://docs.example.com/api"]
    assert row["confidence_score"] == confidence(data) == 0.67


def test_page_builds_with_no_records_at_all(tmp_path):
    out = tmp_path / "index.html"
    dataset = build(data_dir(tmp_path, None), out)
    assert dataset["records"] == [] and len(dataset["apps"]) == 3
    assert embedded(out.read_text(encoding="utf-8"))["flat"] == []
    assert (tmp_path / "apps_flat.csv").read_text(encoding="utf-8").strip() == ",".join(FLAT_FIELDS)


def test_records_from_before_the_schema_change_are_exported_as_unknown(tmp_path):
    old = record()
    del old["deployment_model"]
    del old["mcp"]["maturity"]
    del old["usage"]["critic_tokens"]
    dataset = build(data_dir(tmp_path, [old]), tmp_path / "index.html")
    assert dataset["flat"][0]["deployment_model"] == "unknown"
    assert dataset["flat"][0]["mcp_maturity"] == "unknown"


def test_text_from_the_web_cannot_break_out_of_the_data_script(tmp_path):
    hostile = record(one_liner='A CRM.</script><script>alert("x")</script><!-- ')
    out = tmp_path / "index.html"
    build(data_dir(tmp_path, [hostile]), out)
    html = out.read_text(encoding="utf-8")
    assert "<script>alert" not in html and "<!-- " not in html
    assert html.count("</script>") == 2
    assert embedded(html)["records"][0]["one_liner"] == hostile["one_liner"]


def test_page_makes_no_external_requests_and_carries_no_key_like_strings(tmp_path):
    out = tmp_path / "index.html"
    build(data_dir(tmp_path, [record()]), out, repo_url="https://github.com/example/appscout")
    html = out.read_text(encoding="utf-8")
    shell = html[: html.index('<script type="application/json" id="dataset">')]
    assert not re.search(r'(src|href)="https?://', shell) and "@import" not in shell and "url(" not in shell
    assert not re.search(r"ck_[A-Za-z0-9_-]{16,}|[A-Za-z0-9]{60,}", html)
    assert embedded(html)["repo_url"] == "https://github.com/example/appscout"


def test_process_notes_and_audit_files_are_embedded_when_present(tmp_path):
    root = data_dir(tmp_path, [record()])
    (root / "process_notes.json").write_text(json.dumps({"notes": [{"title": "t", "what_happened": "w", "cost": "c", "what_changed": "x"}]}), encoding="utf-8")
    (root / "audit.json").write_text(json.dumps({"items": [{"app": "Acme", "field": "access", "agent_value": "a", "human_value": "a", "match": True}]}), encoding="utf-8")
    dataset = build(root, tmp_path / "index.html")
    assert dataset["process_notes"]["notes"][0]["title"] == "t"
    assert dataset["audit"]["items"][0]["match"] is True
