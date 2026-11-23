import httpx2
import pytest

from appscout.composio_tools import MAX_RESULT_CHARS, ComposioTools, SpendBudget
from appscout.fetch import Page
from appscout.resilience import CallBudget, RateLimiter, RetryPolicy
from appscout.toolbox import Toolbox


def envelope(*, data=None, error=None, charge="0.004000", preview=None):
    """A COMPOSIO_MULTI_EXECUTE_TOOL response for one tool, in the shape the live endpoint returns."""
    response = {"successful": error is None}
    if error is not None:
        response["error"] = error
    elif preview is not None:
        response["data_preview"] = preview
    else:
        response["data"] = data
    return {
        "successful": True,
        "data": {"results": [{"response": response, "tool_slug": "TAVILY_SEARCH", "index": 0}]},
        "error": None,
        "log_id": "log_1",
        "instant_charge": {"amount": charge, "currency": "USD"},
    }


def rate_limited(retry_after: str) -> httpx2.HTTPStatusError:
    request = httpx2.Request("POST", "https://connect.composio.test/mcp")
    response = httpx2.Response(429, headers={"retry-after": retry_after}, request=request)
    return httpx2.HTTPStatusError("429 Too Many Requests", request=request, response=response)


class FakeCall:
    """Plays back a script of envelopes and exceptions, one per MCP call."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    async def __call__(self, name, arguments):
        self.requests.append((name, arguments))
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step


def make_tools(call, clock, *, spend_limit=None, attempts=5):
    return ComposioTools(
        call,
        spend=SpendBudget(spend_limit),
        limiter=RateLimiter(6000, clock=clock, sleep=clock.sleep),
        policy=RetryPolicy(max_attempts=attempts, base_delay=0.0, max_delay=0.0),
    )


async def test_search_runs_through_multi_execute_with_cost_guards_and_reports_the_charge(clock):
    call = FakeCall([envelope(data={"results": [{"url": "https://docs.example.com"}]})])
    arguments = {"query": "acme api docs", "search_depth": "advanced", "max_results": 50, "include_raw_content": True}
    outcome = await make_tools(call, clock).execute("TAVILY_SEARCH", arguments, CallBudget(5))
    assert outcome.ok and "docs.example.com" in outcome.content and outcome.cost_usd == 0.004
    name, request = call.requests[0]
    assert name == "COMPOSIO_MULTI_EXECUTE_TOOL"
    sent = request["tools"][0]["arguments"]
    assert (sent["search_depth"], sent["max_results"], sent["include_raw_content"]) == ("basic", 8, False)


async def test_extract_is_capped_at_the_five_urls_one_price_unit_covers(clock):
    call = FakeCall([envelope(data={"results": []})])
    urls = [f"https://docs.example.com/{n}" for n in range(9)]
    await make_tools(call, clock).execute("TAVILY_EXTRACT", {"urls": urls}, CallBudget(5))
    assert call.requests[0][1]["tools"][0]["arguments"]["urls"] == urls[:5]


async def test_model_cannot_run_composio_tools_outside_the_research_allowlist(clock):
    call = FakeCall([])
    outcome = await make_tools(call, clock).execute("GMAIL_SEND_EMAIL", {}, CallBudget(5))
    assert not outcome.ok and call.requests == []


async def test_http_429_waits_out_retry_after_then_succeeds(clock):
    call = FakeCall([ExceptionGroup("task group", [rate_limited("9")]), envelope(data="ok")])
    outcome = await make_tools(call, clock).execute("TAVILY_SEARCH", {"query": "q"}, CallBudget(5))
    assert outcome.ok
    assert clock.sleeps == [9.0]


async def test_short_provider_limit_inside_a_failed_result_is_retried(clock):
    call = FakeCall([envelope(error="429 Too Many Requests", charge="0"), envelope(data="ok")])
    outcome = await make_tools(call, clock).execute("TAVILY_SEARCH", {"query": "q"}, CallBudget(5))
    assert outcome.ok and len(call.requests) == 2


async def test_exhausted_daily_quota_is_not_retried(clock):
    call = FakeCall([envelope(error="Rate limit: daily quota exceeded", charge="0")])
    outcome = await make_tools(call, clock).execute("TAVILY_SEARCH", {"query": "q"}, CallBudget(5))
    assert not outcome.ok and len(call.requests) == 1


async def test_giving_up_reports_failure_to_the_model_instead_of_raising(clock):
    call = FakeCall([TimeoutError()] * 3)
    outcome = await make_tools(call, clock, attempts=3).execute("TAVILY_SEARCH", {"query": "q"}, CallBudget(5))
    assert not outcome.ok and "gave up after 3 attempts" in outcome.content


async def test_app_call_cap_stops_calls_before_they_reach_composio(clock):
    call = FakeCall([envelope(data="ok")])
    tools = make_tools(call, clock)
    budget = CallBudget(1)
    assert (await tools.execute("TAVILY_SEARCH", {"query": "q"}, budget)).ok
    outcome = await tools.execute("TAVILY_SEARCH", {"query": "q"}, budget)
    assert not outcome.ok and "budget" in outcome.content.lower()
    assert len(call.requests) == 1


async def test_dollar_cap_is_enforced_from_the_charges_composio_reports(clock):
    call = FakeCall([envelope(data="ok"), envelope(data="ok")])
    tools = make_tools(call, clock, spend_limit=0.008)
    for _ in range(2):
        assert (await tools.execute("TAVILY_SEARCH", {"query": "q"}, CallBudget(9))).ok
    outcome = await tools.execute("TAVILY_SEARCH", {"query": "q"}, CallBudget(9))
    assert not outcome.ok and "$0.01" in outcome.content
    assert len(call.requests) == 2


async def test_result_moved_to_a_remote_file_comes_back_as_a_labelled_preview(clock):
    call = FakeCall([envelope(preview={"results": [{"raw_content": "first lines of the page"}]})])
    outcome = await make_tools(call, clock).execute("TAVILY_EXTRACT", {"urls": ["https://x.test"]}, CallBudget(5))
    assert outcome.ok and "only a preview" in outcome.content and "first lines of the page" in outcome.content


async def test_oversized_results_are_truncated_with_a_visible_marker(clock):
    call = FakeCall([envelope(data="x" * (MAX_RESULT_CHARS + 500))])
    outcome = await make_tools(call, clock).execute("TAVILY_SEARCH", {"query": "q"}, CallBudget(5))
    assert outcome.ok and "[result truncated:" in outcome.content


async def test_page_text_for_the_checker_asks_for_one_url_focused_on_the_quote(clock):
    call = FakeCall([envelope(data={"results": [{"url": "https://x.test", "raw_content": "The quoted sentence."}]})])
    text, charged, log_id = await make_tools(call, clock).page_text("https://x.test", "The quoted sentence.", CallBudget(1))
    assert "The quoted sentence." in text and charged == 0.004 and log_id == "log_1"
    sent = call.requests[0][1]["tools"][0]["arguments"]
    assert sent["urls"] == ["https://x.test"] and sent["query"] == "The quoted sentence."


async def test_catalog_lookup_asks_composios_own_search_and_returns_the_toolkits_it_names(clock):
    statuses = [{"toolkit": "attio", "description": "A CRM."}, {"toolkit": "lusha", "description": "Enrichment."}]
    call = FakeCall([{"successful": True, "data": {"toolkit_connection_statuses": statuses}, "log_id": "log_9"}])
    toolkits, log_id = await make_tools(call, clock).catalog_lookup("Attio")
    assert [toolkit["slug"] for toolkit in toolkits] == ["attio", "lusha"] and log_id == "log_9"
    name, request = call.requests[0]
    assert name == "COMPOSIO_SEARCH_TOOLS" and "Attio" in request["queries"][0]["use_case"]


async def test_catalog_lookup_that_keeps_failing_returns_none_instead_of_an_empty_catalog(clock):
    call = FakeCall([TimeoutError()] * 2)
    assert await make_tools(call, clock, attempts=2).catalog_lookup("Attio") is None


async def test_definitions_come_from_composio_in_openai_function_format(clock):
    schemas = {
        slug: {"description": f"{slug} description", "input_schema": {"type": "object", "properties": {}}}
        for slug in ("TAVILY_SEARCH", "TAVILY_EXTRACT")
    }
    call = FakeCall([{"successful": True, "data": {"tool_schemas": schemas}}])
    tools = make_tools(call, clock)
    await tools.load_definitions()
    assert [d["name"] for d in tools.definitions()] == ["TAVILY_SEARCH", "TAVILY_EXTRACT"]
    assert tools.definitions()[0] == {
        "type": "function",
        "name": "TAVILY_SEARCH",
        "description": "TAVILY_SEARCH description",
        "parameters": {"type": "object", "properties": {}},
        "strict": False,
    }


async def test_missing_schema_fails_loudly_at_startup(clock):
    call = FakeCall([{"successful": False, "error": "unauthorized", "data": None}])
    with pytest.raises(RuntimeError, match="unauthorized"):
        await make_tools(call, clock).load_definitions()


class FakeFetcher:
    def __init__(self, pages, links=()):
        self.pages = pages
        self.links = list(links)

    async def page(self, url):
        return Page(self.pages[url], self.links) if url in self.pages else None


async def test_fetch_page_is_free_and_does_not_touch_composio_or_the_paid_budget(clock):
    call = FakeCall([])
    toolbox = Toolbox(make_tools(call, clock), FakeFetcher({"https://docs.example.com": "Useful   documentation text. " * 20}))
    budget = CallBudget(1)
    outcome = await toolbox.execute("fetch_page", {"url": "https://docs.example.com"}, budget)
    assert outcome.ok and outcome.cost_usd == 0 and "Useful documentation text." in outcome.content
    assert budget.used == 0 and call.requests == []


async def test_fetch_page_points_the_model_at_the_paid_extractor_when_a_page_cannot_be_read(clock):
    toolbox = Toolbox(make_tools(FakeCall([]), clock), FakeFetcher({"https://spa.example.com": "Loading"}))
    for url in ("https://spa.example.com", "https://gone.example.com"):
        outcome = await toolbox.execute("fetch_page", {"url": url}, CallBudget(1))
        assert not outcome.ok and "TAVILY_EXTRACT" in outcome.content


DOCS = "https://docs.example.com"
READABLE = {DOCS: "Useful documentation text. " * 20}


async def test_fetch_page_lists_links_with_same_site_ones_first_so_the_model_can_navigate_for_free(clock):
    links = [("Partner", "https://other.example.org/x"), ("Pricing", "https://docs.example.com/pricing")]
    toolbox = Toolbox(make_tools(FakeCall([]), clock), FakeFetcher(READABLE, links))
    outcome = await toolbox.execute("fetch_page", {"url": DOCS}, CallBudget(1))
    listing = outcome.content.split("LINKS ON THIS PAGE\n")[1].splitlines()
    assert listing == ["- Pricing: https://docs.example.com/pricing", "- Partner: https://other.example.org/x"]


async def test_extract_on_a_page_the_free_fetch_can_read_costs_nothing(clock):
    call = FakeCall([])
    budget = CallBudget(1)
    outcome = await Toolbox(make_tools(call, clock), FakeFetcher(READABLE)).execute("TAVILY_EXTRACT", {"urls": [DOCS]}, budget)
    assert outcome.ok and outcome.cost_usd == 0 and "read directly, no charge" in outcome.content
    assert budget.used == 0 and call.requests == []


async def test_extract_pays_only_for_the_pages_the_free_fetch_cannot_read(clock):
    call = FakeCall([envelope(data={"results": [{"raw_content": "rendered text"}]})])
    spa = "https://spa.example.com/app"
    outcome = await Toolbox(make_tools(call, clock), FakeFetcher(READABLE)).execute(
        "TAVILY_EXTRACT", {"urls": [DOCS, spa], "query": "auth"}, CallBudget(1)
    )
    assert outcome.ok and outcome.cost_usd == 0.004
    assert "read directly, no charge" in outcome.content and "rendered text" in outcome.content
    assert call.requests[0][1]["tools"][0]["arguments"]["urls"] == [spa]


LONG_PAGE = "Intro sentence about the product. " + "Filler words about nothing in particular. " * 600 + (
    "API access is included in the Free plan for every workspace. " + "More filler to pad the page out. " * 300
)


async def test_long_page_is_cut_off_with_a_pointer_to_find(clock):
    toolbox = Toolbox(make_tools(FakeCall([]), clock), FakeFetcher({DOCS: LONG_PAGE}))
    outcome = await toolbox.execute("fetch_page", {"url": DOCS}, CallBudget(1))
    assert len(outcome.content) < 12_400 and "Call fetch_page again with `find` keywords" in outcome.content
    assert "API access is included" not in outcome.content


async def test_find_returns_the_exact_passage_from_deep_in_a_long_page(clock):
    toolbox = Toolbox(make_tools(FakeCall([]), clock), FakeFetcher({DOCS: LONG_PAGE}))
    outcome = await toolbox.execute("fetch_page", {"url": DOCS, "find": ["Free plan"]}, CallBudget(1))
    assert "API access is included in the Free plan for every workspace." in outcome.content
    assert outcome.content.startswith("[This page is") and len(outcome.content) < 4_500


async def test_urls_wrapped_in_quotes_or_brackets_by_the_model_are_still_fetched(clock):
    toolbox = Toolbox(make_tools(FakeCall([]), clock), FakeFetcher(READABLE))
    for raw in (f'"{DOCS}"', f'["{DOCS}"]', [DOCS]):
        outcome = await toolbox.execute("fetch_page", {"url": raw}, CallBudget(1))
        assert outcome.ok and "Useful documentation text." in outcome.content
    outcome = await toolbox.execute("TAVILY_EXTRACT", {"urls": f'["{DOCS}"]'}, CallBudget(1))
    assert outcome.ok and "read directly, no charge" in outcome.content


async def test_fetch_page_without_a_usable_url_tells_the_model_what_it_needs(clock):
    toolbox = Toolbox(make_tools(FakeCall([]), clock), FakeFetcher(READABLE))
    outcome = await toolbox.execute("fetch_page", {"url": "docs.example.com"}, CallBudget(1))
    assert not outcome.ok and "https://" in outcome.content
