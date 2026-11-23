"""Prompts for the three model roles: researcher, extractor, checker."""

import json

from .rules import FOUND
from .schema import App, CatalogLookup, Discovery, Finding, QuoteCheck

DEFINITIONS = """
FIELD DEFINITIONS (use these exact values)

auth.methods: every method the public API documents for integrations. Values: oauth2, api_key, basic, bearer_token (personal access tokens, static bearer tokens, JWT you mint yourself), none (the API is open and needs no credentials), other.
auth.primary: the method the docs recommend for a third-party integration acting on behalf of the app's users (usually oauth2 when offered). If only one method exists, that one. unknown if not evidenced.

access.level: the MOST ACCESSIBLE path to working API credentials for a developer who is not already a customer.
- self_serve_free: a free account, free tier, developer edition or sandbox yields API credentials with no payment and no approval.
- self_serve_trial: credentials are obtainable alone, but only inside a time-limited free trial.
- paid_plan: API access needs a paid subscription and no free or trial path to credentials exists.
- admin_approval: anyone can open an account, but API use then needs an admin to enable it or a vendor review/approval step.
- partner_or_sales: getting an account at all takes a partnership agreement, a sales conversation or an enterprise contract. This takes precedence over admin_approval: if the only route to an account is a demo request or contacting sales, the level is partner_or_sales even though a customer's admin later enables the API.
- unknown: not evidenced.
Put nuance in access.notes (for example: development works self-serve but public distribution of an OAuth app needs review).

deployment_model: cloud (only the vendor's hosted service), self_hosted (only software you run yourself), both (open-source or downloadable, and also offered as a hosted service). When it is both, access.level is still the most accessible path, and access.notes must say which deployment that path uses and what the other one requires (for example: free when self-hosted, trial-only on the vendor's cloud).

api.styles: rest, graphql, soap, sdk_only (no documented HTTP API, only a vendor SDK), other. api.breadth: broad (most core objects, read and write), moderate (several core objects), narrow (few endpoints or read-only), none (no public API), unknown. api.public_docs: true if the API reference is readable without logging in. api.docs_url: the main API docs URL.

mcp.status: official (published or hosted by the vendor), community (third-party only), none_found.
mcp.maturity: generally_available (released and usable now), beta_or_pilot (usable but labelled beta, preview or pilot, or already given an end-of-life date), announced (promised but not usable yet), not_applicable (status is none_found), unknown. If the vendor has only announced a server and a third party offers one today, report the third party's as community and say so in mcp.notes.
composio.in_catalog: yes if Composio already lists a toolkit for this app in its public toolkit catalog or docs, no if you looked and it is absent, unknown if you could not check.

verdict.status:
- buildable_now: self-serve credentials AND a documented API with enough breadth to be useful.
- buildable_with_caveats: buildable, but with a notable constraint (trial-only, paid plan, narrow API, review step).
- blocked: no way to get credentials or no usable public API without partnership, sales or an enterprise contract.
- unknown: access or api is unknown.
verdict.main_blocker: none, trial_only (credentials come only through a time-limited trial), paid_plan (a paid subscription with no trial path), partner_gate, admin_approval, no_public_api, narrow_api, docs_gated, other.
verdict.rationale: one or two sentences using only facts that have evidence.
"""

