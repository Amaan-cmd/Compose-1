from types import SimpleNamespace

import httpx
import pytest

from appscout.fetch import PageFetcher, check_quote
from appscout.llm import LAST_TURN_NOTICE, Llm, LlmStopped
from appscout.resilience import RetryPolicy
from appscout.schema import EvidenceClaim, QuoteCheck, ToolOutcome, Usage

from conftest import GOOD_QUOTE


def usage(input_tokens=100):
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=10, input_tokens_details=SimpleNamespace(cached_tokens=40))


def tool_turn(response_id, *calls):
    output = [
        SimpleNamespace(type="function_call", call_id=f"call_{i}", name=name, arguments=arguments)
        for i, (name, arguments) in enumerate(calls)
    ]
    return SimpleNamespace(id=response_id, status="completed", output=output, usage=usage(), incomplete_details=None)


def final_turn(text, status="completed"):
    message = SimpleNamespace(type="message")
    return SimpleNamespace(id="final", status=status, output=[message], output_text=text, usage=usage(), incomplete_details="max_output_tokens")


class FakeClient:
    def __init__(self, script):
        self._script = list(script)
        self.requests = []
        self.responses = SimpleNamespace(create=self._create)

    async def _create(self, **request):
        self.requests.append(request)
        return self._script.pop(0)


def make_llm(client) -> Llm:
    return Llm(client, model="research-model", critic_model="critic-model")


async def test_tool_outputs_are_sent_back_against_the_previous_response_with_errors_marked():
    client = FakeClient([tool_turn("resp_1", ("SEARCH", '{"q": "a"}'), ("FETCH", "not json")), final_turn("the memo")])
    seen = []

    async def execute(name, arguments):
        seen.append((name, arguments))
        return ToolOutcome(True, "search result")

    spent = Usage()
    memo = await make_llm(client).run_tools(system="s", prompt="p", tools=[], execute=execute, usage=spent)
    assert memo == "the memo"
    assert seen == [("SEARCH", {"q": "a"})]
    second = client.requests[1]
    assert second["previous_response_id"] == "resp_1" and second["instructions"] == "s"
    assert second["input"] == [
        {"type": "function_call_output", "call_id": "call_0", "output": "search result"},
        {"type": "function_call_output", "call_id": "call_1", "output": "ERROR: The tool arguments were not valid JSON."},
    ]
    assert (spent.llm_calls, spent.input_tokens, spent.cached_input_tokens) == (2, 200, 80)


async def test_model_is_told_when_it_has_one_turn_left_and_stopped_if_it_ignores_that():
    client = FakeClient([tool_turn(f"resp_{i}", ("SEARCH", "{}")) for i in range(3)])

    async def execute(name, arguments):
        return ToolOutcome(True, "r")

    with pytest.raises(LlmStopped, match="3 turns"):
        await make_llm(client).run_tools(system="s", prompt="p", tools=[], execute=execute, usage=Usage(), max_turns=3)
    assert client.requests[2]["input"][-1] == {"role": "user", "content": LAST_TURN_NOTICE}


async def test_incomplete_final_response_is_raised_not_returned_as_an_answer():
    client = FakeClient([final_turn("half a memo", status="incomplete")])
    with pytest.raises(LlmStopped, match="incomplete"):
        await make_llm(client).run_tools(system="s", prompt="p", tools=[], execute=None, usage=Usage())


def page(text):
    return f"<html><body><p>{text}</p>{'<p>Other documentation text on the page.</p>' * 10}</body></html>"


def fetcher_for(handler) -> PageFetcher:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return PageFetcher(client, per_host_per_minute=600_000, policy=RetryPolicy(max_attempts=3, base_delay=0, max_delay=0))


def claim(quote=GOOD_QUOTE, url="https://docs.example.com/auth"):
    return EvidenceClaim(field="auth", url=url, quote=quote, source_type="official_docs")


async def test_quote_on_the_page_is_exact_and_a_changed_quote_is_not_found():
    fetcher = fetcher_for(lambda request: httpx.Response(200, html=page(GOOD_QUOTE)))
    assert await check_quote(claim(), fetcher) == QuoteCheck.EXACT
    assert await check_quote(claim("All API requests are authenticated with API keys only."), fetcher) == QuoteCheck.NOT_FOUND


async def test_page_is_refetched_after_a_429_and_fetched_only_once_per_run():
    hits = []

    def handler(request):
        hits.append(request.url)
        if len(hits) == 1:
            return httpx.Response(429, headers={"retry-after": "0"})
        return httpx.Response(200, html=page(GOOD_QUOTE))

    fetcher = fetcher_for(handler)
    assert await check_quote(claim(), fetcher) == QuoteCheck.EXACT
    assert await check_quote(claim(), fetcher) == QuoteCheck.EXACT
    assert len(hits) == 2


async def test_missing_pages_and_javascript_shells_are_unreachable():
    def handler(request):
        if request.url.path == "/gone":
            return httpx.Response(404)
        return httpx.Response(200, html='<html><body><div id="root"></div></body></html>')

    fetcher = fetcher_for(handler)
    assert await check_quote(claim(url="https://docs.example.com/gone"), fetcher) == QuoteCheck.UNREACHABLE
    assert await check_quote(claim(url="https://docs.example.com/spa"), fetcher) == QuoteCheck.UNREACHABLE


async def test_fragment_quotes_are_labelled_too_short_without_fetching_the_page():
    hits = []

    def handler(request):
        hits.append(request.url)
        return httpx.Response(200, html=page("143 Tools"))

    assert await check_quote(claim("143 Tools"), fetcher_for(handler)) == QuoteCheck.TOO_SHORT
    assert hits == []


async def test_model_is_stopped_from_reading_more_once_its_conversation_is_too_large():
    big = tool_turn("resp_1", ("SEARCH", "{}"))
    big.usage = usage(input_tokens=50_000)
    client = FakeClient([big, tool_turn("resp_2", ("SEARCH", "{}")), final_turn("the memo")])
    executed = []

    async def execute(name, arguments):
        executed.append(name)
        return ToolOutcome(True, "r")

    memo = await make_llm(client).run_tools(
        system="s", prompt="p", tools=[], execute=execute, usage=Usage(), context_limit=45_000
    )
    assert memo == "the memo" and executed == ["SEARCH"]
    assert client.requests[1]["input"][-1] == {"role": "user", "content": LAST_TURN_NOTICE}
    assert client.requests[2]["input"][0]["output"].startswith("ERROR: No more tool calls")


async def test_url_without_a_scheme_is_unreadable_even_after_the_client_has_collected_cookies():
    def handler(request):
        return httpx.Response(200, html=page(GOOD_QUOTE), headers={"set-cookie": "session=abc; Path=/"})

    fetcher = fetcher_for(handler)
    assert await fetcher.text("https://docs.example.com/auth") is not None
    assert await fetcher.text('"https://docs.example.com/auth"') is None
    assert await check_quote(claim(url="docs.example.com/auth"), fetcher) == QuoteCheck.UNREACHABLE
