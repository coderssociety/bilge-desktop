"""A record of what the assistant did, kept on the user's machine only, for looking back at what happened."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

# Results can hold page text or e-mail; only the start is kept.
MAX_RESULT_CHARACTERS = 300


class ActionLog:
    def __init__(self, path: Path):
        self.path = path

    def record(self, tool: str, arguments: dict[str, Any], decision: str, result: str) -> None:
        entry = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "tool": tool,
            "arguments": {key: str(value)[:MAX_RESULT_CHARACTERS] for key, value in arguments.items()},
            "decision": decision,
            "result": result[:MAX_RESULT_CHARACTERS],
        }
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Created private from the start; os.open applies the mode only when it creates the file.
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
