"""Shared rate limiting, retry and budget primitives used by every outbound call."""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


class BudgetExhausted(RuntimeError):
    pass


class RetriesExhausted(RuntimeError):
    pass


class Retry(Exception):
    """Raised inside an attempt to ask for another try. `after` is a server-given wait in seconds."""

    def __init__(self, reason: str, after: float | None = None):
        super().__init__(reason)
        self.reason = reason
        self.after = after


class CallBudget:
    def __init__(self, limit: int | None):
        self.limit = limit
        self.used = 0

    def spend(self) -> None:
        if self.limit is not None and self.used >= self.limit:
            raise BudgetExhausted(f"call budget of {self.limit} is used up")
        self.used += 1


class RateLimiter:
    """Spaces calls evenly and lets any caller impose a cooldown that every caller then waits out."""

    def __init__(
        self,
        per_minute: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._interval = 60.0 / per_minute
        self._next_slot = 0.0
        self._clock = clock
        self._sleep = sleep

    async def acquire(self) -> None:
        now = self._clock()
        wait = self._next_slot - now
        self._next_slot = max(now, self._next_slot) + self._interval
        if wait > 0:
            await self._sleep(wait)

    def cool_down(self, seconds: float) -> None:
        self._next_slot = max(self._next_slot, self._clock() + seconds)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay: float = 1.0
    max_delay: float = 30.0


async def with_retry(
    attempt: Callable[[], Awaitable[T]],
    *,
    limiter: RateLimiter,
    policy: RetryPolicy = RetryPolicy(),
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    jitter: Callable[[float, float], float] = random.uniform,
) -> T:
    """Run `attempt` under the limiter, retrying whenever it raises Retry.

    A server-given wait becomes a shared cooldown; otherwise this caller backs off with full jitter.
    """
    for n in range(policy.max_attempts):
        await limiter.acquire()
        try:
            return await attempt()
        except Retry as retry:
            if n == policy.max_attempts - 1:
                raise RetriesExhausted(f"{retry.reason} (gave up after {policy.max_attempts} attempts)") from retry
            if retry.after is not None:
                limiter.cool_down(retry.after)
            else:
                await sleep(jitter(0, min(policy.max_delay, policy.base_delay * 2**n)))
    raise AssertionError("unreachable")


def parse_retry_after(value: str | None) -> float | None:
    try:
        return max(0.0, float(value or ""))
    except ValueError:
        return None


class TokenWindow:
    """Paces requests so the tokens sent in any rolling minute stay under a deployment's tokens-per-minute quota.

    A caller reserves its estimated size before sending and settles the reservation with the real count
    afterwards. A request larger than the whole quota is let through once the window is empty.
    """

    def __init__(
        self,
        per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        period: float = 60.0,
    ):
        self.per_minute = per_minute
        self._clock = clock
        self._sleep = sleep
        self._period = period
        self._reservations: list[list[float]] = []

    async def reserve(self, tokens: int) -> list[float]:
        while True:
            now = self._clock()
            self._reservations = [entry for entry in self._reservations if now - entry[0] < self._period]
            in_window = sum(entry[1] for entry in self._reservations)
            if not self._reservations or in_window + tokens <= self.per_minute:
                reservation = [now, float(tokens)]
                self._reservations.append(reservation)
                return reservation
            await self._sleep(self._reservations[0][0] + self._period - now)

    @staticmethod
    def settle(reservation: list[float], actual_tokens: int) -> None:
        reservation[1] = float(actual_tokens)
