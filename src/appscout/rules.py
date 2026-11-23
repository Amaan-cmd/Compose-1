"""Deterministic accuracy rules: no quote means no claim, and a claim stands only if its quote was found."""

import re

from .schema import (
    AccessLevel,
    Auth,
    AuthMethod,
    Blocker,
    Breadth,
    CatalogStatus,
    EvidenceField,
    FieldResult,
    Finding,
    Judgement,
    McpMaturity,
    McpStatus,
    QuoteCheck,
    Verdict,
    VerdictStatus,
    Verification,
)

NO_EVIDENCE = "No quoted evidence was found."
FOUND = (QuoteCheck.EXACT, QuoteCheck.EXACT_RENDERED)


# Words that pad a product or toolkit name without saying which product it is.
GENERIC_NAME_WORDS = ("com", "io", "ai", "app", "hq", "crm", "inc", "business")


def _base_name(text: str) -> str:
    """The name with any parenthetical and generic words removed, squashed to letters and digits."""
    words = re.findall(r"[a-z0-9]+", re.sub(r"\(.*?\)", "", text.lower()))
    kept = [word for word in words if word not in GENERIC_NAME_WORDS] or words
    return "".join(kept)


def toolkit_slug_candidates(app_name: str) -> list[str]:
    """Slugs Composio might file this app under, most specific spellings first: "Help Scout" could be
    `help_scout` or `helpscout`; "Monday.com" could be `monday`."""
    words = re.findall(r"[a-z0-9]+", re.sub(r"\(.*?\)", "", app_name.lower()))
    kept = [word for word in words if word not in GENERIC_NAME_WORDS] or words
    candidates = ["_".join(words), "".join(words), "_".join(kept), "".join(kept)]
    return list(dict.fromkeys(candidates))


def match_toolkit(app_name: str, slugs: list[str]) -> str:
    """The catalog slug that names this app, or "" if none does.

    The names must be the same once generic words are dropped: "Zoho CRM" is `zoho`, "Monday.com" is
    `monday`, "Close" is `closeio`. A toolkit for a different product from the same vendor does not match:
    "Zoho Cliq" is not `zoho` and "Salesforce Commerce Cloud" is not `salesforce`.
    """
    name = _base_name(app_name)
    for slug in slugs:
        candidate = _base_name(slug)
        if candidate == name or candidate in {name + word for word in GENERIC_NAME_WORDS}:
            return slug
    return ""


def claims_made(finding: Finding) -> dict[EvidenceField, bool]:
    """Which fields assert something that needs a quote behind it."""
    return {
        EvidenceField.AUTH: finding.auth.primary != AuthMethod.UNKNOWN,
        EvidenceField.ACCESS: finding.access.level != AccessLevel.UNKNOWN,
        EvidenceField.API: finding.api.breadth != Breadth.UNKNOWN,
        EvidenceField.MCP: finding.mcp.status != McpStatus.NONE_FOUND,
        EvidenceField.COMPOSIO: finding.composio.in_catalog == CatalogStatus.YES,
    }


def _reset(finding: Finding, field: EvidenceField) -> None:
    if field == EvidenceField.AUTH:
        finding.auth = Auth(methods=[], primary=AuthMethod.UNKNOWN, notes=NO_EVIDENCE)
    elif field == EvidenceField.ACCESS:
        finding.access.level = AccessLevel.UNKNOWN
        finding.access.notes = NO_EVIDENCE
    elif field == EvidenceField.API:
        finding.api.styles = []
        finding.api.breadth = Breadth.UNKNOWN
        finding.api.notes = NO_EVIDENCE
    elif field == EvidenceField.MCP:
        finding.mcp.status = McpStatus.NONE_FOUND
        finding.mcp.maturity = McpMaturity.NOT_APPLICABLE
        finding.mcp.url = ""
        finding.mcp.notes = NO_EVIDENCE
    else:
        finding.composio.in_catalog = CatalogStatus.UNKNOWN
        finding.composio.url = ""


def enforce_evidence(finding: Finding) -> list[str]:
    """Reset every claim that has no quote to unknown. Returns the fields that were reset."""
    quoted = {e.field for e in finding.evidence if e.url.strip() and e.quote.strip()}
    gaps = [field for field, claims in claims_made(finding).items() if claims and field not in quoted]
    for field in gaps:
        _reset(finding, field)
    unknown_basis = finding.access.level == AccessLevel.UNKNOWN or finding.api.breadth == Breadth.UNKNOWN
    if unknown_basis and finding.verdict.status != VerdictStatus.UNKNOWN:
        finding.verdict = Verdict(
            status=VerdictStatus.UNKNOWN,
            main_blocker=Blocker.OTHER,
            rationale="Access or API coverage could not be established from quoted evidence.",
        )
    return [str(field) for field in gaps]


