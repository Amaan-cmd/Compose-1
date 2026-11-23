"""Per-app flow: Composio lookups -> research -> enforce evidence -> verify -> one repair attempt -> record."""

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from .composio_tools import EXTRACT_TOOL, RESEARCH_TOOLS, SEARCH_TOOL
from .fetch import PageFetcher, check_evidence
from .prompts import (
    ACCESS_SYSTEM,
    EXTRACT_SYSTEM,
    JUDGE_SYSTEM,
    RESEARCH_SYSTEM,
    access_prompt,
    extract_prompt,
    judge_prompt,
    research_prompt,
)
from .quotes import contains_quote
from .resilience import CallBudget
from .rules import (
    FOUND,
    combine,
    derive_verdict,
    enforce_evidence,
    failed_fields,
    match_toolkit,
    review_reasons,
    toolkit_slug_candidates,
)
from .schema import (
    AccessLevel,
    AccessReassessment,
    App,
    Attempt,
    CatalogLookup,
    CatalogSource,
    CatalogStatus,
    ComposioCall,
    Discovery,
    Evidence,
    EvidenceField,
    Finding,
    Judgement,
    QuoteCheck,
    Record,
    RunState,
    ToolOutcome,
    VerdictStatus,
)
from .store import Store

MAX_ATTEMPTS = 2
# Composio's docs serve a page titled "<App> - Composio Toolkit" for every toolkit and a 404 otherwise.
TOOLKIT_DOCS_URL = "https://docs.composio.dev/toolkits/{slug}"


@dataclass
class Deps:
    llm: Any
    tools: Any
    fetcher: PageFetcher
    store: Store
    now: Callable[[], str]
    # Composio charges $0.004 per paid call, so 4 calls caps an app at $0.016 across every attempt and check.
    paid_calls_per_app: int = 4
    searches_per_app: int = 2


def _log(state: RunState, tool: str, detail: str, charged_usd: float, log_id: str) -> None:
    state.composio_log.append(ComposioCall(tool=tool, detail=detail, charged_usd=charged_usd, log_id=log_id))


async def _toolkit_docs_slug(app: App, deps: Deps, hint: str) -> str:
    """The slug of this app's toolkit page in Composio's public docs, or "" if no spelling of it exists."""
    slugs = list(dict.fromkeys(([hint] if hint else []) + toolkit_slug_candidates(app.name)))
    for slug in slugs:
        page = await deps.fetcher.page(TOOLKIT_DOCS_URL.format(slug=slug))
        if page is not None and "composio toolkit" in page.text.lower():
            return slug
    return ""


async def check_catalog(app: App, deps: Deps, state: RunState) -> None:
    """Free catalog checks: Composio's own search, then its public docs page. Safe to repeat."""
    if state.catalog is None:
        lookup = await deps.tools.catalog_lookup(app.name)
        if lookup is not None:
            toolkits, log_id = lookup
            slugs = [toolkit["slug"] for toolkit in toolkits]
            state.catalog = CatalogLookup(matched_slug=match_toolkit(app.name, slugs), candidates=slugs)
            _log(state, "COMPOSIO_SEARCH_TOOLS", f"catalog lookup for {app.name}", 0.0, log_id)
    if state.catalog is not None and state.catalog.docs_slug is None:
        state.catalog.docs_slug = await _toolkit_docs_slug(app, deps, state.catalog.matched_slug)


def _searches_used(state: RunState) -> int:
    return sum(1 for call in state.composio_log if call.tool == SEARCH_TOOL)


async def _prepare(app: App, deps: Deps, state: RunState, budget: CallBudget) -> None:
    """Two Composio calls every app gets before the model starts: a free catalog lookup and one web search."""
    await check_catalog(app, deps, state)
    if state.discovery is None:
        query = f"{app.name} MCP server (Model Context Protocol)"
        outcome = await deps.tools.execute(SEARCH_TOOL, {"query": query, "max_results": 6}, budget)
        state.usage.composio_calls = budget.used
        state.usage.composio_usd += outcome.cost_usd
        _log(state, SEARCH_TOOL, query, outcome.cost_usd, outcome.log_id)
        if outcome.ok:
            state.discovery = Discovery(query=query, results=outcome.content)


