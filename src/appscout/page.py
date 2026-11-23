"""Build the single-page case study (index.html) and the flat exports from data/results.jsonl.

The page computes every number it shows from the dataset embedded in it, so the patterns
cannot drift from the table. Run it as often as you like while a batch is in progress.
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TEMPLATE = Path(__file__).with_name("page_template.html")
DATASET_SLOT = "__DATASET_JSON__"
FOUND = ("exact", "exact_rendered")

FLAT_FIELDS = [
    "app_name",
    "category",
    "one_line_summary",
    "auth_methods",
    "primary_auth",
    "access_tier",
    "deployment_model",
    "api_surface",
    "endpoint_breadth",
    "existing_mcp",
    "mcp_maturity",
    "mcp_url",
    "in_composio_catalog",
    "composio_toolkit_slug",
    "buildability_verdict",
    "primary_blocker",
    "evidence_urls",
    "quotes_verified",
    "quotes_total",
    "confidence_score",
    "needs_human_review",
    "verification_notes",
]


def load_records(data_dir: Path) -> list[dict]:
    path = data_dir / "results.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_apps(data_dir: Path) -> list[dict]:
    with (data_dir / "apps.csv").open(newline="", encoding="utf-8") as handle:
        return [
            {"id": row["id"], "name": row["name"], "category": row["category"], "batch": int(row["batch"])}
            for row in csv.DictReader(handle)
        ]


def _load_optional(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def buildability(record: dict) -> str:
    """The user's verdict names, derived from verdict.status and verdict.main_blocker."""
    status = record["verdict"]["status"]
    blocker = record["verdict"]["main_blocker"]
    if status == "buildable_now":
        return "Ready_Now"
    if status == "buildable_with_caveats":
        return "Conditional"
    if status == "blocked":
        return "Blocked_No_Public_API" if blocker in ("no_public_api", "narrow_api") else "Blocked_Partner_Gated"
    return "Unknown"


def confidence(record: dict) -> float:
    """Share of the record's checked fields that the verification step marked supported. Not model-reported."""
    results = [item["result"] for item in record.get("verification", [])]
    return round(results.count("supported") / len(results), 2) if results else 0.0


def flat_row(record: dict) -> dict:
    evidence = record.get("evidence", [])
    verified = [item for item in evidence if item.get("check") in FOUND]
    mcp = record["mcp"]
    return {
        "app_name": record["name"],
        "category": record["category"],
        "one_line_summary": record["one_liner"],
        "auth_methods": record["auth"]["methods"],
        "primary_auth": record["auth"]["primary"],
        "access_tier": record["access"]["level"],
        "deployment_model": record.get("deployment_model", "unknown"),
        "api_surface": record["api"]["styles"],
        "endpoint_breadth": record["api"]["breadth"],
        "existing_mcp": mcp["status"] != "none_found",
        "mcp_maturity": mcp.get("maturity", "unknown"),
        "mcp_url": mcp.get("url", ""),
        "in_composio_catalog": bool(record.get("in_composio_catalog", False)),
        "composio_toolkit_slug": record.get("composio_toolkit_slug", ""),
        "buildability_verdict": buildability(record),
        "primary_blocker": record["verdict"]["main_blocker"],
        "evidence_urls": list(dict.fromkeys(item["url"] for item in verified)),
        "quotes_verified": len(verified),
        "quotes_total": len(evidence),
        "confidence_score": confidence(record),
        "needs_human_review": bool(record.get("needs_human_review", False)),
        "verification_notes": record.get("review_reasons", []),
    }


def build_dataset(data_dir: Path, repo_url: str | None, generated_at: str) -> dict:
    records = load_records(data_dir)
    return {
        "generated_at": generated_at,
        "repo_url": repo_url,
        "apps": load_apps(data_dir),
        "records": records,
        "flat": [flat_row(record) for record in records],
        "flat_fields": FLAT_FIELDS,
        "process_notes": _load_optional(data_dir / "process_notes.json"),
        "audit": _load_optional(data_dir / "audit.json"),
        "pass1": _load_optional(data_dir / "pass1_results.json"),
    }


def render(dataset: dict) -> str:
    # "<" is escaped so no value in the data can close the script element or open a comment.
    payload = json.dumps(dataset, ensure_ascii=False).replace("<", "\\u003c")
    return TEMPLATE.read_text(encoding="utf-8").replace(DATASET_SLOT, payload)


def _csv_cell(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


def write_flat_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(FLAT_FIELDS)
        writer.writerows([_csv_cell(row[field]) for field in FLAT_FIELDS] for row in rows)


def build(data_dir: Path, out: Path, repo_url: str | None = None, generated_at: str | None = None) -> dict:
    """Write index.html, data/apps.json and data/apps_flat.csv. Returns the dataset that was embedded."""
    generated_at = generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    dataset = build_dataset(data_dir, repo_url, generated_at)
    out.write_text(render(dataset), encoding="utf-8")
    (data_dir / "apps.json").write_text(json.dumps(dataset["records"], indent=2, ensure_ascii=False), encoding="utf-8")
    write_flat_csv(data_dir / "apps_flat.csv", dataset["flat"])
    return dataset


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="appscout.page", description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"), help="data directory (default: ./data)")
    parser.add_argument("--out", type=Path, default=Path("index.html"), help="output file (default: ./index.html)")
    parser.add_argument("--repo-url", help="public repository URL to show in the Proof section")
    args = parser.parse_args()
    dataset = build(args.data, args.out, args.repo_url)
    print(f"{args.out}: {len(dataset['records'])} of {len(dataset['apps'])} apps researched")


if __name__ == "__main__":
    main()
