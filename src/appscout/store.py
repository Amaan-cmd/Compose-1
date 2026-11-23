"""Files under data/: the app list, per-app checkpoints, and finished records."""

import csv
import json
import os
import time
from pathlib import Path

from .schema import App, Record, RunState


def _write_atomic(path: Path, text: str) -> None:
    """Write through a temporary file and rename, so a crash or kill never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    for attempt in range(5):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            # A sync client (OneDrive) can hold the target open for a moment on Windows.
            if attempt == 4:
                raise
            time.sleep(0.2 * (attempt + 1))


class Store:
    def __init__(self, root: Path):
        self.apps_file = root / "apps.csv"
        self.results_file = root / "results.jsonl"
        self.state_dir = root / "state"
        self.records_dir = root / "records"

    def apps(self, batch: int | None = None) -> list[App]:
        with self.apps_file.open(newline="", encoding="utf-8") as handle:
            apps = [App(**row) for row in csv.DictReader(handle)]
        return [app for app in apps if batch is None or app.batch == batch]

    def load_state(self, app_id: str) -> RunState | None:
        path = self.state_dir / f"{app_id}.json"
        if not path.exists():
            return None
        return RunState.model_validate_json(path.read_text(encoding="utf-8"))

    def save_state(self, app_id: str, state: RunState) -> None:
        _write_atomic(self.state_dir / f"{app_id}.json", state.model_dump_json(indent=2))

    def clear(self, app_id: str) -> None:
        """Forget an app's checkpoint and record so the next run starts it from scratch."""
        (self.state_dir / f"{app_id}.json").unlink(missing_ok=True)
        (self.records_dir / f"{app_id}.json").unlink(missing_ok=True)
        self._rebuild_results()

    def load_record(self, app_id: str) -> Record | None:
        path = self.records_dir / f"{app_id}.json"
        if not path.exists():
            return None
        return Record.model_validate_json(path.read_text(encoding="utf-8"))

    def save_record(self, record: Record) -> None:
        _write_atomic(self.records_dir / f"{record.id}.json", record.model_dump_json(indent=2))
        self._rebuild_results()

    def _rebuild_results(self) -> None:
        """results.jsonl: one line per finished app, in app-list order, rewritten atomically after every app."""
        lines = []
        for app in self.apps():
            path = self.records_dir / f"{app.id}.json"
            if path.exists():
                lines.append(json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False))
        _write_atomic(self.results_file, "".join(line + "\n" for line in lines))