def combine(finding: Finding, checks: list[QuoteCheck], judgement: Judgement) -> list[Verification]:
    """Merge the string-match result for each quote with the checker's reading of what the quotes prove."""
    judged = {j.field: j for j in judgement.fields}
    results: list[Verification] = []
    for field, claims in claims_made(finding).items():
        field_checks = [check for item, check in zip(finding.evidence, checks) if item.field == field]
        if not claims:
            result, note = FieldResult.SUPPORTED, "No claim was made, so there is nothing to check."
        elif any(check in FOUND for check in field_checks):
            judgement_for_field = judged.get(field)
            if judgement_for_field is None:
                result, note = FieldResult.UNSUPPORTED, "The checker returned no judgement for this field."
            elif judgement_for_field.supported_by_quotes:
                result, note = FieldResult.SUPPORTED, judgement_for_field.note
            else:
                result, note = FieldResult.UNSUPPORTED, judgement_for_field.note
        elif field_checks and all(check == QuoteCheck.UNREACHABLE for check in field_checks):
            result, note = FieldResult.UNREACHABLE, "None of the cited pages could be read without a browser."
        elif field_checks and all(check == QuoteCheck.TOO_SHORT for check in field_checks):
            result, note = FieldResult.UNSUPPORTED, "Every quote for this field is too short to verify."
        else:
            result, note = FieldResult.UNSUPPORTED, "The quoted text was not found on the cited page."
        results.append(Verification(field=str(field), result=result, note=note))

    by_field = {v.field: v.result for v in results}
    basis_confirmed = by_field["access"] == FieldResult.SUPPORTED and by_field["api"] == FieldResult.SUPPORTED
    if finding.verdict.status == VerdictStatus.UNKNOWN:
        result, note = FieldResult.SUPPORTED, "No verdict was given."
    elif not judgement.verdict_follows:
        result, note = FieldResult.UNSUPPORTED, judgement.verdict_note
    elif not basis_confirmed:
        result, note = FieldResult.UNSUPPORTED, "The verdict rests on access or API claims that were not confirmed."
    else:
        result, note = FieldResult.SUPPORTED, judgement.verdict_note
    results.append(Verification(field="verdict", result=result, note=note))
    return results


def failed_fields(verification: list[Verification]) -> list[str]:
    return [v.field for v in verification if v.result != FieldResult.SUPPORTED]


def review_reasons(finding: Finding, verification: list[Verification]) -> list[str]:
    """Why a human should look at this record. A gate with evidence is a finding, not a reason."""
    reasons = [f"{v.field}: {v.result} ({v.note})" for v in verification if v.result != FieldResult.SUPPORTED]
    if finding.auth.primary == AuthMethod.UNKNOWN:
        reasons.append("auth is unknown")
    if finding.access.level == AccessLevel.UNKNOWN:
        reasons.append("access is unknown")
    if finding.api.breadth == Breadth.UNKNOWN:
        reasons.append("api is unknown")
    return reasons


def derive_verdict(finding: Finding) -> Verdict | None:
    """The verdict that follows from access and API coverage under the definitions, or None if either is unknown."""
    access, breadth = finding.access.level, finding.api.breadth
    if breadth == Breadth.NONE:
        return Verdict(status=VerdictStatus.BLOCKED, main_blocker=Blocker.NO_PUBLIC_API, rationale="No public API is documented.")
    if access == AccessLevel.UNKNOWN or breadth == Breadth.UNKNOWN:
        return None
    if access == AccessLevel.PARTNER_OR_SALES:
        return Verdict(
            status=VerdictStatus.BLOCKED,
            main_blocker=Blocker.PARTNER_GATE,
            rationale="Getting an account takes a sales or partnership conversation.",
        )
    caveat = {
        AccessLevel.SELF_SERVE_TRIAL: (Blocker.TRIAL_ONLY, "Credentials are only available through a time-limited trial."),
        AccessLevel.PAID_PLAN: (Blocker.PAID_PLAN, "API access needs a paid plan."),
        AccessLevel.ADMIN_APPROVAL: (Blocker.ADMIN_APPROVAL, "API use needs an admin or vendor approval step."),
    }.get(access)
    if caveat is None and breadth == Breadth.NARROW:
        caveat = (Blocker.NARROW_API, "Credentials are self-serve, but the API is narrow.")
    if caveat:
        return Verdict(status=VerdictStatus.BUILDABLE_WITH_CAVEATS, main_blocker=caveat[0], rationale=caveat[1])
    return Verdict(
        status=VerdictStatus.BUILDABLE_NOW,
        main_blocker=Blocker.NONE,
        rationale="Credentials are self-serve and free, and the documented API is broad enough to be useful.",
    )