async def _research(
    app: App, deps: Deps, state: RunState, previous: Attempt | None, budget: CallBudget
) -> Attempt:
    searches = _searches_used(state)

    async def execute(tool_slug: str, arguments: dict):
        nonlocal searches
        if tool_slug == SEARCH_TOOL:
            if searches >= deps.searches_per_app:
                return ToolOutcome(
                    False, "Search limit for this app reached. Navigate with fetch_page and the links it lists."
                )
            searches += 1
        outcome = await deps.tools.execute(tool_slug, arguments, budget)
        state.usage.composio_calls = budget.used
        state.usage.composio_usd += outcome.cost_usd
        if tool_slug in RESEARCH_TOOLS:
            detail = arguments.get("query") or ", ".join(arguments.get("urls") or [])
            _log(state, tool_slug, str(detail), outcome.cost_usd, outcome.log_id)
        return outcome

    prompt = research_prompt(
        app,
        focus=failed_fields(previous.verification) if previous else [],
        previous=previous.finding if previous else None,
        paid_calls_left=max(0, deps.paid_calls_per_app - budget.used),
        searches_left=max(0, deps.searches_per_app - searches),
        catalog=state.catalog,
        discovery=state.discovery,
    )
    memo = await deps.llm.run_tools(
        system=RESEARCH_SYSTEM, prompt=prompt, tools=deps.tools.definitions(), execute=execute, usage=state.usage
    )
    finding = await deps.llm.extract(
        system=EXTRACT_SYSTEM, prompt=extract_prompt(app, memo), schema=Finding, usage=state.usage
    )
    gaps = enforce_evidence(finding)
    return Attempt(finding=finding, memo=memo, evidence_gaps=gaps)


async def _recheck_rendered(
    attempt: Attempt, checks: list[QuoteCheck], deps: Deps, state: RunState, budget: CallBudget
) -> None:
    """Second chance for quotes on pages the direct fetch could not read: look through Composio's extractor."""
    for index, item in enumerate(attempt.finding.evidence):
        if checks[index] != QuoteCheck.UNREACHABLE:
            continue
        text, charged, log_id = await deps.tools.rendered_text(item.url, item.quote, budget)
        state.usage.composio_usd += charged
        if log_id:
            _log(state, EXTRACT_TOOL, f"quote check on {item.url}", charged, log_id)
        # The extractor returns excerpts, so a miss proves nothing; only a hit changes the result.
        if text and contains_quote(item.quote, text):
            checks[index] = QuoteCheck.EXACT_RENDERED
    state.usage.composio_calls = budget.used


async def judge(attempt: Attempt, deps: Deps, state: RunState) -> None:
    """Ask the critic whether the already-checked quotes prove each field. Reusable without re-fetching."""
    judgement = await deps.llm.extract(
        system=JUDGE_SYSTEM,
        prompt=judge_prompt(attempt.finding, attempt.checks),
        schema=Judgement,
        usage=state.usage,
        critic=True,
    )
    attempt.verification = combine(attempt.finding, attempt.checks, judgement)


async def _verify(attempt: Attempt, deps: Deps, state: RunState, budget: CallBudget) -> None:
    checks = await check_evidence(attempt.finding.evidence, deps.fetcher)
    await _recheck_rendered(attempt, checks, deps, state, budget)
    attempt.checks = checks
    await judge(attempt, deps, state)


def _catalog_status(best: Attempt, state: RunState) -> tuple[bool, str, CatalogSource, str]:
    """In the catalog if Composio's docs have a page for the toolkit, its own search matched one, or a quote
    from its toolkit page was verified. The docs page is the strongest signal and is checked for every app."""
    docs_slug = (state.catalog.docs_slug or "") if state.catalog else ""
    if docs_slug:
        return True, docs_slug, CatalogSource.DOCS_PAGE, TOOLKIT_DOCS_URL.format(slug=docs_slug)
    slug = state.catalog.matched_slug if state.catalog else ""
    page_verified = (
        best.finding.composio.in_catalog == CatalogStatus.YES and "composio" not in failed_fields(best.verification)
    )
    if slug and page_verified:
        source = CatalogSource.BOTH
    elif slug:
        source = CatalogSource.MCP_LOOKUP
    elif page_verified:
        source = CatalogSource.TOOLKIT_PAGE
    else:
        source = CatalogSource.NONE
    return source != CatalogSource.NONE, slug, source, ""


def _best(state: RunState) -> Attempt:
    """The attempt with the fewest unconfirmed fields; the later one on a tie."""
    return min(reversed(state.attempts), key=lambda attempt: len(failed_fields(attempt.verification)))


def _build_record(app: App, state: RunState, deps: Deps) -> Record:
    best = _best(state)
    evidence = [
        Evidence(**item.model_dump(), check=check) for item, check in zip(best.finding.evidence, best.checks)
    ]
    reasons = review_reasons(best.finding, best.verification)
    if state.catalog is None:
        reasons.append("Composio catalog lookup did not run")
    if state.discovery is None:
        reasons.append("the mandatory Composio web search did not run")
    in_catalog, toolkit_slug, catalog_source, toolkit_url = _catalog_status(best, state)
    return Record(
        **best.finding.model_dump(exclude={"evidence"}),
        **app.model_dump(),
        in_composio_catalog=in_catalog,
        composio_toolkit_slug=toolkit_slug,
        composio_catalog_source=catalog_source,
        composio_toolkit_url=toolkit_url,
        access_basis=state.access_basis,
        evidence=evidence,
        verification=best.verification,
        needs_human_review=bool(reasons),
        review_reasons=reasons,
        attempts=len(state.attempts),
        researched_at=deps.now(),
        model=state.model or deps.llm.model,
        critic_model=state.critic_model or deps.llm.critic_model,
        usage=state.usage,
        composio_log=state.composio_log,
    )


