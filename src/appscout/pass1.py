"""Export what the first research attempt of every app looked like, before any repair, re-read or correction.

`uv run python -m appscout.pass1` reads the checkpoints in data/state (git-ignored) and writes
data/pass1_results.json, which the page uses for its accuracy progression.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from .store import Store


def first_attempts(store: Store) -> list[dict]:
    rows = []
    for app in store.apps():
        state = store.load_state(app.id)
        if state is None or not state.attempts or state.attempts[0].verification is None:
            continue
        first = state.attempts[0]
        rows.append(
            {
                "id": app.id,
                "name": app.name,
                "attempts": len(state.attempts),
                "quote_checks": dict(Counter(str(check) for check in first.checks)),
                "fields": {item.field: str(item.result) for item in first.verification},
                "access": str(first.finding.access.level),
                "verdict": str(first.finding.verdict.status),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    args = parser.parse_args()
    rows = first_attempts(Store(args.data))
    note = (
        "First research attempt of each app. For records whose only attempt was later re-judged with the "
        "recalibrated checker, the field results here are the re-judged ones, so this stage is slightly flattered."
    )
    (args.data / "pass1_results.json").write_text(json.dumps({"note": note, "apps": rows}, indent=2), encoding="utf-8")
    print(f"pass1_results.json: {len(rows)} apps")


if __name__ == "__main__":
    main()
