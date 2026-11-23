"""Turn a fetched page into text and test whether a quote appears in it."""

import html
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin

MIN_QUOTE_CHARS = 20
MIN_PAGE_CHARS = 200


class _TextExtractor(HTMLParser):
    SKIPPED = {"script", "style", "noscript", "template", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIPPED:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIPPED and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(markup)
    return " ".join(extractor.parts)


def normalize(text: str) -> str:
    """Lowercase and reduce every run of punctuation or whitespace to one space, so markup differences don't matter."""
    text = unicodedata.normalize("NFKC", html.unescape(text)).lower()
    return re.sub(r"[\W_]+", " ", text).strip()


def looks_rendered(page_text: str) -> bool:
    """False for the near-empty shell a JavaScript-rendered site returns to a plain HTTP client."""
    return len(normalize(page_text)) >= MIN_PAGE_CHARS


def long_enough(quote: str) -> bool:
    """A fragment such as a heading or a count matches too many pages to prove anything."""
    return len(normalize(quote)) >= MIN_QUOTE_CHARS


def contains_quote(quote: str, page_text: str) -> bool:
    return long_enough(quote) and normalize(quote) in normalize(page_text)


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((" ".join("".join(self._text).split()), self._href))
            self._href = None


def html_links(markup: str, base_url: str) -> list[tuple[str, str]]:
    """(link text, absolute URL) for each distinct http(s) link on the page, in page order."""
    extractor = _LinkExtractor()
    extractor.feed(markup)
    seen: set[str] = set()
    links = []
    for text, href in extractor.links:
        url = urldefrag(urljoin(base_url, href)).url
        if url.startswith(("http://", "https://")) and url not in seen and url != urldefrag(base_url).url:
            seen.add(url)
            links.append((text, url))
    return links
