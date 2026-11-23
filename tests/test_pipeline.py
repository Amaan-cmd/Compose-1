from appscout.fetch import Page
from appscout.pipeline import Deps, refresh_app, run_app, run_batch
from appscout.resilience import BudgetExhausted
from appscout.rules import derive_verdict, match_toolkit, toolkit_slug_candidates
from appscout.schema import (
    AccessReassessment,
    App,
    Attempt,
    CatalogLookup,
    Discovery,
    EvidenceClaim,
    Finding,
    Judgement,
    RunState,
    ToolOutcome,
)
from appscout.store import Store

from conftest import GOOD_QUOTE, make_finding

APP = App(id="acme", name="Acme", website="acme.test", category="CRM and Sales", batch=1)
PAGES = {
    "https://docs.example.com/auth": GOOD_QUOTE,
    "https://docs.example.com/start": "Create a free developer account to get API credentials.",
    "https://docs.example.com/api": "The REST API covers contacts, companies, deals and tasks.",
    "https://composio.dev/toolkits/acme": "Acme MCP server for AI agents and assistants.",
}
FILLER = " Other documentation text on the page." * 10

ALL_SUPPORTED = Judgement.model_validate(
    {
        "fields": [
            {"field": name, "supported_by_quotes": True, "note": "ok"}
            for name in ("auth", "access", "api", "mcp", "composio")
        ],
        "verdict_follows": True,
        "verdict_note": "ok",
    }
)


class FakeFetcher:
    def __init__(self, toolkit_docs=()):
        self.toolkit_docs = {f"https://docs.composio.dev/toolkits/{slug}" for slug in toolkit_docs}

    async def text(self, url):
        if url in self.toolkit_docs:
            return "Acme - Composio Toolkit | Composio." + FILLER
        return PAGES[url] + FILLER if url in PAGES else None

    async def page(self, url):
        text = await self.text(url)
        return Page(text, []) if text else None


class FakeTools:
    """Every paid call costs $0.004. The catalog returns `catalog`; rendered_text serves `rendered` pages."""

    def __init__(self, catalog=("lusha", "apollo"), rendered=None, search_works=True):
        self.catalog = catalog
        self.rendered = rendered or {}
        self.search_works = search_works
        self.searches = []

    def definitions(self):
        return []

    async def catalog_lookup(self, app_name):
        if self.catalog is None:
            return None
        return [{"slug": slug, "description": ""} for slug in self.catalog], "log_catalog"

    async def execute(self, tool_slug, arguments, budget):
        try:
            budget.spend()
        except BudgetExhausted:
            return ToolOutcome(False, "Paid tool budget exhausted.")
        if tool_slug == "TAVILY_SEARCH":
            self.searches.append(arguments["query"])
            if not self.search_works:
                return ToolOutcome(False, "Tool unavailable.")
        return ToolOutcome(True, "search results", 0.004, "log_paid")

    async def rendered_text(self, url, quote, budget):
        try:
            budget.spend()
        except BudgetExhausted:
            return None, 0.0, ""
        return self.rendered.get(url), 0.004, "log_extract"


class FakeLlm:
    """Returns scripted findings in order; every research call makes one paid search of its own."""

    model = "research-model"
    critic_model = "critic-model"

    def __init__(self, findings, fail_for=()):
        self.findings = list(findings)
        self.fail_for = fail_for
        self.research_calls = 0
        self.prompts = []

    async def run_tools(self, *, system, prompt, tools, execute, usage):
        if any(name in prompt for name in self.fail_for):
            raise RuntimeError("model unavailable")
        self.research_calls += 1
        self.prompts.append(prompt)
        await execute("TAVILY_SEARCH", {"query": "acme api docs"})
        usage.llm_calls += 1
        usage.input_tokens += 1000
        return "memo"

    async def extract(self, *, system, prompt, schema, usage, critic=False):
        assert critic == (schema is Judgement)
        usage.llm_calls += 1
        if schema is AccessReassessment:
            return self.reassessment
        return self.findings.pop(0) if schema is Finding else ALL_SUPPORTED


