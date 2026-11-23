# Which apps can become an agent toolkit today?

A 100-app study of how ready each app is to become an agent toolkit: its auth methods, how a developer gets credentials, its API surface, whether it already has an MCP server, whether Composio already has a toolkit for it, and a buildability verdict. Every claim carries a quote from the page it came from, and a program checks each quote against the live page.

- **Case study page:** `index.html` in this repo, published at <https://amaan-cmd.github.io/Compose-1/> once GitHub Pages is enabled. It is one self-contained file with no external requests; the full dataset is embedded in it as JSON.
- **Data:** `data/results.jsonl` (one record per app) and `data/apps_flat.csv` (one flat row per app).
- **Agent:** the `appscout` package in `src/`, built on Composio's Connect MCP endpoint for search, page extraction and catalog lookup.

## Findings (100 apps, researched 2026-11-23 and 2026-11-24)

| | Apps |
|---|---|
| Buildable now | 48 |
| Buildable with caveats (trial-only, admin approval, paid plan, narrow API) | 35 |
| Blocked (sales or partner gate, or no public API) | 7 |
| Verdict unknown | 10 |
| Already in Composio's catalog | 77 |
| Not in Composio's catalog | 23 |

- OAuth2 is the primary auth method for 65 apps; an API key for 18.
- 74 apps are self-serve (59 free, 15 trial-only), 15 are gated, and 11 could not be settled from quoted evidence.
- Seven apps are buildable now and not in Composio's catalog: Binance, Magento (Adobe Commerce), Netlify, Reducto, Vonage, WooCommerce and systeme.io.
- Five need outreach because an account takes a sales or partner contact: Gladly, Otter AI, PitchBook, Pylon and Salesforce Commerce Cloud.
- 1,251 of 1,287 quotes (97%) were found on the page they cite. 21 records are flagged for human review.

Accuracy, in three stages:

