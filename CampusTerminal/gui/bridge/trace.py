# SPDX-License-Identifier: GPL-3.0-or-later
import json
from datetime import datetime, timezone


def emit(stage, **detail):
    try:
        from gui.bridge.store import APP_DIR
        APP_DIR.mkdir(parents=True, exist_ok=True)
        row = {"at": datetime.now(timezone.utc).isoformat(), "stage": stage}
        row.update(detail)
        with (APP_DIR / "gui-events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass
