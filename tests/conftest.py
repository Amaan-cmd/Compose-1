import pytest

from appscout.schema import Finding

GOOD_QUOTE = "All API requests are authenticated with OAuth 2.0 access tokens."


def make_finding(**overrides) -> Finding:
    base = {
        "one_liner": "A CRM.",
        "deployment_model": "cloud",
        "auth": {"methods": ["oauth2"], "primary": "oauth2", "notes": ""},
        "access": {"level": "self_serve_free", "notes": ""},
        "api": {"styles": ["rest"], "breadth": "broad", "public_docs": True, "docs_url": "https://docs.example.com", "notes": ""},
        "mcp": {"status": "none_found", "maturity": "not_applicable", "url": "", "notes": ""},
        "composio": {"in_catalog": "no", "url": ""},
        "verdict": {"status": "buildable_now", "main_blocker": "none", "rationale": "Free credentials and a broad API."},
        "evidence": [
            {"field": "auth", "url": "https://docs.example.com/auth", "quote": GOOD_QUOTE, "source_type": "official_docs"},
            {"field": "access", "url": "https://docs.example.com/start", "quote": "Create a free developer account to get API credentials.", "source_type": "official_docs"},
            {"field": "api", "url": "https://docs.example.com/api", "quote": "The REST API covers contacts, companies, deals and tasks.", "source_type": "official_docs"},
        ],
        "problems": [],
    }
    base.update(overrides)
    return Finding.model_validate(base)


class FakeClock:
    """A clock whose sleep() advances time instantly and records each wait."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()
