"""Model calls through the OpenAI Responses API: a tool-using research loop and schema-constrained extraction."""

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from openai import APIConnectionError, AsyncOpenAI, InternalServerError, RateLimitError
from pydantic import BaseModel

from .resilience import RateLimiter, Retry, RetryPolicy, TokenWindow, parse_retry_after, with_retry
from .schema import ToolOutcome, Usage

LAST_TURN_NOTICE = "That was your last tool call. Write your final answer now from what you have."
NO_MORE_TOOLS = "No more tool calls are available. Write your final answer now from what you have."
DEFAULT_REQUESTS_PER_MINUTE = 120
DEFAULT_COOLDOWN_SECONDS = 20.0
MAX_COOLDOWN_SECONDS = 120.0
LLM_RETRY_POLICY = RetryPolicy(max_attempts=16, base_delay=2.0, max_delay=60.0)
# Every request re-sends the whole conversation, so its size is what a tokens-per-minute quota really meters.
DEFAULT_CONTEXT_LIMIT = 45_000
TPM_HEADROOM = 0.85

M = TypeVar("M", bound=BaseModel)
Execute = Callable[[str, dict], Awaitable[ToolOutcome]]


class LlmStopped(RuntimeError):
    """The model stopped without a usable answer (incomplete response, refusal, turn limit)."""


def estimate_tokens(*texts: str) -> int:
    """A deliberately high guess at a request's size, used only to pace requests before the real count is known."""
    return sum(len(text) for text in texts) // 3 + 500


def _record(usage: Usage, response: Any, *, critic: bool = False) -> None:
    usage.llm_calls += 1
    if critic:
        usage.critic_tokens += response.usage.input_tokens + response.usage.output_tokens
    usage.input_tokens += response.usage.input_tokens
    usage.output_tokens += response.usage.output_tokens
    usage.cached_input_tokens += response.usage.input_tokens_details.cached_tokens


def _server_wait(error: RateLimitError) -> float:
    """How long the endpoint asked us to wait, capped; a default when it did not say."""
    headers = error.response.headers
    milliseconds = parse_retry_after(headers.get("retry-after-ms"))
    seconds = milliseconds / 1000 if milliseconds is not None else parse_retry_after(headers.get("retry-after"))
    return min(seconds, MAX_COOLDOWN_SECONDS) if seconds is not None else DEFAULT_COOLDOWN_SECONDS


class Llm:
    """`model` researches and extracts; `critic_model` judges. Both come from the environment by default.

    The client should be created with max_retries=0: this class is the only retry layer. Requests are paced
    per model so the tokens sent in any minute stay under that deployment's quota (`tpm_limits`), and a 429
    that still gets through pauses every worker using that model.
    """

    def __init__(
        self,
        client: AsyncOpenAI,
        *,
        critic_client: AsyncOpenAI | None = None,
        model: str | None = None,
        critic_model: str | None = None,
        max_concurrency: int = 4,
        tpm_limits: dict[str, int] | None = None,
        limiters: dict[str, RateLimiter] | None = None,
        token_windows: dict[str, TokenWindow] | None = None,
        policy: RetryPolicy = LLM_RETRY_POLICY,
    ):
        self._client = client
        self._critic_client = critic_client or client
        self.model = model or os.environ["APPSCOUT_MODEL"]
        self.critic_model = critic_model or os.environ.get("APPSCOUT_CRITIC_MODEL", self.model)
        self._slots = asyncio.Semaphore(max_concurrency)
        self._limiters = limiters if limiters is not None else {}
        self._windows = token_windows if token_windows is not None else {
            name: TokenWindow(int(limit * TPM_HEADROOM)) for name, limit in (tpm_limits or {}).items()
        }
        self._policy = policy

    async def _request(self, model: str, estimate: int, send: Callable[[str], Awaitable[Any]]) -> Any:
        # Keyed by model name: two deployments have separate quotas even on one endpoint.
        limiter = self._limiters.setdefault(model, RateLimiter(DEFAULT_REQUESTS_PER_MINUTE))
        window = self._windows.get(model)

        async def attempt() -> Any:
            try:
                async with self._slots:
                    return await send(model)
            except RateLimitError as error:
                raise Retry("model rate limit", after=_server_wait(error)) from error
            except (APIConnectionError, InternalServerError) as error:
                raise Retry(f"model {type(error).__name__}") from error

        reservation = await window.reserve(estimate) if window else None
        try:
            response = await with_retry(attempt, limiter=limiter, policy=self._policy)
        except BaseException:
            if reservation is not None:
                TokenWindow.settle(reservation, 0)
            raise
        if reservation is not None:
            TokenWindow.settle(reservation, response.usage.input_tokens + response.usage.output_tokens)
        return response

    async def run_tools(
        self,
        *,
        system: str,
        prompt: str,
        tools: list[dict],
        execute: Execute,
        usage: Usage,
        max_turns: int = 12,
        context_limit: int = DEFAULT_CONTEXT_LIMIT,
    ) -> str:
        """Let the model call tools until it writes its answer. Returns the text of the final turn.

        The model gets one notice when it is about to run out of turns or its conversation has grown past
        `context_limit` tokens; tool calls after that notice are refused rather than executed.
        """

        async def run_call(call: Any) -> ToolOutcome:
            try:
                arguments = json.loads(call.arguments)
            except json.JSONDecodeError:
                return ToolOutcome(False, "The tool arguments were not valid JSON.")
            return await execute(call.name, arguments)

        next_input: list[dict] = [{"role": "user", "content": prompt}]
        previous_id = None
        estimate = estimate_tokens(system, prompt, json.dumps(tools))
        closing = False
        for turn in range(max_turns):
            request = {"input": next_input, "previous_response_id": previous_id}
            response = await self._request(
                self.model,
                estimate,
                lambda model: self._client.responses.create(model=model, instructions=system, tools=tools, **request),
            )
            _record(usage, response)
            calls = [item for item in response.output if item.type == "function_call"]
            if not calls:
                if response.status != "completed":
                    raise LlmStopped(f"research ended with status={response.status} ({response.incomplete_details})")
                return response.output_text

            if closing:
                outcomes = [ToolOutcome(False, NO_MORE_TOOLS)] * len(calls)
            else:
                outcomes = await asyncio.gather(*(run_call(call) for call in calls))
            outputs = [outcome.content if outcome.ok else f"ERROR: {outcome.content}" for outcome in outcomes]
            next_input = [
                {"type": "function_call_output", "call_id": call.call_id, "output": output}
                for call, output in zip(calls, outputs)
            ]
            if not closing and (turn >= max_turns - 2 or response.usage.input_tokens >= context_limit):
                closing = True
                next_input.append({"role": "user", "content": LAST_TURN_NOTICE})
            previous_id = response.id
            estimate = response.usage.input_tokens + response.usage.output_tokens + estimate_tokens(*outputs)
        raise LlmStopped(f"research did not finish within {max_turns} turns")

    async def extract(self, *, system: str, prompt: str, schema: type[M], usage: Usage, critic: bool = False) -> M:
        """One call whose output is guaranteed to match `schema`."""
        client = self._critic_client if critic else self._client
        response = await self._request(
            self.critic_model if critic else self.model,
            estimate_tokens(system, prompt) + 1500,
            lambda model: client.responses.parse(model=model, instructions=system, input=prompt, text_format=schema),
        )
        _record(usage, response, critic=critic)
        if response.output_parsed is None:
            raise LlmStopped(f"extraction returned no parsed output (status={response.status})")
        return response.output_parsed
