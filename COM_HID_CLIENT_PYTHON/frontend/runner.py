import threading
import time

from serial_module import CursorController
from .models import RunResult, MacroStep


class MacroRunner:
    def __init__(self, app, serial_manager, yolo_detector):
        self.app = app
        self.serial_manager = serial_manager
        self.yolo_detector = yolo_detector
        self.thread = None
        self.stop_flag = threading.Event()
        self.running = False
        self.stop_on_no_detection = False

    def start(self, steps, cycles: int):
        if self.running:
            raise RuntimeError("Макрос уже выполняется")
        self.stop_flag.clear()
        self.thread = threading.Thread(target=self._run, args=(steps, cycles), daemon=True)
        self.running = True
        self.thread.start()

    def stop(self):
        self.stop_flag.set()

    def _parse_xy(self, parts, command: str):
        if len(parts) != 3:
            raise RuntimeError(f"Неверный формат {command}. Нужно: {parts[0]} X Y")
        try:
            return int(parts[1]), int(parts[2])
        except ValueError as exc:
            raise RuntimeError(f"Координаты должны быть целыми числами: {command}") from exc

    def _parse_region_tail(self, parts, min_len_without_region: int):
        if len(parts) == min_len_without_region:
            return None
        if len(parts) == min_len_without_region + 4:
            try:
                return (int(parts[-4]), int(parts[-3]), int(parts[-2]), int(parts[-1]))
            except ValueError as exc:
                raise RuntimeError("Координаты области должны быть целыми числами") from exc
        raise RuntimeError("Неверный формат области. Нужно: x1 y1 x2 y2")

    def _format_move_result(self, command: str, result: dict) -> str:
        return (
            f">> {command} | start={result['start']} target={result['target']} "
            f"end={result['end']} | steps={result['commands_sent']} | << {result['last_response']}"
        )

    def _detect_target(self, target_class: str, mode: str = "best", region=None):
        if mode == "best":
            det = self.yolo_detector.find_best(target_class, region=region)
        elif mode == "nearest_screen":
            det = self.yolo_detector.find_nearest_to_screen_center(target_class, region=region)
        elif mode == "nearest_cursor":
            det = self.yolo_detector.find_nearest_to_cursor(target_class, region=region)
        elif mode == "largest":
            det = self.yolo_detector.find_largest(target_class, region=region)
        else:
            raise RuntimeError(f"Неизвестный режим детекта: {mode}")
        if det is None:
            return None
        return det

    def _execute_detect(self, verb: str, parts):
        region = None
        if verb in ("DETECT_MOVE", "DETECT_CLICK", "DETECT_DOUBLE_CLICK", "DETECT_NEAREST_CURSOR", "DETECT_NEAREST_SCREEN"):
            region = self._parse_region_tail(parts, 2) if len(parts) != 2 else None
            target_class = parts[1]
        elif verb in ("DETECT_MOVE_OFFSET", "DETECT_CLICK_OFFSET"):
            target_class = parts[1]
            dx = int(parts[2])
            dy = int(parts[3])
            region = self._parse_region_tail(parts, 4) if len(parts) != 4 else None
        else:
            target_class = ""

        if verb == "DETECT_LIST":
            region = self._parse_region_tail(parts, 1) if len(parts) != 1 else None
            detections = self.yolo_detector.detect(region=region)
            if not detections:
                return RunResult.NO_DETECTION, f">> DETECT_LIST | region={region} | << ничего не найдено"
            preview = ", ".join(f"{d.class_name}:{d.confidence:.2f}@{d.center}" for d in detections[:25])
            return RunResult.COMPLETED, f">> DETECT_LIST | count={len(detections)} | region={region} | << {preview}"

        if verb == "DETECT_MOVE":
            det = self._detect_target(target_class, "best", region)
            if det is None:
                return RunResult.NO_DETECTION, f">> DETECT_MOVE {target_class} | region={region} | << NOT_FOUND"
            result = CursorController.move_to(self.serial_manager, *det.center)
            return RunResult.COMPLETED, f">> DETECT_MOVE {target_class} | bbox=({det.x1},{det.y1},{det.x2},{det.y2}) | conf={det.confidence:.2f} | center={det.center} | region={region} | << {result['last_response']}"

        if verb == "DETECT_CLICK":
            det = self._detect_target(target_class, "best", region)
            if det is None:
                return RunResult.NO_DETECTION, f">> DETECT_CLICK {target_class} | region={region} | << NOT_FOUND"
            CursorController.move_to(self.serial_manager, *det.center)
            CursorController.left_click(self.serial_manager)
            return RunResult.COMPLETED, f">> DETECT_CLICK {target_class} | bbox=({det.x1},{det.y1},{det.x2},{det.y2}) | conf={det.confidence:.2f} | center={det.center} | region={region} | << CLICK"

        if verb == "DETECT_DOUBLE_CLICK":
            det = self._detect_target(target_class, "best", region)
            if det is None:
                return RunResult.NO_DETECTION, f">> DETECT_DOUBLE_CLICK {target_class} | region={region} | << NOT_FOUND"
            CursorController.move_to(self.serial_manager, *det.center)
            CursorController.double_click(self.serial_manager)
            return RunResult.COMPLETED, f">> DETECT_DOUBLE_CLICK {target_class} | bbox=({det.x1},{det.y1},{det.x2},{det.y2}) | conf={det.confidence:.2f} | center={det.center} | region={region} | << DOUBLE_CLICK"

        if verb == "DETECT_NEAREST_CURSOR":
            det = self._detect_target(target_class, "nearest_cursor", region)
            if det is None:
                return RunResult.NO_DETECTION, f">> DETECT_NEAREST_CURSOR {target_class} | region={region} | << NOT_FOUND"
            result = CursorController.move_to(self.serial_manager, *det.center)
            return RunResult.COMPLETED, f">> DETECT_NEAREST_CURSOR {target_class} | bbox=({det.x1},{det.y1},{det.x2},{det.y2}) | conf={det.confidence:.2f} | center={det.center} | region={region} | << {result['last_response']}"

        if verb == "DETECT_NEAREST_SCREEN":
            det = self._detect_target(target_class, "nearest_screen", region)
            if det is None:
                return RunResult.NO_DETECTION, f">> DETECT_NEAREST_SCREEN {target_class} | region={region} | << NOT_FOUND"
            result = CursorController.move_to(self.serial_manager, *det.center)
            return RunResult.COMPLETED, f">> DETECT_NEAREST_SCREEN {target_class} | bbox=({det.x1},{det.y1},{det.x2},{det.y2}) | conf={det.confidence:.2f} | center={det.center} | region={region} | << {result['last_response']}"

        if verb == "DETECT_MOVE_OFFSET":
            det = self._detect_target(target_class, "best", region)
            if det is None:
                return RunResult.NO_DETECTION, f">> DETECT_MOVE_OFFSET {target_class} | region={region} | << NOT_FOUND"
            tx, ty = det.center[0] + dx, det.center[1] + dy
            result = CursorController.move_to(self.serial_manager, tx, ty)
            return RunResult.COMPLETED, f">> DETECT_MOVE_OFFSET {target_class} {dx} {dy} | center={det.center} | target=({tx}, {ty}) | conf={det.confidence:.2f} | region={region} | << {result['last_response']}"

        if verb == "DETECT_CLICK_OFFSET":
            det = self._detect_target(target_class, "best", region)
            if det is None:
                return RunResult.NO_DETECTION, f">> DETECT_CLICK_OFFSET {target_class} | region={region} | << NOT_FOUND"
            tx, ty = det.center[0] + dx, det.center[1] + dy
            CursorController.move_to(self.serial_manager, tx, ty)
            CursorController.left_click(self.serial_manager)
            return RunResult.COMPLETED, f">> DETECT_CLICK_OFFSET {target_class} {dx} {dy} | center={det.center} | target=({tx}, {ty}) | conf={det.confidence:.2f} | region={region} | << CLICK"

        raise RuntimeError(f"Неизвестная detect-команда: {verb}")

    def execute_step(self, step: MacroStep):
        command = step.command.strip()
        if not command:
            return RunResult.COMPLETED, ">> (пустой шаг)"

        parts = command.split()
        verb = parts[0].upper()

        if verb == "MOVE_TO":
            x, y = self._parse_xy(parts, command)
            result = CursorController.move_to(self.serial_manager, x, y)
            return RunResult.COMPLETED, self._format_move_result(command, result)

        if verb == "MOUSE_CLICK":
            button = parts[1].upper()
            if button == "LEFT":
                CursorController.left_click(self.serial_manager)
            elif button == "RIGHT":
                CursorController.right_click(self.serial_manager)
            else:
                raise RuntimeError("Поддержаны только LEFT и RIGHT")
            return RunResult.COMPLETED, f">> {command} | << OK"

        if verb == "MOUSE_PRESS":
            button = parts[1].upper()
            if button == "LEFT":
                CursorController.left_press(self.serial_manager)
            elif button == "RIGHT":
                CursorController.right_press(self.serial_manager)
            else:
                raise RuntimeError("Поддержаны только LEFT и RIGHT")
            return RunResult.COMPLETED, f">> {command} | << OK"

        if verb == "MOUSE_RELEASE":
            button = parts[1].upper()
            if button == "LEFT":
                CursorController.left_release(self.serial_manager)
            elif button == "RIGHT":
                CursorController.right_release(self.serial_manager)
            else:
                raise RuntimeError("Поддержаны только LEFT и RIGHT")
            return RunResult.COMPLETED, f">> {command} | << OK"

        if verb.startswith("DETECT_"):
            return self._execute_detect(verb, parts)

        response = self.serial_manager.send_command(command, expect_response=step.expect_response)
        message = f">> {command}"
        if step.expect_response:
            message += f" | << {response or '(пусто)'}"
        return RunResult.COMPLETED, message

    def _run(self, steps, cycles: int):
        try:
            total_steps = len(steps) * cycles if cycles > 0 else 0
            done = 0

            for cycle_index in range(cycles):
                if self.stop_flag.is_set():
                    self.app.on_macro_finished(RunResult.STOPPED)
                    return

                self.app.log(f"=== Цикл {cycle_index + 1}/{cycles} ===")

                for step_index, step in enumerate(steps, start=1):
                    if self.stop_flag.is_set():
                        self.app.on_macro_finished(RunResult.STOPPED)
                        return

                    result, message = self.execute_step(step)
                    self.app.log(f"[{cycle_index + 1}:{step_index}] {message}")
                    if result == RunResult.NO_DETECTION and self.stop_on_no_detection:
                        self.app.log("[MACRO] Детект не найден. Текущий скрипт остановлен по настройке.")
                        self.app.on_macro_finished(RunResult.NO_DETECTION)
                        return

                    done += 1
                    self.app.set_progress(done, total_steps)

                    if step.delay_ms > 0:
                        end_time = time.time() + (step.delay_ms / 1000.0)
                        while time.time() < end_time:
                            if self.stop_flag.is_set():
                                self.app.on_macro_finished(RunResult.STOPPED)
                                return
                            time.sleep(0.02)

            self.app.on_macro_finished(RunResult.COMPLETED)

        except Exception as exc:
            self.app.log(f"[ОШИБКА] {exc}")
            self.app.safe_messagebox("Ошибка", str(exc), error=True)
            self.app.on_macro_finished(RunResult.ERROR)
        finally:
            self.running = False