async def _reassess_access(app: App, deps: Deps, state: RunState, attempt: Attempt) -> bool:
    """Re-read an unknown access level from the access quotes already verified. True if it is now known."""
    verified = any(
        check in FOUND
        for item, check in zip(attempt.finding.evidence, attempt.checks)
        if item.field == EvidenceField.ACCESS
    )
    if attempt.finding.access.level != AccessLevel.UNKNOWN or not verified:
        return False
    reading = await deps.llm.extract(
        system=ACCESS_SYSTEM,
        prompt=access_prompt(app, attempt.finding, attempt.checks),
        schema=AccessReassessment,
        usage=state.usage,
    )
    if reading.level == AccessLevel.UNKNOWN:
        return False
    attempt.finding.access.level = reading.level
    attempt.finding.access.notes = reading.notes
    state.access_basis = str(reading.basis)
    return True


async def refresh_app(app: App, deps: Deps, *, rejudge: bool, reassess: bool = False) -> Record | None:
    """Update a finished app without researching it again.

    Always reruns the free catalog checks. With `reassess`, an unknown access level is re-read from the quotes
    already verified, and a verdict left unknown is filled in by the fixed rule. With `rejudge`, or whenever
    the record changed, the critic judges the stored quotes afresh. Returns None if the app has no record yet.
    """
    state = deps.store.load_state(app.id)
    previous = deps.store.load_record(app.id)
    # Only finished apps: one that is part-way through still has research or a repair attempt to come.
    if state is None or previous is None:
        return None
    state.attempts = [attempt for attempt in state.attempts if attempt.verification is not None]
    if not state.model:
        state.model, state.critic_model = previous.model, previous.critic_model
    if state.catalog is not None:
        state.catalog.docs_slug = None
    await check_catalog(app, deps, state)
    best = _best(state)
    changed = reassess and await _reassess_access(app, deps, state, best)
    if reassess and best.finding.verdict.status == VerdictStatus.UNKNOWN:
        derived = derive_verdict(best.finding)
        if derived is not None:
            best.finding.verdict = derived
            changed = True
    if rejudge or changed:
        await judge(best, deps, state)
        state.critic_model = deps.llm.critic_model
    deps.store.save_state(app.id, state)
    record = _build_record(app, state, deps)
    deps.store.save_record(record)
    return record


async def run_app(app: App, deps: Deps) -> Record:
    """Research one app, resuming from its checkpoint if a previous run was interrupted."""
    state = deps.store.load_state(app.id) or RunState()
    state.last_error = None
    state.model, state.critic_model = deps.llm.model, deps.llm.critic_model
    budget = CallBudget(deps.paid_calls_per_app)
    budget.used = state.usage.composio_calls  # the cap covers the whole app, including earlier interrupted runs
    try:
        while True:
            last = state.attempts[-1] if state.attempts else None
            if last is not None and last.verification is None:
                await _verify(last, deps, state, budget)
            elif last is None or (failed_fields(last.verification) and len(state.attempts) < MAX_ATTEMPTS):
                await _prepare(app, deps, state, budget)
                state.attempts.append(await _research(app, deps, state, last, budget))
            else:
                break
            deps.store.save_state(app.id, state)
    except Exception as error:
        # Keep the usage spent so far and the reason, so the next run resumes and the cost stays honest.
        state.last_error = f"{type(error).__name__}: {error}"
        deps.store.save_state(app.id, state)
        raise
    record = _build_record(app, state, deps)
    deps.store.save_record(record)
    return record


async def run_batch(
    apps: list[App], deps: Deps, *, concurrency: int = 3, pool: list[tuple[Any, int]] | None = None
) -> list[Record | Exception]:
    """Run apps concurrently. One app failing is recorded on its checkpoint and never stops the others.

    `pool` is a list of (researcher, workers), one entry per model deployment. Every worker takes the next
    waiting app, so a deployment with more quota simply gets through more apps. Without a pool, `deps.llm`
    runs `concurrency` workers.
    """
    waiting = deque(enumerate(apps))
    results: list[Record | Exception | None] = [None] * len(apps)

    async def worker(llm: Any) -> None:
        worker_deps = replace(deps, llm=llm)
        while waiting:
            index, app = waiting.popleft()
            try:
                results[index] = await run_app(app, worker_deps)
            except Exception as error:
                results[index] = error

    researchers = pool or [(deps.llm, concurrency)]
    await asyncio.gather(*(worker(llm) for llm, workers in researchers for _ in range(workers)))
    return results
