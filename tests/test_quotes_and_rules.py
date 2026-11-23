from appscout.quotes import contains_quote, html_links, html_to_text, looks_rendered
from appscout.rules import combine, enforce_evidence, failed_fields, review_reasons
from appscout.schema import FieldResult, Judgement, QuoteCheck

from conftest import GOOD_QUOTE, make_finding

PAGE = f"""<html><head><style>p {{ color: red }}</style><script>var x = "OAuth";</script></head>
<body><h1>Authentication</h1><p>All API requests are authenticated with
<a href="/oauth">OAuth&nbsp;2.0</a> access tokens.</p>{'<p>More documentation text.</p>' * 20}</body></html>"""


def judgement(*, auth=True, access=True, api=True, verdict=True) -> Judgement:
    return Judgement.model_validate(
        {
            "fields": [
                {"field": "auth", "supported_by_quotes": auth, "note": "auth note"},
                {"field": "access", "supported_by_quotes": access, "note": "access note"},
                {"field": "api", "supported_by_quotes": api, "note": "api note"},
            ],
            "verdict_follows": verdict,
            "verdict_note": "verdict note",
        }
    )


def test_quote_matches_across_markup_whitespace_and_case():
    text = html_to_text(PAGE)
    assert contains_quote(GOOD_QUOTE.upper(), text)
    assert not contains_quote("All API requests are authenticated with API keys.", text)


def test_script_and_style_content_is_not_page_text():
    assert "var x" not in html_to_text(PAGE)
    assert "color: red" not in html_to_text(PAGE)


def test_short_quotes_never_match():
    assert not contains_quote("OAuth 2.0", html_to_text(PAGE))


def test_javascript_shell_does_not_count_as_a_page():
    assert not looks_rendered(html_to_text('<html><body><div id="root"></div><script src="app.js"></script></body></html>'))
    assert looks_rendered(html_to_text(PAGE))


def test_claim_without_a_quote_is_reset_to_unknown_and_takes_the_verdict_with_it():
    finding = make_finding()
    finding.evidence = [item for item in finding.evidence if item.field != "access"]
    assert enforce_evidence(finding) == ["access"]
    assert finding.access.level == "unknown"
    assert finding.verdict.status == "unknown"
    assert finding.auth.primary == "oauth2"


def test_fully_evidenced_finding_is_left_alone():
    finding = make_finding()
    assert enforce_evidence(finding) == []
    assert finding.verdict.status == "buildable_now"


def test_all_quotes_found_and_judged_supported():
    finding = make_finding()
    verification = combine(finding, [QuoteCheck.EXACT] * 3, judgement())
    assert failed_fields(verification) == []
    assert review_reasons(finding, verification) == []


def test_quote_missing_from_page_fails_the_field_and_the_verdict_that_rests_on_it():
    finding = make_finding()
    checks = [QuoteCheck.EXACT, QuoteCheck.NOT_FOUND, QuoteCheck.EXACT]
    assert failed_fields(combine(finding, checks, judgement())) == ["access", "verdict"]


def test_found_quote_that_does_not_prove_the_claim_fails():
    verification = combine(make_finding(), [QuoteCheck.EXACT] * 3, judgement(auth=False))
    by_field = {v.field: v for v in verification}
    assert by_field["auth"].result == FieldResult.UNSUPPORTED
    assert by_field["auth"].note == "auth note"


def test_unreadable_pages_are_reported_as_unreachable_not_wrong():
    checks = [QuoteCheck.UNREACHABLE, QuoteCheck.EXACT, QuoteCheck.EXACT]
    by_field = {v.field: v.result for v in combine(make_finding(), checks, judgement())}
    assert by_field["auth"] == FieldResult.UNREACHABLE


def test_gated_access_with_evidence_is_not_a_review_reason():
    finding = make_finding(
        access={"level": "partner_or_sales", "notes": ""},
        verdict={"status": "blocked", "main_blocker": "partner_gate", "rationale": "Needs a contract."},
    )
    verification = combine(finding, [QuoteCheck.EXACT] * 3, judgement())
    assert review_reasons(finding, verification) == []


def test_unknown_required_field_is_a_review_reason():
    finding = make_finding()
    finding.evidence = [item for item in finding.evidence if item.field != "auth"]
    enforce_evidence(finding)
    verification = combine(finding, [QuoteCheck.EXACT] * 2, judgement())
    assert "auth is unknown" in review_reasons(finding, verification)


def test_field_backed_only_by_fragments_fails_as_too_short_not_as_missing():
    finding = make_finding()
    checks = [QuoteCheck.TOO_SHORT, QuoteCheck.EXACT, QuoteCheck.EXACT]
    by_field = {v.field: v for v in combine(finding, checks, judgement())}
    assert by_field["auth"].result == FieldResult.UNSUPPORTED
    assert by_field["auth"].note == "Every quote for this field is too short to verify."


def test_links_are_made_absolute_deduplicated_and_stripped_of_fragments():
    markup = """<a href="/pricing">Pricing <b>plans</b></a> <a href="/pricing#faq">FAQ</a>
    <a href="https://help.example.com/api">API help</a> <a href="mailto:x@example.com">Mail</a> <a href="#top">Top</a>"""
    assert html_links(markup, "https://example.com/docs") == [
        ("Pricing plans", "https://example.com/pricing"),
        ("API help", "https://help.example.com/api"),
    ]