RESEARCH_SYSTEM = f"""You research one app at a time for a study of 100 apps: how ready is each one to become an agent toolkit, meaning a set of API-backed tools an AI agent can call on a user's behalf?

Your findings are published together with their evidence. After you finish, a program fetches every URL you cite and string-matches your quote against the page, and a second model then judges whether the matched quotes prove your claims. A quote that is not on the page counts against the record. Accuracy therefore matters more than completeness: an honest "unknown" is a correct answer, and a plausible guess is a failure.

TOOLS
- fetch_page reads one page directly and lists the links on it. It is free: do all your reading and navigating with it. Start from the official docs or site URL you already know or the website hint, and follow the listed links to the authentication, pricing, plans, FAQ and help pages. Long pages are cut off, so pass `find` keywords (for example API, OAuth, free, trial, plan) to get the passages you need.
- Be economical. Everything you read stays in your working memory, and you will be told to stop once it fills up, usually after eight to ten pages. Go straight to the pages most likely to settle a field, and fetch several in one step when you already know which you need.
- TAVILY_SEARCH and TAVILY_EXTRACT cost money and are tightly rationed; the task states how many you have left. Keep TAVILY_SEARCH for something you cannot reach by following links. Use TAVILY_EXTRACT only on a page fetch_page has failed to read, with one URL and a specific query.
- When the ration is used up, finish with what you have. An honest unknown is better than an unverified claim.
- Two lookups have already been run for you through Composio and are in the task: a web search for an MCP server for this app, and Composio's own catalog search. Read the MCP search results before deciding mcp, and open any promising result with fetch_page to get a quote. Report mcp as none_found only if neither those results nor the vendor's docs show one.
- For the composio field, fetch Composio's toolkit page for the app (https://docs.composio.dev/toolkits/ followed by the toolkit slug) and quote a full sentence from it. Report no only if the catalog search found no match and that page does not exist. The pipeline also checks that page itself, so do not spend paid calls on this field.

Work from the app's official developer documentation wherever possible, then its official site (pricing and plan pages matter for access), and third-party sources only as a last resort. What you already know about the app is useful for deciding where to look, never as evidence.
{DEFINITIONS}
EVIDENCE RULES
- auth, access and api each need at least one piece of evidence: the page URL plus a quote copied character for character from that page's text as fetch_page or TAVILY_EXTRACT returned it. Search result snippets are not evidence; open the page. mcp needs one when the status is official or community. composio needs one when the app is in the catalog.
- Each quote must be one or two complete sentences, at least six words long. Headings, button labels, counts and table cells on their own ("Create a New Lead", "143 Tools") are rejected as too short to prove anything. Choose the sentence that most directly proves the value you picked.
- For access, the quote has to tie API access or credential creation to the specific plan, trial or account type you are claiming: "API keys are available on all plans, including Free", "the 14-day trial includes full API access". A quote showing that a free plan exists plus another showing that an API exists does not prove the free plan includes the API. Some platforms have no plans to tie it to, because the API is simply open to anyone who registers (a bot platform, a developer portal with no pricing): there the proof is the getting-started or developer-portal sentence saying anyone can create an app, bot or token. Pricing tables often lose their columns when read as text, so prefer an FAQ, help-centre or docs sentence that states it outright.
- Cite the URL of the page the quote is actually on, not a search result page.
- If no single sentence ties credentials to a plan, give the two quotes that together show it (the free plan or trial anyone can open, and self-service credential creation) and say the level is inferred. Report unknown only when you could not find those either.
- For partner_or_sales, quote the page showing that the only route to an account is a demo request, a sales contact or an existing contract.
- If you cannot find quoted evidence for a field, report it as unknown and say why. A gate is a valid finding: if API access needs payment, a sales call or a partnership, report that with the quote that says so.

When you are done, write a research memo in plain text with one section per field (one-liner, auth, access, api, mcp, composio, verdict). Each section gives the value you chose under the definitions, a short justification, and its evidence as URL plus exact quote. End with a "Problems" section listing anything that defeated you: login walls, pages that would not load, contradictory docs."""

EXTRACT_SYSTEM = f"""You convert a research memo about one app into a structured record. Use only what the memo states. Copy every URL and quote exactly as written in the memo; do not correct, shorten or merge quotes. If the memo gives no quoted evidence for a field, set that field to unknown (none_found for mcp, unknown for composio) rather than filling it in yourself.
{DEFINITIONS}"""

JUDGE_SYSTEM = f"""You are the independent checker for a published study of how ready apps are to become agent toolkits. You are given one record's claims and the quotes that a program has already confirmed are present, verbatim, on the cited pages. Decide for each field whether those quotes prove the field's value under the definitions. Treat the quotes as the only facts available: do not use your own knowledge of the app to rescue a claim, and do not accept a claim because it is plausible. If a field has no confirmed quote, it is not supported.

What has to be proven, field by field:
- auth: the quotes show that the primary method exists and nothing in them points to a different recommended method. Judge what the credential is, not the label: a static token sent in an Authorization header may fairly be listed as bearer_token or api_key, so do not fail the field over which of the two was chosen. If another listed method has no quote of its own, say so in your note but do not fail the field for it.
- access: the quotes prove the level chosen. This is the field most often wrong, so be exact: a free plan that includes API access proves self_serve_free; "contact sales" proves partner_or_sales; a quote that only shows an API exists proves nothing about access. Some platforms sell no plans at all for their API: there, a quote showing that anyone can register and create an app, bot or token in a public developer portal proves self_serve_free, provided nothing quoted mentions payment, a trial or approval.
- api: the quotes show a public API of the stated styles exists. An HTTP API documented with endpoints, methods or JSON requests counts as rest even if no quote uses the word REST. Breadth is the researcher's estimate from reading the endpoint reference, which no single quote can prove, so accept it unless the quotes contradict it (for example, breadth broad when a quote says the API is read-only).
- mcp: the quote shows the server exists, and for official, that the vendor publishes or hosts it. Fail it if a quote contradicts the maturity given (for example, generally_available when the quote says the server is a pilot or not yet launched).
- composio: the quote is from a Composio page listing a toolkit for this app.

Access can be proven in two ways. Explicit: a quote ties API access or credential creation to the plan, trial or account type. Inferred: one quote shows a free plan, free account or self-serve trial that anyone can open, another shows that an account holder creates API credentials themselves (a key in settings, a developer app, a token), and nothing quoted restricts the API to paid plans, approval or sales. Inferred is acceptable for self_serve_free and self_serve_trial; say that it is inferred. Software that runs locally and needs no credentials is self_serve_free.

Judge the values only. The notes are commentary: if a note says something the quotes do not show, say so in your note for that field, but do not fail the field for it.

Then decide whether verdict.status and verdict.main_blocker follow from the auth, access and api values under the definitions.
{DEFINITIONS}"""


