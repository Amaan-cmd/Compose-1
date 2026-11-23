"""Fetch cited pages directly, independently of the tools that produced the evidence, and string-match quotes."""

import asyncio
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from .quotes import contains_quote, html_links, html_to_text, long_enough, looks_rendered
from .resilience import RateLimiter, RetriesExhausted, Retry, RetryPolicy, parse_retry_after, with_retry
from .schema import EvidenceClaim, QuoteCheck

USER_AGENT = "Mozilla/5.0 (compatible; appscout/0.1; evidence checker)"
RETRYABLE_STATUS = {429, 502, 503, 504}


_HTTP_URL = re.compile(r"https?://[^\s\"'<>\[\]]+")


def clean_urls(raw: object) -> list[str]:
    """The http(s) URLs inside whatever a model passed. Models sometimes wrap a URL in quotes or brackets,
    or send a list as one string."""
    if isinstance(raw, str):
        return _HTTP_URL.findall(raw)
    if isinstance(raw, list):
        return [url for item in raw for url in clean_urls(item)]
    return []


@dataclass(frozen=True)
class Page:
    text: str
    links: list[tuple[str, str]]


def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(follow_redirects=True, timeout=30.0, headers={"User-Agent": USER_AGENT})


class PageFetcher:
    """Fetches each URL once per run, with a separate rate limiter per host."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        per_host_per_minute: float = 30,
        policy: RetryPolicy = RetryPolicy(max_attempts=4),
    ):
        self._client = client
        self._per_host_per_minute = per_host_per_minute
        self._policy = policy
        self._limiters: dict[str, RateLimiter] = {}
        self._pages: dict[str, asyncio.Task[Page | None]] = {}

    async def page(self, url: str) -> Page | None:
        """The page's text and links, or None if it could not be loaded."""
        # Without a scheme the HTTP client fails in its cookie handling before any request is made.
        if not url.startswith(("http://", "https://")):
            return None
        task = self._pages.get(url)
        if task is None:
            task = self._pages[url] = asyncio.create_task(self._fetch(url))
        return await task

    async def text(self, url: str) -> str | None:
        page = await self.page(url)
        return page.text if page else None

    async def _fetch(self, url: str) -> Page | None:
        host = urlsplit(url).netloc
        limiter = self._limiters.setdefault(host, RateLimiter(self._per_host_per_minute))

        async def attempt() -> httpx.Response:
            try:
                response = await self._client.get(url)
            except httpx.TransportError as error:
                raise Retry(f"{type(error).__name__} fetching {url}") from error
            if response.status_code in RETRYABLE_STATUS:
                raise Retry(
                    f"HTTP {response.status_code} from {host}",
                    after=parse_retry_after(response.headers.get("retry-after")),
                )
            return response

        try:
            response = await with_retry(attempt, limiter=limiter, policy=self._policy)
        except (RetriesExhausted, httpx.InvalidURL):
            return None
        if response.status_code != 200:
            return None
        if "html" in response.headers.get("content-type", ""):
            return Page(html_to_text(response.text), html_links(response.text, str(response.url)))
        return Page(response.text, [])


async def check_quote(claim: EvidenceClaim, fetcher: PageFetcher) -> QuoteCheck:
    if not long_enough(claim.quote):
        return QuoteCheck.TOO_SHORT
    text = await fetcher.text(claim.url)
    if text is None or not looks_rendered(text):
        return QuoteCheck.UNREACHABLE
    return QuoteCheck.EXACT if contains_quote(claim.quote, text) else QuoteCheck.NOT_FOUND


async def check_evidence(evidence: list[EvidenceClaim], fetcher: PageFetcher) -> list[QuoteCheck]:
    return list(await asyncio.gather(*(check_quote(claim, fetcher) for claim in evidence)))