def deps_for(tmp_path, llm, tools=None, fetcher=None) -> Deps:
    rows = "id,name,website,category,batch\nacme,Acme,acme.test,CRM and Sales,1\nglobex,Globex,globex.test,CRM and Sales,1\n"
    (tmp_path / "apps.csv").write_text(rows, encoding="utf-8")
    return Deps(llm=llm, tools=tools or FakeTools(), fetcher=fetcher or FakeFetcher(), store=Store(tmp_path), now=lambda: "2026-11-23T00:00:00+00:00")


def finding_with_bad_auth_quote() -> Finding:
    finding = make_finding()
    finding.evidence[0].quote = "All API requests are authenticated with a made-up sentence."
    return finding


def finding_citing_a_javascript_page() -> Finding:
    finding = make_finding()
    finding.evidence[0].url = "https://spa.example.com/auth"
    return finding


def finding_with_composio_page() -> Finding:
    finding = make_finding(composio={"in_catalog": "yes", "url": "https://composio.dev/toolkits/acme"})
    url = "https://composio.dev/toolkits/acme"
    finding.evidence.append(EvidenceClaim(field="composio", url=url, quote=PAGES[url], source_type="official_site"))
    return finding


async def test_verified_record_is_written_after_one_attempt(tmp_path):
    deps = deps_for(tmp_path, FakeLlm([make_finding()]))
    record = await run_app(APP, deps)
    assert record.attempts == 1 and not record.needs_human_review
    assert [item.check for item in record.evidence] == ["exact", "exact", "exact"]
    assert (record.model, record.critic_model) == ("research-model", "critic-model")
    assert deps.store.load_record("acme") == record


async def test_every_app_gets_a_catalog_lookup_and_one_mcp_search_through_composio_and_both_are_logged(tmp_path):
    tools = FakeTools()
    llm = FakeLlm([make_finding()])
    record = await run_app(APP, deps_for(tmp_path, llm, tools))
    assert tools.searches[0] == "Acme MCP server (Model Context Protocol)"
    assert [(call.tool, call.charged_usd, call.log_id) for call in record.composio_log] == [
        ("COMPOSIO_SEARCH_TOOLS", 0.0, "log_catalog"),
        ("TAVILY_SEARCH", 0.004, "log_paid"),
        ("TAVILY_SEARCH", 0.004, "log_paid"),
    ]
    assert record.usage.composio_calls == 2 and record.usage.composio_usd == 0.008
    assert "MCP WEB SEARCH (already run)" in llm.prompts[0] and "search results" in llm.prompts[0]
    assert "No toolkit matching this app was returned. Nearest results: lusha, apollo." in llm.prompts[0]


async def test_app_is_in_the_catalog_when_composios_own_search_returns_its_toolkit(tmp_path):
    record = await run_app(APP, deps_for(tmp_path, FakeLlm([make_finding()]), FakeTools(catalog=("lusha", "acme"))))
    assert (record.in_composio_catalog, record.composio_toolkit_slug, record.composio_catalog_source) == (True, "acme", "mcp_lookup")


async def test_app_is_in_the_catalog_when_only_the_verified_toolkit_page_shows_it(tmp_path):
    record = await run_app(APP, deps_for(tmp_path, FakeLlm([finding_with_composio_page()])))
    assert (record.in_composio_catalog, record.composio_toolkit_slug, record.composio_catalog_source) == (True, "", "toolkit_page")


async def test_app_is_net_new_when_neither_signal_finds_it(tmp_path):
    record = await run_app(APP, deps_for(tmp_path, FakeLlm([make_finding()])))
    assert (record.in_composio_catalog, record.composio_catalog_source) == (False, "none")
    assert not record.needs_human_review


async def test_failed_lookups_are_review_reasons_not_silent_negatives(tmp_path):
    tools = FakeTools(catalog=None, search_works=False)
    record = await run_app(APP, deps_for(tmp_path, FakeLlm([make_finding()]), tools))
    assert not record.in_composio_catalog
    assert "Composio catalog lookup did not run" in record.review_reasons
    assert "the mandatory Composio web search did not run" in record.review_reasons