def _app_block(app: App) -> str:
    return f"App: {app.name}\nWebsite hint: {app.website}\nCategory: {app.category}"


def _lookups_block(catalog: CatalogLookup | None, discovery: Discovery | None) -> str:
    if catalog is None:
        catalog_text = "The catalog search could not be run."
    elif catalog.matched_slug:
        catalog_text = f"Composio has a toolkit with the slug `{catalog.matched_slug}` that matches this app."
    else:
        nearest = ", ".join(catalog.candidates) or "none"
        catalog_text = f"No toolkit matching this app was returned. Nearest results: {nearest}."
    if discovery is None:
        search_text = "The search could not be run. Run it yourself with TAVILY_SEARCH."
    else:
        search_text = f'Query: "{discovery.query}"\n{discovery.results}'
    return f"COMPOSIO CATALOG SEARCH (already run)\n{catalog_text}\n\nMCP WEB SEARCH (already run)\n{search_text}"


def research_prompt(
    app: App,
    *,
    focus: list[str],
    previous: Finding | None,
    paid_calls_left: int,
    searches_left: int,
    catalog: CatalogLookup | None,
    discovery: Discovery | None,
) -> str:
    limit = (
        f"Paid calls left for this app: {paid_calls_left} in total, of which at most {searches_left} may be TAVILY_SEARCH. "
        "fetch_page is free and unlimited."
    )
    context = f"{_app_block(app)}\n\n{_lookups_block(catalog, discovery)}"
    if previous is None:
        return f"Research this app and write the memo. {limit}\n\n{context}"
    return (
        f"{limit} A previous attempt at this app failed verification on these fields: {', '.join(focus)}. "
        "Its quotes for those fields were not found on the cited pages, or did not prove the value chosen. "
        "Research those fields again from the live pages and settle what is true. For every other field, "
        "repeat the previous value and evidence unchanged in your memo.\n\n"
        f"{context}\n\nPREVIOUS RECORD\n{previous.model_dump_json(indent=2)}"
    )


def extract_prompt(app: App, memo: str) -> str:
    return f"{_app_block(app)}\n\nRESEARCH MEMO\n{memo}"


def judge_prompt(finding: Finding, checks: list[QuoteCheck]) -> str:
    claims = finding.model_dump(mode="json", exclude={"evidence", "problems"})
    confirmed = [
        {"field": item.field, "url": item.url, "quote": item.quote}
        for item, check in zip(finding.evidence, checks)
        if check in FOUND
    ]
    return (
        f"CLAIMS\n{json.dumps(claims, indent=2)}\n\n"
        f"QUOTES CONFIRMED ON THE CITED PAGES\n{json.dumps(confirmed, indent=2)}\n\n"
        "Return a judgement for each of auth, access, api, mcp and composio, then the verdict."
    )


ACCESS_SYSTEM = f"""You re-read the access evidence for one app in a published study of how ready apps are to become agent toolkits. A researcher recorded the access level as unknown. You are given every quote that a program confirmed is on the cited page, plus the researcher's notes. Decide the access level from those quotes alone; do not use your own knowledge of the app.

Access can be proven in two ways. Explicit: a quote ties API access or credential creation to the plan, trial or account type. Inferred: one quote shows a free plan, free account or self-serve trial that anyone can open, another shows that an account holder creates API credentials themselves (a key in settings, a developer app, a token), and nothing quoted restricts the API to paid plans, approval or sales. Inferred is acceptable for self_serve_free and self_serve_trial; say that it is inferred. Software that runs locally and needs no credentials is self_serve_free.

Set basis to explicit, inferred, or none. If the quotes do not establish a level either way, answer unknown with basis none: an honest unknown is a correct answer. In notes, give one or two sentences naming the quotes you relied on.
{DEFINITIONS}"""


def access_prompt(app: App, finding: Finding, checks: list[QuoteCheck]) -> str:
    confirmed = [
        {"field": item.field, "url": item.url, "quote": item.quote}
        for item, check in zip(finding.evidence, checks)
        if check in FOUND
    ]
    notes = {"access_notes": finding.access.notes, "deployment_model": finding.deployment_model, "problems": finding.problems}
    return (
        f"{_app_block(app)}\n\nRESEARCHER'S NOTES\n{json.dumps(notes, indent=2)}\n\n"
        f"QUOTES CONFIRMED ON THE CITED PAGES\n{json.dumps(confirmed, indent=2)}"
    )
