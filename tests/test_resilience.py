import pytest

from appscout.resilience import (
    BudgetExhausted,
    CallBudget,
    RateLimiter,
    RetriesExhausted,
    Retry,
    RetryPolicy,
    parse_retry_after,
    with_retry,
)


async def test_limiter_spaces_calls_evenly(clock):
    limiter = RateLimiter(60, clock=clock, sleep=clock.sleep)
    for _ in range(3):
        await limiter.acquire()
    assert clock.sleeps == [1.0, 1.0]


async def test_cooldown_delays_every_later_caller(clock):
    limiter = RateLimiter(6000, clock=clock, sleep=clock.sleep)
    await limiter.acquire()
    limiter.cool_down(12)
    await limiter.acquire()
    assert clock.sleeps == [12.0]


async def test_server_retry_after_becomes_a_shared_cooldown(clock):
    limiter = RateLimiter(6000, clock=clock, sleep=clock.sleep)
    attempts = []

    async def attempt():
        attempts.append(clock.now)
        if len(attempts) == 1:
            raise Retry("rate limited", after=7)
        return "ok"

    assert await with_retry(attempt, limiter=limiter, sleep=clock.sleep) == "ok"
    assert attempts == [0.0, 7.0]


async def test_backoff_uses_capped_full_jitter_when_no_wait_is_given(clock):
    limiter = RateLimiter(6_000_000, clock=clock, sleep=clock.sleep)
    ceilings = []

    def jitter(low, high):
        ceilings.append(high)
        return high

    async def attempt():
        raise Retry("flaky")

    policy = RetryPolicy(max_attempts=4, base_delay=1.0, max_delay=3.0)
    with pytest.raises(RetriesExhausted, match="flaky"):
        await with_retry(attempt, limiter=limiter, policy=policy, sleep=clock.sleep, jitter=jitter)
    assert ceilings == [1.0, 2.0, 3.0]


async def test_other_errors_are_not_retried(clock):
    limiter = RateLimiter(6000, clock=clock, sleep=clock.sleep)
    calls = 0

    async def attempt():
        nonlocal calls
        calls += 1
        raise ValueError("bad input")

    with pytest.raises(ValueError):
        await with_retry(attempt, limiter=limiter, sleep=clock.sleep)
    assert calls == 1


def test_budget_refuses_calls_past_its_limit():
    budget = CallBudget(2)
    budget.spend()
    budget.spend()
    with pytest.raises(BudgetExhausted):
        budget.spend()
    assert budget.used == 2


def test_retry_after_parsing():
    assert parse_retry_after("12") == 12.0
    assert parse_retry_after("-3") == 0.0
    assert parse_retry_after("Wed, 21 Oct 2026 07:28:00 GMT") is None
    assert parse_retry_after(None) is None