| Stage | Field values confirmed |
|---|---|
| First research attempt (the pipeline's own check) | 505 of 600 (84%) |
| Final records, after one repair attempt and a re-read of stored quotes | 576 of 600 (96%) |
| Human audit of 20 randomly drawn apps against the live docs | 95 of 100 values (95%) |

The five audit misses (Pipedrive's blocker, Smartsheet's access and verdict, Stripe's primary auth, Mermaid CLI's verdict) are listed on the page and corrected in the records; each corrected record keeps what the agent originally said in `human_corrections`.

These numbers are a snapshot. The page computes its own from the data, so it stays correct when records change. The page's "What went wrong" section lists the mistakes made along the way and what each one cost.

## Result files

| File | What it is |
|---|---|
| `index.html` | The case study. The dataset is embedded as `<script type="application/json" id="dataset">`. |
| `data/apps.csv` | The 100 apps: id, name, website hint, category, batch (1 to 10, one per category). |
| `data/results.jsonl` | One line per researched app, rewritten atomically after every app finishes. The source of truth. |
| `data/records/<id>.json` | The same records, one file per app. |
| `data/apps.json`, `data/apps_flat.csv` | Exports written by the page builder: full records, and one flat row per app. |
| `data/process_notes.json` | Hand-maintained log of mistakes and changes, rendered on the page. |
| `data/audit_sheet.md` | The human audit sheet: 20 apps, 2 drawn at random per category, with the evidence to check. |
| `data/audit.json` | The human audit results: 100 values, each a hit or a miss with the auditor's finding. |
| `data/corrections.json` | Values a person corrected after the audit. Applied whenever a record is rebuilt. |
| `data/pass1_results.json` | What each app's first research attempt looked like, for the page's accuracy progression. Written by `uv run python -m appscout.pass1`. |
| `data/state/` | Per-app checkpoints (git-ignored). A rerun resumes from them. |

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11 or later.

```bash
uv sync
cp .env.example .env    # then fill in the keys
```

`.env` needs a Composio Connect consumer key (sent to the Composio MCP endpoint as `x-consumer-api-key`), an OpenAI-compatible endpoint that serves the Responses API, and the deployment names for the researcher and the critic. More endpoints can be added by name; see the comments in `.env.example`. `.env` is git-ignored.

If the repository sits in a OneDrive folder on Windows, keep the virtual environment outside it, because OneDrive locks files and breaks `uv sync`:

```bash
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/appscout"
```

## Commands

```bash
uv run appscout run --batch 1     # research one category; skips apps that already have a record
uv run appscout run               # research every app that has no record yet
uv run appscout status            # progress for all 100 apps
uv run appscout refresh           # recheck the Composio catalog for finished apps; no research, no spend
uv run python -m appscout.page --repo-url https://github.com/Amaan-cmd/Compose-1
uv run pytest -q
```

- `run` options: `--only <id> ...`, `--force` (redo), `--max-spend` (Composio dollars for the run), `--paid-calls` and `--searches` (per-app caps), `--model`, `--critic-model`.
- `--researchers "model@ENDPOINT:workers/critic@ENDPOINT,..."` runs several researcher deployments at once, each with its own critic, so no model checks its own research. The full run used `gpt-6-sol`, `gpt-6.2-sol` and `grok-4.7`.
- `refresh --rejudge` reruns the critic on the stored quotes of flagged records. `refresh --reassess-access` re-reads an unknown access level from the quotes already verified.

A run can be interrupted at any point. Each stage of each app is checkpointed, records are written as each app finishes, and one app failing does not stop the others.

## How the pipeline works

1. **App list.** Name, website hint and category from `data/apps.csv`.
2. **Composio lookups.** For every app: Composio's catalog search, a check of Composio's toolkit docs page (`docs.composio.dev/toolkits/<slug>`), and one Composio web search for an MCP server. Every Composio call is logged on the record with its charge and Composio's log id.
3. **Researcher model.** Reads the official docs with a free direct page fetch that also lists each page's links. Composio's search and extract tools are rationed per app; the extractor is used only for pages the direct fetch cannot read.
4. **Evidence rule.** A field with no quoted evidence is reset to unknown.
5. **Quote check.** A program fetches every cited URL itself and string-matches the quote against the page text. Quotes on pages it cannot read get a second look through Composio's extractor.
6. **Critic model.** A different model from the researcher. It sees only the claims and the matched quotes and judges whether the quotes prove each field's value.
7. **One repair attempt.** Fields that fail are researched once more. A record that still fails is flagged for human review.
8. **Record.** Written atomically to `data/records/` and `data/results.jsonl`.

## How accuracy is checked

- **Quote check (deterministic).** Results per quote: `exact`, `exact_rendered` (found through Composio's extractor), `too_short` (under 20 characters; a fragment proves nothing), `not_found`, `unreachable`.
- **Critic (model).** Six verdicts per app: auth, access, API, MCP, the Composio catalog page, and whether the verdict follows from the rest.
- **Composio catalog flag.** True if Composio's docs have a page for the app's toolkit. The catalog search and a verified quote from a toolkit page are secondary signals; the catalog search alone missed Discord, Twilio, Telegram, Pumble and WhatsApp.
- **Access basis.** Where a record's access level was re-read from its verified quotes, it is marked `explicit` (one quote ties credentials to the plan) or `inferred` (a free or trial account anyone can open, plus self-service credential creation, with nothing restricting the API).
- **Human audit.** A person checks 20 apps (2 per category, drawn with a fixed seed) against the live docs using `data/audit_sheet.md`. Results go in `data/audit.json` as `{"checked_on", "sample_method", "items": [{"app", "field", "agent_value", "human_value", "match", "note"}]}` and are shown on the page, hits and misses alike.

`confidence_score` in the flat export is computed, not model-reported: the share of a record's checked fields the verification step marked supported.

## Cost controls

- **Per-app Composio cap.** Four paid calls per app (about $0.016 at the observed $0.004 per call), across research, repair and quote checks, including resumed runs. At most two of them may be web searches. The 100 apps cost about $0.75 of Composio credit in total.
- **Run cap.** `--max-spend` stops paid calls once the charges Composio reports for the run reach the limit.
- **Tokens-per-minute pacing.** Requests to each model deployment are held back so a rolling minute stays under its quota (`APPSCOUT_TPM_LIMITS`). A rate-limit response pauses every worker on that deployment.
- **Small page reads.** A page fetch returns about 12,000 characters at most, or the passages around keywords the model asks for, and a research conversation is told to stop reading once it passes a context ceiling.

## Known limitations

- **JavaScript-only pages.** The direct fetch does not run JavaScript. Quotes on such pages are verified only if Composio's extractor returns the passage; otherwise the item is `unreachable` and the record is flagged.
- **API breadth is an estimate.** No single quote can prove an API is broad, so the critic fails breadth only when a quote contradicts it.
- **"Not in Composio's catalog" means no toolkit docs page was found** under any spelling of the app's name. A toolkit filed under an unrelated name, or one without a docs page, would be missed.
- **Access is judged from public pages.** No accounts were created, so a signup flow that behaves differently from its documentation is not caught.
- **Three researcher models produced the records.** Each record names its researcher and critic. The critic is a model too: two critic models agreed on 81 of 84 field verdicts when given the same quotes.
- **Seven of the ten CRM records predate the final schema** and show deployment model and MCP maturity as not recorded.
- **Records are dated.** Docs and pricing change; each record carries the time it was researched.
