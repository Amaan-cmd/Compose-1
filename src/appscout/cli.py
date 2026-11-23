"""Command line: run a batch through the research pipeline, or show status."""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx2
from dotenv import load_dotenv
from openai import AsyncOpenAI

from .composio_tools import DEFAULT_MCP_URL, ComposioTools, SpendBudget, mcp_transport
from .fetch import PageFetcher, http_client
from .llm import TPM_HEADROOM, Llm
from .pipeline import Deps, refresh_app, run_batch
from .resilience import TokenWindow
from .store import Store
from .toolbox import Toolbox


def _endpoint(name: str) -> AsyncOpenAI:
    """A model endpoint named in .env by prefix: NAME_BASE_URL and NAME_API_KEY (the default name is OPENAI)."""
    return AsyncOpenAI(base_url=os.environ[f"{name}_BASE_URL"], api_key=os.environ[f"{name}_API_KEY"], max_retries=0)


def _tpm_limits(setting: str) -> dict[str, int]:
    """Parse APPSCOUT_TPM_LIMITS, e.g. "gpt-6-sol=125000,gpt-6.2-sol=100000". Models not listed are not paced."""
    pairs = (item.split("=") for item in setting.split(",") if item.strip())
    return {name.strip(): int(limit) for name, limit in pairs}


def _researchers(setting: str) -> list[tuple[str, str, int, str | None, str | None]]:
    """Parse "model@ENDPOINT:workers[/critic@ENDPOINT],...".

    Example: "gpt-6-sol@OPENAI:3/grok-4.7@OPENAI,grok-4.7@OPENAI:2". The optional part after the slash
    gives that researcher its own critic, so no model ends up checking its own research.
    """
    pool = []
    for item in (part.strip() for part in setting.split(",") if part.strip()):
        research, _, critic = item.partition("/")
        target, _, workers = research.partition(":")
        model, _, endpoint = target.partition("@")
        critic_model, _, critic_endpoint = critic.partition("@")
        pool.append((model, endpoint or "OPENAI", int(workers or 1), critic_model or None, critic_endpoint or None))
    return pool


async def _run(args: argparse.Namespace, store: Store) -> int:
    apps = [app for app in store.apps(args.batch) if not args.only or app.id in args.only]
    if args.command == "refresh":
        apps = [app for app in apps if (store.state_dir / f"{app.id}.json").exists()]
    elif args.force:
        for app in apps:
            store.clear(app.id)
    else:
        apps = [app for app in apps if store.load_record(app.id) is None]
    if not apps:
        print("Nothing to do: every selected app already has a record (use --force to redo).")
        return 0

    spend = SpendBudget(args.max_spend)
    composio_headers = {"x-consumer-api-key": os.environ["COMPOSIO_CONSUMER_KEY"]}
    async with http_client() as pages, httpx2.AsyncClient(headers=composio_headers, timeout=120.0) as composio_http:
        composio = ComposioTools(mcp_transport(composio_http, os.environ.get("COMPOSIO_MCP_URL", DEFAULT_MCP_URL)), spend=spend)
        await composio.load_definitions()
        fetcher = PageFetcher(pages)
        # One pacing window and one limiter per deployment, shared by every researcher and the critic.
        limits = _tpm_limits(os.environ.get("APPSCOUT_TPM_LIMITS", ""))
        windows = {name: TokenWindow(int(limit * TPM_HEADROOM)) for name, limit in limits.items()}
        limiters: dict = {}
        default_critic = args.critic_endpoint or os.environ.get("APPSCOUT_CRITIC_ENDPOINT", "OPENAI")

        def researcher(
            model: str | None,
            endpoint: str,
            workers: int,
            critic_model: str | None = None,
            critic_endpoint: str | None = None,
        ) -> Llm:
            return Llm(
                _endpoint(endpoint),
                critic_client=_endpoint(critic_endpoint or default_critic),
                model=model,
                critic_model=critic_model or args.critic_model,
                max_concurrency=workers,
                token_windows=windows,
                limiters=limiters,
            )

        pool_setting = args.researchers or os.environ.get("APPSCOUT_RESEARCHERS", "")
        pool = [(researcher(*entry), entry[2]) for entry in _researchers(pool_setting)]
        default_endpoint = args.researcher_endpoint or os.environ.get("APPSCOUT_RESEARCHER_ENDPOINT", "OPENAI")
        deps = Deps(
            llm=pool[0][0] if pool else researcher(args.model, default_endpoint, args.concurrency),
            tools=Toolbox(composio, fetcher),
            fetcher=fetcher,
            store=store,
            now=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"),
            paid_calls_per_app=args.paid_calls,
            searches_per_app=args.searches,
        )
        if args.command == "refresh":
            return await _refresh(args, store, deps)
        results = await run_batch(apps, deps, concurrency=args.concurrency, pool=pool or None)

    failures = 0
    for app, result in zip(apps, results):
        if isinstance(result, Exception):
            failures += 1
            print(f"FAILED  {app.name}: {type(result).__name__}: {result}")
        else:
            flag = "REVIEW" if result.needs_human_review else "OK    "
            usage = result.usage
            print(
                f"{flag}  {app.name}: {result.verdict.status} / auth {result.auth.primary} / access {result.access.level}"
                f" / attempts {result.attempts} / {usage.input_tokens + usage.output_tokens:,} tokens"
                f" / {usage.composio_calls} Composio calls (${usage.composio_usd:.3f})"
            )
    cap = f" of ${spend.limit_usd:.2f} cap" if spend.limit_usd is not None else ""
    print(f"\nComposio spend this run: ${spend.spent_usd:.3f}{cap}")
    return 1 if failures else 0


