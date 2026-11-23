"""Composio as the pipeline's tool layer, reached through the Composio Connect MCP endpoint.

Every paid call goes through one shared rate limiter, a retry policy, a per-app call cap and a
run-wide dollar cap. Spend is taken from the `instant_charge` Composio reports on each response.
"""

import json
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx2
from mcp import ClientSession, MCPError
from mcp.client.streamable_http import streamable_http_client

from .resilience import (
    BudgetExhausted,
    CallBudget,
    RateLimiter,
    RetriesExhausted,
    Retry,
    RetryPolicy,
    parse_retry_after,
    with_retry,
)
from .schema import ToolOutcome

DEFAULT_MCP_URL = "https://connect.composio.dev/mcp"
SEARCH_TOOL = "TAVILY_SEARCH"
EXTRACT_TOOL = "TAVILY_EXTRACT"
RESEARCH_TOOLS = (SEARCH_TOOL, EXTRACT_TOOL)

# Composio's Hobby plan allows 2,000 requests a minute per organisation; stay well under it.
DEFAULT_CALLS_PER_MINUTE = 120
MAX_RESULT_CHARS = 16_000
MAX_SEARCH_RESULTS = 8
MAX_URLS_PER_EXTRACT = 5  # Composio prices TAVILY_EXTRACT per 5 URLs, so one call never costs more than one unit.

# Arguments the pipeline sets itself so the model cannot pick a dearer or noisier variant.
FORCED_ARGUMENTS = {
    SEARCH_TOOL: {"search_depth": "basic", "include_raw_content": False, "include_images": False},
    EXTRACT_TOOL: {"extract_depth": "basic", "include_images": False, "format": "text"},
}

# Provider-side limits arrive inside a failed result rather than as a transport error (Composio docs, "Avoid rate limits").
PROVIDER_LIMIT_MARKERS = ("429", "rate limit", "ratelimitexceeded", "resource_exhausted", "throttle", "too many requests")
QUOTA_EXHAUSTED_MARKERS = ("daily", "per day", "dailylimitexceeded", "monthly")

Call = Callable[[str, dict], Awaitable[dict]]


class SpendBudget:
    """A dollar cap for the run, fed by the charges Composio reports."""

    def __init__(self, limit_usd: float | None):
        self.limit_usd = limit_usd
        self.spent_usd = 0.0

    def check(self) -> None:
        if self.limit_usd is not None and self.spent_usd >= self.limit_usd:
            raise BudgetExhausted(f"Composio spend cap of ${self.limit_usd:.2f} is reached")

    def add(self, amount_usd: float) -> None:
        self.spent_usd += amount_usd


def is_short_provider_limit(error_text: str) -> bool:
    text = error_text.lower()
    limited = any(marker in text for marker in PROVIDER_LIMIT_MARKERS)
    exhausted = any(marker in text for marker in QUOTA_EXHAUSTED_MARKERS)
    return limited and not exhausted


def _leaves(error: BaseException) -> list[BaseException]:
    if isinstance(error, BaseExceptionGroup):
        return [leaf for inner in error.exceptions for leaf in _leaves(inner)]
    return [error]


def _retry_after(error: BaseException) -> float | None:
    for leaf in _leaves(error):
        if isinstance(leaf, httpx2.HTTPStatusError) and leaf.response.status_code == 429:
            return parse_retry_after(leaf.response.headers.get("retry-after"))
    return None


def mcp_transport(http: httpx2.AsyncClient, url: str = DEFAULT_MCP_URL) -> Call:
    """A function that makes one MCP tool call and returns Composio's JSON envelope.

    Each call opens its own short MCP session over the shared HTTP connection pool, so concurrent
    workers share no session state and a dropped session can never poison later calls.
    """

    @asynccontextmanager
    async def session():
        async with streamable_http_client(url, http_client=http) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                yield client

    async def call(name: str, arguments: dict) -> dict:
        async with session() as client:
            result = await client.call_tool(name, arguments)
        text = "".join(getattr(block, "text", "") for block in result.content)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"successful": False, "error": text or "empty response from Composio"}

    return call


def _charge(envelope: dict) -> float:
    charge = envelope.get("instant_charge") or {}
    return float(charge.get("amount") or 0)


def _first_response(envelope: dict) -> dict:
    """The single tool's own result inside a COMPOSIO_MULTI_EXECUTE_TOOL envelope."""
    if not envelope.get("successful"):
        return {"successful": False, "error": str(envelope.get("error") or "Composio reported a failure")}
    results = (envelope.get("data") or {}).get("results") or []
    if not results:
        return {"successful": False, "error": "Composio returned no result for the tool call"}
    return results[0].get("response") or {"successful": False, "error": "empty tool response"}


def _render(data: Any) -> str:
    text = json.dumps(data, ensure_ascii=False, default=str)
    if len(text) > MAX_RESULT_CHARS:
        return text[:MAX_RESULT_CHARS] + f"\n[result truncated: {len(text) - MAX_RESULT_CHARS} more characters not shown]"
    return text


def _guard(tool_slug: str, arguments: dict) -> dict:
    guarded = {**arguments, **FORCED_ARGUMENTS[tool_slug]}
    if tool_slug == SEARCH_TOOL:
        guarded["max_results"] = min(int(guarded.get("max_results") or 5), MAX_SEARCH_RESULTS)
    else:
        urls = guarded.get("urls") or []
        guarded["urls"] = ([urls] if isinstance(urls, str) else list(urls))[:MAX_URLS_PER_EXTRACT]
    return guarded


