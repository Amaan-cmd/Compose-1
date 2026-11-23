"""The record every app is reduced to. Enumerated values are fixed so 100 records cluster cleanly."""

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel


class AuthMethod(StrEnum):
    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    BASIC = "basic"
    BEARER_TOKEN = "bearer_token"
    NONE = "none"
    OTHER = "other"
    UNKNOWN = "unknown"


class AccessLevel(StrEnum):
    SELF_SERVE_FREE = "self_serve_free"
    SELF_SERVE_TRIAL = "self_serve_trial"
    PAID_PLAN = "paid_plan"
    ADMIN_APPROVAL = "admin_approval"
    PARTNER_OR_SALES = "partner_or_sales"
    UNKNOWN = "unknown"


class ApiStyle(StrEnum):
    REST = "rest"
    GRAPHQL = "graphql"
    SOAP = "soap"
    SDK_ONLY = "sdk_only"
    OTHER = "other"


class Breadth(StrEnum):
    BROAD = "broad"
    MODERATE = "moderate"
    NARROW = "narrow"
    NONE = "none"
    UNKNOWN = "unknown"


class McpStatus(StrEnum):
    OFFICIAL = "official"
    COMMUNITY = "community"
    NONE_FOUND = "none_found"


class McpMaturity(StrEnum):
    GENERALLY_AVAILABLE = "generally_available"
    BETA_OR_PILOT = "beta_or_pilot"
    ANNOUNCED = "announced"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class DeploymentModel(StrEnum):
    CLOUD = "cloud"
    SELF_HOSTED = "self_hosted"
    BOTH = "both"
    UNKNOWN = "unknown"


class CatalogStatus(StrEnum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


class VerdictStatus(StrEnum):
    BUILDABLE_NOW = "buildable_now"
    BUILDABLE_WITH_CAVEATS = "buildable_with_caveats"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class Blocker(StrEnum):
    NONE = "none"
    TRIAL_ONLY = "trial_only"
    PAID_PLAN = "paid_plan"
    PARTNER_GATE = "partner_gate"
    ADMIN_APPROVAL = "admin_approval"
    NO_PUBLIC_API = "no_public_api"
    NARROW_API = "narrow_api"
    DOCS_GATED = "docs_gated"
    OTHER = "other"


class SourceType(StrEnum):
    OFFICIAL_DOCS = "official_docs"
    OFFICIAL_SITE = "official_site"
    THIRD_PARTY = "third_party"


class EvidenceField(StrEnum):
    AUTH = "auth"
    ACCESS = "access"
    API = "api"
    MCP = "mcp"
    COMPOSIO = "composio"


class QuoteCheck(StrEnum):
    EXACT = "exact"
    EXACT_RENDERED = "exact_rendered"
    TOO_SHORT = "too_short"
    NOT_FOUND = "not_found"
    UNREACHABLE = "unreachable"


class FieldResult(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNREACHABLE = "unreachable"


class AccessBasis(StrEnum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"
    NONE = "none"


class AccessReassessment(BaseModel):
    """A second reading of the access evidence already verified for a record."""

    level: AccessLevel
    basis: AccessBasis
    notes: str


class Auth(BaseModel):
    methods: list[AuthMethod]
    primary: AuthMethod
    notes: str


class Access(BaseModel):
    level: AccessLevel
    notes: str


class Api(BaseModel):
    styles: list[ApiStyle]
    breadth: Breadth
    public_docs: bool
    docs_url: str
    notes: str


class Mcp(BaseModel):
    status: McpStatus
    maturity: McpMaturity
    url: str
    notes: str


class ComposioListing(BaseModel):
    in_catalog: CatalogStatus
    url: str


class Verdict(BaseModel):
    status: VerdictStatus
    main_blocker: Blocker
    rationale: str


class EvidenceClaim(BaseModel):
    field: EvidenceField
    url: str
    quote: str
    source_type: SourceType


class Finding(BaseModel):
    """What the researcher asserts about one app. This is the model's structured output."""

    one_liner: str
    deployment_model: DeploymentModel
    auth: Auth
    access: Access
    api: Api
    mcp: Mcp
    composio: ComposioListing
    verdict: Verdict
    evidence: list[EvidenceClaim]
    problems: list[str]


class FieldJudgement(BaseModel):
    field: EvidenceField
    supported_by_quotes: bool
    note: str


class Judgement(BaseModel):
    """The checker model's structured output: does each claim follow from its verified quotes?"""

    fields: list[FieldJudgement]
    verdict_follows: bool
    verdict_note: str


class Evidence(EvidenceClaim):
    check: QuoteCheck


class Verification(BaseModel):
    field: str
    result: FieldResult
    note: str


class Usage(BaseModel):
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    critic_tokens: int = 0
    composio_calls: int = 0
    composio_usd: float = 0.0


class App(BaseModel):
    id: str
    name: str
    website: str
    category: str
    batch: int


class ComposioCall(BaseModel):
    """One call made through the Composio MCP endpoint, kept so usage can be audited against Composio's logs."""

    tool: str
    detail: str
    charged_usd: float
    log_id: str


class CatalogSource(StrEnum):
    DOCS_PAGE = "docs_page"
    MCP_LOOKUP = "mcp_lookup"
    TOOLKIT_PAGE = "toolkit_page"
    BOTH = "both"
    NONE = "none"


class CatalogLookup(BaseModel):
    """What Composio's catalog search returned for this app. matched_slug is empty when nothing matched."""

    matched_slug: str
    candidates: list[str]
    # Composio's public docs page for the toolkit, when one exists. None means the check has not been run.
    docs_slug: str | None = None


class Discovery(BaseModel):
    """The one web search every app gets through Composio before the model starts."""

    query: str
    results: str


class Record(Finding):
    id: str
    name: str
    website: str
    category: str
    batch: int
    in_composio_catalog: bool
    composio_toolkit_slug: str
    composio_catalog_source: CatalogSource
    composio_toolkit_url: str = ""
    # Set when the access level was re-read from the verified quotes: "explicit" or "inferred".
    access_basis: str = ""
    evidence: list[Evidence]
    verification: list[Verification]
    needs_human_review: bool
    review_reasons: list[str]
    attempts: int
    researched_at: str
    model: str
    critic_model: str
    usage: Usage
    composio_log: list[ComposioCall]


class Attempt(BaseModel):
    finding: Finding
    memo: str
    evidence_gaps: list[str]
    checks: list[QuoteCheck] | None = None
    verification: list[Verification] | None = None


class RunState(BaseModel):
    """Checkpoint for one app, saved after every stage so an interrupted run resumes where it stopped."""

    catalog: CatalogLookup | None = None
    discovery: Discovery | None = None
    # Which deployments did the research and the checking, kept so a later refresh does not relabel the record.
    model: str = ""
    critic_model: str = ""
    access_basis: str = ""
    attempts: list[Attempt] = []
    usage: Usage = Usage()
    composio_log: list[ComposioCall] = []
    last_error: str | None = None


@dataclass(frozen=True)
class ToolOutcome:
    ok: bool
    content: str
    cost_usd: float = 0.0
    log_id: str = ""
