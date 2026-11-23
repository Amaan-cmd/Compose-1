from types import SimpleNamespace

import httpx2
import pytest
from openai import APIConnectionError, RateLimitError

from appscout.llm import DEFAULT_COOLDOWN_SECONDS, Llm
from appscout.resilience import RateLimiter, RetriesExhausted, RetryPolicy, TokenWindow
from appscout.schema import Judgement, Usage

REQUEST = httpx2.Request("POST", "https://model.test/v1/responses")
JUDGEMENT = Judgement(fields=[], verdict_follows=True, verdict_note="ok")


def rate_limited(headers: dict) -> RateLimitError:
    return RateLimitError("exceeded token rate limit", response=httpx2.Response(429, headers=headers, request=REQUEST), body=None)


def parsed():
    usage = SimpleNamespace(input_tokens=10, output_tokens=1, input_tokens_details=SimpleNamespace(cached_tokens=0))
    return SimpleNamespace(output_parsed=JUDGEMENT, status="completed", usage=usage)


class ScriptedClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self.responses = SimpleNamespace(parse=self._parse)

    async def _parse(self, **request):
        self.calls += 1
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def make_llm(client, clock, attempts=5) -> Llm:
    return Llm(
        client,
        model="m",
        critic_model="critic",
        limiters={name: RateLimiter(6000, clock=clock, sleep=clock.sleep) for name in ("m", "critic")},
        policy=RetryPolicy(max_attempts=attempts, base_delay=0.0, max_delay=0.0),
    )


async def extract(llm):
    return await llm.extract(system="s", prompt="p", schema=Judgement, usage=Usage())


async def test_model_429_pauses_for_the_time_the_endpoint_asks_then_succeeds(clock):
    client = ScriptedClient([rate_limited({"retry-after": "37"}), parsed()])
    assert await extract(make_llm(client, clock)) == JUDGEMENT
    assert clock.sleeps == [37.0]


async def test_millisecond_header_is_understood_and_long_waits_are_capped(clock):
    client = ScriptedClient([rate_limited({"retry-after-ms": "1500"}), rate_limited({"retry-after": "3600"}), parsed()])
    await extract(make_llm(client, clock))
    assert clock.sleeps == [1.5, 120.0]


async def test_429_without_a_wait_time_still_pauses_every_worker(clock):
    client = ScriptedClient([rate_limited({}), parsed()])
    await extract(make_llm(client, clock))
    assert clock.sleeps == [DEFAULT_COOLDOWN_SECONDS]


async def test_connection_errors_are_retried(clock):
    client = ScriptedClient([APIConnectionError(request=REQUEST), parsed()])
    assert await extract(make_llm(client, clock)) == JUDGEMENT
    assert client.calls == 2


async def test_persistent_rate_limiting_ends_in_a_clear_error_after_the_policy_runs_out(clock):
    client = ScriptedClient([rate_limited({"retry-after": "1"})] * 3)
    with pytest.raises(RetriesExhausted, match="model rate limit"):
        await extract(make_llm(client, clock, attempts=3))
    assert client.calls == 3


async def test_a_throttled_researcher_does_not_stall_a_critic_on_another_deployment(clock):
    client = ScriptedClient([rate_limited({"retry-after": "50"}), parsed()])
    llm = make_llm(client, clock, attempts=1)
    with pytest.raises(RetriesExhausted):
        await extract(llm)
    usage = Usage()
    await llm.extract(system="s", prompt="p", schema=Judgement, usage=usage, critic=True)
    assert clock.sleeps == []
    assert usage.critic_tokens == 11


async def test_critic_calls_go_to_the_critic_endpoint_when_one_is_given(clock):
    researcher, critic = ScriptedClient([parsed()]), ScriptedClient([parsed()])
    llm = Llm(researcher, critic_client=critic, model="m", critic_model="critic")
    await llm.extract(system="s", prompt="p", schema=Judgement, usage=Usage(), critic=True)
    assert (researcher.calls, critic.calls) == (0, 1)
    await llm.extract(system="s", prompt="p", schema=Judgement, usage=Usage())
    assert (researcher.calls, critic.calls) == (1, 1)


async def test_requests_wait_for_room_in_the_deployments_tokens_per_minute_window(clock):
    window = TokenWindow(1000, clock=clock, sleep=clock.sleep)
    first = await window.reserve(700)
    TokenWindow.settle(first, 900)
    await window.reserve(200)
    assert clock.sleeps == [60.0]


async def test_a_request_bigger_than_the_whole_quota_goes_once_the_window_is_empty(clock):
    window = TokenWindow(1000, clock=clock, sleep=clock.sleep)
    await window.reserve(5000)
    assert clock.sleeps == []
    await window.reserve(5000)
    assert clock.sleeps == [60.0]


async def test_model_calls_are_paced_by_their_real_token_counts(clock):
    client = ScriptedClient([parsed(), parsed()])
    window = TokenWindow(5000, clock=clock, sleep=clock.sleep)
    llm = Llm(
        client,
        model="m",
        token_windows={"m": window},
        limiters={"m": RateLimiter(6_000_000, clock=clock, sleep=clock.sleep)},
    )
    await extract(llm)
    await extract(llm)
    # Each call is estimated high, then settled at its real 11 tokens, so the second call needs no wait.
    assert [sleep for sleep in clock.sleeps if sleep >= 1] == []
    assert sum(entry[1] for entry in window._reservations) == 22
