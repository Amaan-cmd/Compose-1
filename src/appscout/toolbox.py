"""The tools the research model sees: a free direct page fetch, plus Composio's paid search and extract."""

from urllib.parse import urlsplit

from .composio_tools import EXTRACT_TOOL, ComposioTools
from .fetch import Page, PageFetcher, clean_urls
from .quotes import looks_rendered
from .resilience import CallBudget
from .schema import ToolOutcome

FETCH_TOOL = "fetch_page"
# Everything a tool returns is re-sent on every later request, so page views are kept small and targeted.
MAX_PAGE_CHARS = 12_000
OPENING_CHARS = 1_500
PASSAGE_BEFORE = 400
PASSAGE_AFTER = 800
MAX_LINKS = 40

FETCH_PAGE = {
    "type": "function",
    "name": FETCH_TOOL,
    "description": (
        "Fetch one web page directly. Free and unlimited. Returns the page text followed by the links on it, so "
        "you can navigate a site page by page. Long pages are cut off after about 12,000 characters: pass `find` "
        "with a few keywords (for example ['API', 'OAuth', 'free', 'trial']) to get the passages around those "
        "words instead. It cannot run JavaScript, so it fails on pages that only render in a browser; "
        "TAVILY_EXTRACT is the fallback for those."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Full URL of the page, including https://"},
            "find": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional keywords. On a long page, only the passages around them are returned.",
            },
        },
        "required": ["url"],
        "additionalProperties": False,
    },
    "strict": False,
}


def _passages(text: str, keywords: list[str]) -> str | None:
    """Verbatim windows of `text` around each keyword, merged where they overlap, up to the page limit."""
    lowered = text.lower()
    spans: list[tuple[int, int]] = []
    for keyword in keywords:
        needle = keyword.lower().strip()
        position = lowered.find(needle) if needle else -1
        while position != -1:
            spans.append((max(0, position - PASSAGE_BEFORE), min(len(text), position + len(needle) + PASSAGE_AFTER)))
            position = lowered.find(needle, position + len(needle))
    if not spans:
        return None
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    parts: list[str] = []
    total = 0
    for start, end in merged:
        if total + (end - start) > MAX_PAGE_CHARS:
            break
        parts.append(text[start:end])
        total += end - start
    return "\n[...]\n".join(parts)


def _body(page: Page, find: list[str]) -> str:
    text = " ".join(page.text.split())
    if len(text) <= MAX_PAGE_CHARS:
        return text
    found = _passages(text, find)
    if found:
        return (
            f"[This page is {len(text):,} characters long. Shown: its opening, then the passages matching {find}.]\n"
            f"{text[:OPENING_CHARS]}\n[...]\n{found}"
        )
    hint = "None of the `find` keywords appear on it." if find else "Call fetch_page again with `find` keywords to read specific passages."
    return f"{text[:MAX_PAGE_CHARS]}\n[Page cut off: {len(text) - MAX_PAGE_CHARS:,} more characters not shown. {hint}]"


def _render(url: str, page: Page, find: list[str]) -> str:
    host = urlsplit(url).netloc
    # Same-site links first: they are the ones worth following for docs, pricing and help pages.
    links = sorted(page.links, key=lambda link: urlsplit(link[1]).netloc != host)[:MAX_LINKS]
    body = _body(page, find)
    if not links:
        return body
    listing = "\n".join(f"- {label or '(no text)'}: {link}" for label, link in links)
    return f"{body}\n\nLINKS ON THIS PAGE\n{listing}"


class Toolbox:
    def __init__(self, composio: ComposioTools, fetcher: PageFetcher):
        self._composio = composio
        self._fetcher = fetcher

    def definitions(self) -> list[dict]:
        return [FETCH_PAGE, *self._composio.definitions()]

    async def _readable(self, url: str) -> Page | None:
        page = await self._fetcher.page(url)
        return page if page is not None and looks_rendered(page.text) else None

    async def execute(self, name: str, arguments: dict, app_budget: CallBudget) -> ToolOutcome:
        if name == FETCH_TOOL:
            return await self._fetch_page(arguments)
        if name == EXTRACT_TOOL:
            return await self._extract(arguments, app_budget)
        return await self._composio.execute(name, arguments, app_budget)

    async def _fetch_page(self, arguments: dict) -> ToolOutcome:
        urls = clean_urls(arguments.get("url"))
        if not urls:
            return ToolOutcome(False, "fetch_page needs one full URL starting with https://.")
        url = urls[0]
        find = [word for word in arguments.get("find") or [] if isinstance(word, str)]
        page = await self._readable(url)
        if page is None:
            return ToolOutcome(
                False,
                "This page could not be read directly (missing, blocked, or rendered by JavaScript). "
                "Try a different page, or TAVILY_EXTRACT on this one if you have a paid call left.",
            )
        return ToolOutcome(True, _render(url, page, find))

    async def _extract(self, arguments: dict, app_budget: CallBudget) -> ToolOutcome:
        """The paid extractor is only for pages the free fetch cannot read; readable ones are served directly."""
        urls = clean_urls(arguments.get("urls"))
        query = arguments.get("query")
        find = [query] if isinstance(query, str) and query else []
        direct: list[str] = []
        unreadable: list[str] = []
        for url in urls:
            page = await self._readable(url)
            if page is None:
                unreadable.append(url)
            else:
                direct.append(f"{url} (read directly, no charge)\n{_render(url, page, find)}")
        if not unreadable:
            return ToolOutcome(bool(direct), "\n\n".join(direct) or "TAVILY_EXTRACT needs at least one URL.")
        outcome = await self._composio.execute(EXTRACT_TOOL, {**arguments, "urls": unreadable}, app_budget)
        content = "\n\n".join([*direct, outcome.content])
        return ToolOutcome(outcome.ok or bool(direct), content, outcome.cost_usd, outcome.log_id)

    async def rendered_text(self, url: str, quote: str, app_budget: CallBudget) -> tuple[str | None, float, str]:
        """Page text through Composio's extractor, for quotes on pages the direct fetch cannot read."""
        return await self._composio.page_text(url, quote, app_budget)

    async def catalog_lookup(self, app_name: str) -> tuple[list[dict], str] | None:
        return await self._composio.catalog_lookup(app_name)
