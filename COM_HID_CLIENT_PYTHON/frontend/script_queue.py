import json
import os
from typing import List, Optional

from .models import MacroStep


class ScriptQueueManager:
    def __init__(self):
        self.folder_path: str = ""
        self.files: List[str] = []
        self.index: int = -1
        self.folder_cycles: int = 1
        self.current_cycle: int = 0
        self.enabled: bool = False
        self.auto_run_next: bool = False

    def load_folder(self, folder_path: str):
        self.folder_path = folder_path
        self.files = sorted(
            os.path.join(folder_path, name)
            for name in os.listdir(folder_path)
            if name.lower().endswith(".json")
        )
        self.index = 0 if self.files else -1
        self.current_cycle = 0

    def has_scripts(self) -> bool:
        return bool(self.files)

    def current_file(self) -> Optional[str]:
        if self.index < 0 or self.index >= len(self.files):
            return None
        return self.files[self.index]

    def next_file(self) -> Optional[str]:
        if not self.files:
            return None
        self.index += 1
        if self.index >= len(self.files):
            self.index = 0
            self.current_cycle += 1
            if self.current_cycle >= self.folder_cycles:
                return None
        return self.current_file()

    def reset_run(self):
        if self.files:
            self.index = 0
        else:
            self.index = -1
        self.current_cycle = 0

    def load_steps_from_file(self, path: str) -> List[MacroStep]:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        steps_raw = data.get("steps", data)
        return [
            MacroStep(
                command=item["command"],
                delay_ms=int(item.get("delay_ms", 120)),
                expect_response=bool(item.get("expect_response", True)),
            )
            for item in steps_raw
        ]