async def test_quote_that_is_not_on_the_page_triggers_one_repair_attempt_without_repeating_the_lookups(tmp_path):
    tools = FakeTools()
    llm = FakeLlm([finding_with_bad_auth_quote(), make_finding()])
    record = await run_app(APP, deps_for(tmp_path, llm, tools))
    assert llm.research_calls == 2 and record.attempts == 2
    assert not record.needs_human_review
    assert tools.searches.count("Acme MCP server (Model Context Protocol)") == 1
    # The mandatory search plus one by the model is the per-app search limit, so the repair attempt gets none.
    assert tools.searches == ["Acme MCP server (Model Context Protocol)", "acme api docs"]
    assert record.usage.composio_calls == 2


async def test_record_that_still_fails_after_repair_is_flagged_for_a_human(tmp_path):
    llm = FakeLlm([finding_with_bad_auth_quote(), finding_with_bad_auth_quote()])
    record = await run_app(APP, deps_for(tmp_path, llm))
    assert llm.research_calls == 2 and record.needs_human_review
    assert any(reason.startswith("auth: unsupported") for reason in record.review_reasons)


async def test_interrupted_run_resumes_at_verification_without_researching_again(tmp_path):
    llm = FakeLlm([])
    tools = FakeTools()
    deps = deps_for(tmp_path, llm, tools)
    saved = RunState(
        catalog=CatalogLookup(matched_slug="acme", candidates=["acme"]),
        discovery=Discovery(query="q", results="r"),
        attempts=[Attempt(finding=make_finding(), memo="memo", evidence_gaps=[])],
    )
    deps.store.save_state("acme", saved)
    record = await run_app(APP, deps)
    assert llm.research_calls == 0 and tools.searches == []
    assert record.attempts == 1 and record.in_composio_catalog and not record.needs_human_review


async def test_quote_on_a_page_only_composio_can_render_is_confirmed_through_the_extractor(tmp_path):
    tools = FakeTools(rendered={"https://spa.example.com/auth": f"Docs. {GOOD_QUOTE} More."})
    record = await run_app(APP, deps_for(tmp_path, FakeLlm([finding_citing_a_javascript_page()]), tools))
    assert [item.check for item in record.evidence] == ["exact_rendered", "exact", "exact"]
    assert record.attempts == 1 and not record.needs_human_review
    assert record.composio_log[-1].tool == "TAVILY_EXTRACT"
    assert record.usage.composio_calls == 3 and round(record.usage.composio_usd, 3) == 0.012


async def test_page_nobody_can_read_goes_to_human_review_as_unreachable(tmp_path):
    llm = FakeLlm([finding_citing_a_javascript_page(), finding_citing_a_javascript_page()])
    record = await run_app(APP, deps_for(tmp_path, llm))
    assert record.evidence[0].check == "unreachable" and record.needs_human_review
    assert any(reason.startswith("auth: unreachable") for reason in record.review_reasons)


async def test_one_failing_app_does_not_stop_the_batch_and_its_error_is_saved(tmp_path):
    other = App(id="globex", name="Globex", website="globex.test", category="CRM and Sales", batch=1)
    deps = deps_for(tmp_path, FakeLlm([make_finding()], fail_for=("Globex",)))
    acme, globex = await run_batch([APP, other], deps, concurrency=2)
    assert acme.id == "acme"
    assert isinstance(globex, RuntimeError)
    assert deps.store.load_state("globex").last_error == "RuntimeError: model unavailable"
    assert deps.store.load_record("globex") is None


