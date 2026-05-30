from .models import MacroStep

ACTION_DEFS = {
    "DETECT_MOVE": "Найти объект и навести курсор в центр bbox.",
    "DETECT_CLICK": "Найти объект, навести курсор и кликнуть.",
    "DETECT_DOUBLE_CLICK": "Найти объект, навести курсор и сделать двойной клик.",
    "DETECT_NEAREST_CURSOR": "Среди объектов класса выбрать тот, что ближе к курсору.",
    "DETECT_NEAREST_SCREEN": "Среди объектов класса выбрать тот, что ближе к центру экрана или области.",
    "DETECT_MOVE_OFFSET": "Найти объект и навести курсор со смещением dx/dy от центра.",
    "DETECT_CLICK_OFFSET": "Найти объект и кликнуть со смещением dx/dy от центра.",
    "DETECT_LIST": "Показать найденные объекты в журнале.",
}

CURSOR_ACTION_DEFS = {
    "MOVE_TO": "Навести курсор на абсолютные координаты X/Y.",
    "MOUSE_CLICK LEFT": "Клик левой кнопкой.",
    "MOUSE_CLICK RIGHT": "Клик правой кнопкой.",
    "MOUSE_PRESS LEFT": "Удерживать левую кнопку.",
    "MOUSE_RELEASE LEFT": "Отпустить левую кнопку.",
    "MOUSE_PRESS RIGHT": "Удерживать правую кнопку.",
    "MOUSE_RELEASE RIGHT": "Отпустить правую кнопку.",
}


def parse_region_from_ui(x1, y1, x2, y2):
    values = [x1.strip(), y1.strip(), x2.strip(), y2.strip()]
    if not any(values):
        return None
    if not all(values):
        raise RuntimeError("Для области детекции нужно заполнить все 4 координаты: X1 Y1 X2 Y2")
    try:
        return tuple(int(v) for v in values)
    except ValueError as exc:
        raise RuntimeError("Координаты области должны быть целыми числами") from exc


def parse_offset_from_ui(dx, dy):
    try:
        return int(dx.strip() or "0"), int(dy.strip() or "0")
    except ValueError as exc:
        raise RuntimeError("dx и dy должны быть целыми числами") from exc


def build_yolo_command_from_ui(action, target, region, dxdy):
    action = action.strip()
    target = target.strip()

    if action != "DETECT_LIST" and not target:
        raise RuntimeError("Выбери или введи класс объекта")

    if action in ("DETECT_MOVE_OFFSET", "DETECT_CLICK_OFFSET"):
        dx, dy = dxdy
        parts = [action, target, str(dx), str(dy)]
    elif action == "DETECT_LIST":
        parts = [action]
    else:
        parts = [action, target]

    if region is not None:
        parts.extend(str(v) for v in region)

    return " ".join(parts)


def build_cursor_command_from_ui(action, x_text, y_text):
    action = action.strip()
    if action == "MOVE_TO":
        if not x_text.strip() or not y_text.strip():
            raise RuntimeError("Для MOVE_TO нужны X и Y")
        try:
            x = int(x_text.strip())
            y = int(y_text.strip())
        except ValueError as exc:
            raise RuntimeError("X и Y должны быть целыми числами") from exc
        return f"MOVE_TO {x} {y}"
    return action


def make_macro_step(command: str, delay_ms: int = 120):
    return MacroStep(command=command, delay_ms=delay_ms, expect_response=False)