class ComposioTools:
    def __init__(
        self,
        call: Call,
        *,
        spend: SpendBudget,
        limiter: RateLimiter | None = None,
        policy: RetryPolicy = RetryPolicy(),
    ):
        self._call = call
        self._spend = spend
        self._limiter = limiter or RateLimiter(DEFAULT_CALLS_PER_MINUTE)
        self._policy = policy
        self._definitions: list[dict] = []

    async def load_definitions(self) -> None:
        """Fetch the research tools' schemas from Composio once and keep them in OpenAI function format."""
        envelope = await self._call("COMPOSIO_GET_TOOL_SCHEMAS", {"tool_slugs": list(RESEARCH_TOOLS)})
        schemas = (envelope.get("data") or {}).get("tool_schemas") or {}
        missing = [slug for slug in RESEARCH_TOOLS if slug not in schemas]
        if missing:
            raise RuntimeError(f"Composio did not return schemas for {missing}: {envelope.get('error')}")
        self._definitions = [
            {
                "type": "function",
                "name": slug,
                "description": schemas[slug]["description"],
                "parameters": schemas[slug]["input_schema"],
                "strict": False,
            }
            for slug in RESEARCH_TOOLS
        ]

    def definitions(self) -> list[dict]:
        return self._definitions

    async def _mcp(self, name: str, arguments: dict) -> dict:
        """One MCP call; any transport failure becomes a Retry so the caller's policy decides what happens."""
        try:
            return await self._call(name, arguments)
        except (MCPError, httpx2.HTTPError, TimeoutError, OSError, ExceptionGroup) as error:
            names = ", ".join(sorted({type(leaf).__name__ for leaf in _leaves(error)}))
            raise Retry(f"Composio MCP call failed ({names})", after=_retry_after(error)) from error

    async def _execute(self, tool_slug: str, arguments: dict, app_budget: CallBudget) -> tuple[dict, float, str]:
        """Run one paid tool call with retries. Returns the tool's response, the charge, and Composio's log id."""
        charged = 0.0
        log_id = ""

        async def attempt() -> dict:
            nonlocal charged, log_id
            self._spend.check()
            app_budget.spend()
            request = {
                "tools": [{"tool_slug": tool_slug, "arguments": _guard(tool_slug, arguments)}],
                "sync_response_to_workbench": False,
            }
            envelope = await self._mcp("COMPOSIO_MULTI_EXECUTE_TOOL", request)
            cost = _charge(envelope)
            charged += cost
            self._spend.add(cost)
            log_id = str(envelope.get("log_id") or "")
            response = _first_response(envelope)
            if not response.get("successful") and is_short_provider_limit(str(response.get("error") or "")):
                raise Retry("provider rate limit")
            return response

        response = await with_retry(attempt, limiter=self._limiter, policy=self._policy)
        return response, charged, log_id

    async def execute(self, tool_slug: str, arguments: dict, app_budget: CallBudget) -> ToolOutcome:
        """Run a research tool for the model. Expected failures come back as text the model can act on."""
        if tool_slug not in RESEARCH_TOOLS:
            return ToolOutcome(False, f"Unknown tool {tool_slug}. Available: {', '.join(RESEARCH_TOOLS)}.")
        try:
            response, charged, log_id = await self._execute(tool_slug, arguments, app_budget)
        except BudgetExhausted as error:
            return ToolOutcome(False, f"Paid tool budget exhausted ({error}). Finish with what you already have.")
        except RetriesExhausted as error:
            return ToolOutcome(False, f"Tool unavailable: {error}.")
        if not response.get("successful"):
            error_text = f"Tool call failed: {response.get('error') or 'no error message returned'}."
            return ToolOutcome(False, error_text, charged, log_id)
        if "data" in response:
            return ToolOutcome(True, _render(response["data"]), charged, log_id)
        # Composio moves large results to a remote file and returns only a preview.
        return ToolOutcome(
            True,
            "The full result was too large for Composio to return inline, so this is only a preview. "
            "For complete text, call again with a single URL and a specific query.\n"
            + _render(response.get("data_preview")),
            charged,
            log_id,
        )

    async def page_text(self, url: str, query: str, app_budget: CallBudget) -> tuple[str | None, float, str]:
        """Text of one page as Composio's extractor renders it, focused on `query`. For the quote checker."""
        arguments = {"urls": [url], "query": query[:300], "chunks_per_source": 5}
        try:
            response, charged, log_id = await self._execute(EXTRACT_TOOL, arguments, app_budget)
        except (BudgetExhausted, RetriesExhausted):
            return None, 0.0, ""
        if not response.get("successful"):
            return None, charged, log_id
        return " ".join(_strings(response.get("data") or response.get("data_preview"))) or None, charged, log_id

    async def catalog_lookup(self, app_name: str) -> tuple[list[dict], str] | None:
        """Ask Composio's own catalog search which toolkits it has for this app. Free. None if the lookup failed."""
        request = {
            "queries": [
                {"use_case": f"list records in the {app_name} app"},
                {"use_case": f"create or update an item using the {app_name} toolkit"},
            ]
        }

        async def attempt() -> dict:
            envelope = await self._mcp("COMPOSIO_SEARCH_TOOLS", request)
            if not envelope.get("successful") and is_short_provider_limit(str(envelope.get("error") or "")):
                raise Retry("Composio catalog search rate limit")
            return envelope

        try:
            envelope = await with_retry(attempt, limiter=self._limiter, policy=self._policy)
        except RetriesExhausted:
            return None
        if not envelope.get("successful"):
            return None
        statuses = (envelope.get("data") or {}).get("toolkit_connection_statuses") or []
        toolkits = [{"slug": str(s.get("toolkit") or ""), "description": str(s.get("description") or "")} for s in statuses]
        return toolkits, str(envelope.get("log_id") or "")


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []
