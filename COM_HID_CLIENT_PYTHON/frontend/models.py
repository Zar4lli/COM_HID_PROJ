from dataclasses import dataclass

APP_TITLE = "HID COM Macro GUI + YOLO"
APP_VERSION = "9.0"
DEFAULT_STEP_DELAY_MS = 120


@dataclass
class MacroStep:
    command: str
    delay_ms: int = DEFAULT_STEP_DELAY_MS
    expect_response: bool = True


class RunResult:
    COMPLETED = "completed"
    NO_DETECTION = "no_detection"
    STOPPED = "stopped"
    ERROR = "error"