async def _refresh(args: argparse.Namespace, store: Store, deps: Deps) -> int:
    """Recheck the Composio catalog for finished apps (free), and with --rejudge rerun the critic on their
    stored quotes. Nothing is researched again."""
    changed = 0
    for app in store.apps(args.batch):
        if args.only and app.id not in args.only:
            continue
        before = store.load_record(app.id)
        rejudge = args.rejudge and before is not None and (before.needs_human_review or args.all)
        after = await refresh_app(app, deps, rejudge=rejudge, reassess=args.reassess_access)
        if after is None:
            continue
        was = (before.in_composio_catalog, before.needs_human_review, before.access.level, before.verdict.status)
        now = (after.in_composio_catalog, after.needs_human_review, after.access.level, after.verdict.status)
        if was != now:
            changed += 1
            print(
                f"{app.name}: in catalog {was[0]} -> {now[0]}, needs review {was[1]} -> {now[1]}, "
                f"access {was[2]} -> {now[2]}, verdict {was[3]} -> {now[3]}"
            )
    print(f"\n{changed} records changed")
    return 0


def _status(store: Store) -> int:
    for app in store.apps():
        record = store.load_record(app.id)
        state = store.load_state(app.id)
        if record:
            line = f"done ({record.verdict.status}{', needs review' if record.needs_human_review else ''})"
        elif state and state.last_error:
            line = f"failed: {state.last_error}"
        elif state:
            line = "in progress (checkpoint saved)"
        else:
            line = "not started"
        print(f"batch {app.batch}  {app.name:<20} {line}")
    return 0


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(override=True)  # the project's .env wins over whatever the shell happens to export
    parser = argparse.ArgumentParser(prog="appscout", description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"), help="data directory (default: ./data)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="show every app's progress")
    run = commands.add_parser("run", help="research apps that have no record yet")
    run.add_argument("--batch", type=int, help="only this batch number")
    run.add_argument("--only", nargs="+", help="only these app ids")
    run.add_argument("--force", action="store_true", help="redo apps that already have a record")
    run.add_argument("--concurrency", type=int, default=4, help="apps researched at once (default 4)")
    run.add_argument("--max-spend", type=float, default=0.50, help="Composio dollar cap for this run (default 0.50)")
    run.add_argument("--paid-calls", type=int, default=4, help="paid Composio calls per app, $0.004 each (default 4 = $0.016)")
    run.add_argument("--searches", type=int, default=2, help="TAVILY_SEARCH calls per app, including the mandatory one (default 2)")
    run.add_argument("--model", help="researcher deployment (default: $APPSCOUT_MODEL)")
    run.add_argument("--critic-model", help="critic deployment (default: $APPSCOUT_CRITIC_MODEL)")
    run.add_argument("--researcher-endpoint", help="env prefix of the researcher's endpoint (default: OPENAI)")
    run.add_argument("--critic-endpoint", help="env prefix of the critic's endpoint (default: OPENAI)")
    run.add_argument(
        "--researchers",
        help="several researcher deployments at once, as model@ENDPOINT:workers,... (default: $APPSCOUT_RESEARCHERS)",
    )
    refresh = commands.add_parser("refresh", help="recheck the Composio catalog for finished apps; no research")
    refresh.add_argument("--rejudge", action="store_true", help="also rerun the critic on records flagged for review")
    refresh.add_argument("--all", action="store_true", help="with --rejudge: rerun the critic on every record")
    refresh.add_argument(
        "--reassess-access",
        action="store_true",
        help="re-read unknown access levels from the quotes already verified, and fill in unknown verdicts",
    )
    refresh.add_argument("--batch", type=int, help="only this batch number")
    refresh.add_argument("--only", nargs="+", help="only these app ids")
    refresh.add_argument("--model", help="deployment that re-reads access (default: $APPSCOUT_MODEL)")
    refresh.add_argument("--critic-model", help="critic deployment for --rejudge (default: $APPSCOUT_CRITIC_MODEL)")
    refresh.add_argument("--critic-endpoint", help="env prefix of the critic's endpoint (default: OPENAI)")
    # A refresh never researches, so it gets no paid Composio budget and no researcher pool.
    refresh.set_defaults(
        force=False, max_spend=0.0, concurrency=3, paid_calls=4, searches=2, researchers=None, researcher_endpoint=None
    )
    args = parser.parse_args()

    store = Store(args.data)
    code = _status(store) if args.command == "status" else asyncio.run(_run(args, store))
    sys.exit(code)