def test_toolkit_matching_accepts_real_name_variants_and_rejects_lookalikes():
    assert match_toolkit("Attio", ["lusha", "attio"]) == "attio"
    assert match_toolkit("Zoho CRM", ["zoho", "apollo"]) == "zoho"
    assert match_toolkit("Close", ["closeio"]) == "closeio"
    assert match_toolkit("DealCloud", ["apollo", "mistral_ai", "lusha"]) == ""
    assert match_toolkit("Box", ["boxhero"]) == ""
    assert match_toolkit("Box", ["boxhero", "box"]) == "box"
    assert match_toolkit("Monday.com", ["monday"]) == "monday"
    assert match_toolkit("systeme.io", ["systeme_io"]) == "systeme_io"
    assert match_toolkit("Lark (Larksuite)", ["lark"]) == "lark"
    assert match_toolkit("Google Ads", ["googleads"]) == "googleads"
    assert match_toolkit("WhatsApp Business", ["whatsapp"]) == "whatsapp"
    assert match_toolkit("Zoho Cliq", ["zoho"]) == ""
    assert match_toolkit("Salesforce Commerce Cloud", ["salesforce"]) == ""
    assert match_toolkit("Amazon Selling Partner", ["amazon"]) == ""


async def test_paid_calls_are_capped_per_app_across_research_and_quote_checks(tmp_path):
    finding = make_finding()
    for item in finding.evidence:
        item.url = item.url.replace("docs.example.com", "spa.example.com")
    tools = FakeTools()
    deps = deps_for(tmp_path, FakeLlm([finding, finding.model_copy(deep=True)]), tools)
    record = await run_app(APP, deps)
    assert record.usage.composio_calls == 4 == deps.paid_calls_per_app
    assert round(record.usage.composio_usd, 3) == 0.016
    assert [call.tool for call in record.composio_log if call.charged_usd] == [
        "TAVILY_SEARCH",
        "TAVILY_SEARCH",
        "TAVILY_EXTRACT",
        "TAVILY_EXTRACT",
    ]


async def test_cap_still_applies_when_an_interrupted_app_is_resumed(tmp_path):
    deps = deps_for(tmp_path, FakeLlm([make_finding()]))
    saved = RunState(catalog=CatalogLookup(matched_slug="acme", candidates=["acme"]))
    saved.usage.composio_calls = 4
    deps.store.save_state("acme", saved)
    record = await run_app(APP, deps)
    assert record.usage.composio_calls == 4
    assert "the mandatory Composio web search did not run" in record.review_reasons


async def test_apps_are_shared_out_across_a_pool_of_researchers_and_each_record_names_its_own(tmp_path):
    apps = [App(id=f"app{n}", name=f"App{n}", website="x.test", category="CRM and Sales", batch=1) for n in range(6)]
    rows = "id,name,website,category,batch\n" + "".join(f"{a.id},{a.name},{a.website},{a.category},1\n" for a in apps)
    fast, slow = FakeLlm([make_finding() for _ in apps]), FakeLlm([make_finding() for _ in apps])
    fast.model, slow.model = "fast-model", "slow-model"
    deps = deps_for(tmp_path, fast)
    (tmp_path / "apps.csv").write_text(rows, encoding="utf-8")
    records = await run_batch(apps, deps, pool=[(fast, 2), (slow, 1)])
    assert [record.id for record in records] == [app.id for app in apps]
    assert {record.model for record in records} == {"fast-model", "slow-model"}
    assert fast.research_calls + slow.research_calls == 6


async def test_composio_docs_page_puts_an_app_in_the_catalog_even_when_the_catalog_search_misses_it(tmp_path):
    deps = deps_for(tmp_path, FakeLlm([make_finding()]), fetcher=FakeFetcher(toolkit_docs=["acme"]))
    record = await run_app(APP, deps)
    assert (record.in_composio_catalog, record.composio_toolkit_slug, record.composio_catalog_source) == (True, "acme", "docs_page")
    assert record.composio_toolkit_url == "https://docs.composio.dev/toolkits/acme"


def test_toolkit_slug_candidates_cover_the_spellings_composio_uses():
    assert toolkit_slug_candidates("Help Scout") == ["help_scout", "helpscout"]
    assert toolkit_slug_candidates("Monday.com") == ["monday_com", "mondaycom", "monday"]
    assert toolkit_slug_candidates("Zoho CRM") == ["zoho_crm", "zohocrm", "zoho"]
    assert toolkit_slug_candidates("Zoho Cliq") == ["zoho_cliq", "zohocliq"]
    assert toolkit_slug_candidates("Lark (Larksuite)") == ["lark"]


async def test_refresh_updates_the_catalog_flag_and_rejudges_without_researching_again(tmp_path):
    llm = FakeLlm([finding_with_bad_auth_quote(), finding_with_bad_auth_quote()])
    deps = deps_for(tmp_path, llm)
    before = await run_app(APP, deps)
    assert before.needs_human_review and not before.in_composio_catalog and before.model == "research-model"

    other = FakeLlm([])
    other.model, other.critic_model = "someone-else", "second-critic"
    refreshed = await refresh_app(APP, deps_for(tmp_path, other, fetcher=FakeFetcher(toolkit_docs=["acme"])), rejudge=True)
    assert other.research_calls == 0
    assert refreshed.in_composio_catalog and refreshed.composio_catalog_source == "docs_page"
    assert (refreshed.model, refreshed.critic_model) == ("research-model", "second-critic")
    assert refreshed.usage.composio_calls == before.usage.composio_calls


async def test_refresh_leaves_an_app_that_is_part_way_through_for_the_run_to_finish(tmp_path):
    deps = deps_for(tmp_path, FakeLlm([]))
    assert await refresh_app(APP, deps, rejudge=False) is None
    part_way = Attempt(finding=make_finding(), memo="memo", evidence_gaps=[], checks=["exact"] * 3, verification=[])
    deps.store.save_state("acme", RunState(attempts=[part_way]))
    assert await refresh_app(APP, deps, rejudge=False) is None
    assert deps.store.load_record("acme") is None


def finding_with_access_left_unknown() -> Finding:
    return make_finding(
        access={"level": "unknown", "notes": "No sentence ties the free plan to API keys."},
        verdict={"status": "unknown", "main_blocker": "other", "rationale": "Access is unknown."},
    )


async def test_unknown_access_is_reread_from_the_verified_quotes_and_the_verdict_follows_by_rule(tmp_path):
    deps = deps_for(tmp_path, FakeLlm([finding_with_access_left_unknown()]))
    before = await run_app(APP, deps)
    assert before.access.level == "unknown" and before.verdict.status == "unknown" and before.needs_human_review

    reader = FakeLlm([])
    reader.reassessment = AccessReassessment(level="self_serve_free", basis="inferred", notes="Free account plus self-serve keys.")
    after = await refresh_app(APP, deps_for(tmp_path, reader), rejudge=False, reassess=True)
    assert reader.research_calls == 0
    assert (after.access.level, after.access_basis) == ("self_serve_free", "inferred")
    assert (after.verdict.status, after.verdict.main_blocker) == ("buildable_now", "none")
    assert not after.needs_human_review


async def test_access_stays_unknown_when_the_second_reading_cannot_settle_it(tmp_path):
    deps = deps_for(tmp_path, FakeLlm([finding_with_access_left_unknown()]))
    await run_app(APP, deps)
    reader = FakeLlm([])
    reader.reassessment = AccessReassessment(level="unknown", basis="none", notes="The quotes do not say.")
    after = await refresh_app(APP, deps_for(tmp_path, reader), rejudge=False, reassess=True)
    assert after.access.level == "unknown" and after.verdict.status == "unknown" and after.access_basis == ""


def test_verdict_rule_covers_every_access_level():
    def verdict(access, breadth="broad"):
        finding = make_finding(access={"level": access, "notes": ""})
        finding.api.breadth = breadth
        result = derive_verdict(finding)
        return (str(result.status), str(result.main_blocker)) if result else None

    assert verdict("self_serve_free") == ("buildable_now", "none")
    assert verdict("self_serve_free", "narrow") == ("buildable_with_caveats", "narrow_api")
    assert verdict("self_serve_trial") == ("buildable_with_caveats", "trial_only")
    assert verdict("paid_plan") == ("buildable_with_caveats", "paid_plan")
    assert verdict("admin_approval") == ("buildable_with_caveats", "admin_approval")
    assert verdict("partner_or_sales") == ("blocked", "partner_gate")
    assert verdict("unknown") is None
    assert verdict("unknown", "none") == ("blocked", "no_public_api")
