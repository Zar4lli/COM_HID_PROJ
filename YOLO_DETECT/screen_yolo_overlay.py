import os
import sys
import time
import json
import queue
import threading
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional

import cv2
import mss
import numpy as np
import keyboard
from ultralytics import YOLO

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# =========================
# КОНФИГ
# =========================

CONFIG_FILE = "yolo_screen_gui_config.json"


@dataclass
class AppConfig:
    model_path: str = "yolov8n.pt"
    confidence: float = 0.35
    capture_width: int = 960
    process_every_n_frame: int = 1
    monitor_index: int = 1
    save_screenshots: bool = False
    screenshot_dir: str = "detections"
    screenshot_cooldown_sec: float = 1.0
    stop_hotkey: str = "ctrl+shift+q"
    show_labels: bool = True
    line_thickness: int = 3


def load_config() -> AppConfig:
    if not os.path.exists(CONFIG_FILE):
        return AppConfig()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return AppConfig(**data)
    except Exception:
        return AppConfig()


def save_config(cfg: AppConfig) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(asdict(cfg), f, ensure_ascii=False, indent=2)


# =========================
# OVERLAY
# =========================

class OverlayWindow(tk.Toplevel):
    def __init__(self, master, geometry: dict, show_labels: bool = True, line_thickness: int = 3):
        super().__init__(master)
        self.geometry_info = geometry
        self.show_labels = show_labels
        self.line_thickness = line_thickness

        self.left = geometry["left"]
        self.top = geometry["top"]
        self.width = geometry["width"]
        self.height = geometry["height"]

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.config(bg="magenta")

        # Прозрачный цвет для tkinter overlay на Windows
        try:
            self.wm_attributes("-transparentcolor", "magenta")
        except Exception:
            pass

        self.geometry(f"{self.width}x{self.height}+{self.left}+{self.top}")

        self.canvas = tk.Canvas(self, width=self.width, height=self.height, bg="magenta", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.detections: List[Tuple[int, int, int, int, str, float]] = []

        # попытка сделать "прозрачным для мыши" не всегда работает из tkinter
        # GUI остается отдельным окном, клики поверх него могут блокироваться
        # для настоящего click-through лучше делать через WinAPI/PySide6/pywin32

    def set_detections(self, detections: List[Tuple[int, int, int, int, str, float]]) -> None:
        self.detections = detections
        self.redraw()

    def clear_detections(self) -> None:
        self.detections = []
        self.redraw()

    def redraw(self) -> None:
        self.canvas.delete("all")

        for x1, y1, x2, y2, label, conf in self.detections:
            rx1 = x1 - self.left
            ry1 = y1 - self.top
            rx2 = x2 - self.left
            ry2 = y2 - self.top

            self.canvas.create_rectangle(
                rx1, ry1, rx2, ry2,
                outline="lime",
                width=self.line_thickness
            )

            if self.show_labels:
                text = f"{label} {conf:.2f}"
                text_x = rx1
                text_y = max(20, ry1 - 10)

                rect_id = self.canvas.create_rectangle(
                    text_x,
                    text_y - 18,
                    text_x + max(110, len(text) * 8),
                    text_y + 2,
                    fill="lime",
                    outline="lime"
                )
                self.canvas.create_text(
                    text_x + 5,
                    text_y - 8,
                    text=text,
                    anchor="w",
                    fill="black",
                    font=("Arial", 10, "bold")
                )


# =========================
# ДЕТЕКТОР
# =========================

class DetectionEngine:
    def __init__(self, ui_queue: queue.Queue):
        self.ui_queue = ui_queue
        self.worker_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.running = False
        self.hotkey_registered = False
        self.hotkey_handle = None
        self.last_screenshot_time = 0.0

    def start(self, cfg: AppConfig) -> None:
        if self.running:
            return

        if not os.path.exists(cfg.model_path):
            raise FileNotFoundError(f"Модель не найдена: {cfg.model_path}")

        if cfg.save_screenshots:
            os.makedirs(cfg.screenshot_dir, exist_ok=True)

        self.stop_event.clear()
        self.running = True
        self.last_screenshot_time = 0.0

        self.worker_thread = threading.Thread(
            target=self._run_detection_loop,
            args=(cfg,),
            daemon=True
        )
        self.worker_thread.start()

        self._register_hotkey(cfg.stop_hotkey)

    def stop(self) -> None:
        if not self.running:
            return

        self.stop_event.set()
        self.running = False
        self._unregister_hotkey()
        self.ui_queue.put(("stopped", None))

    def _register_hotkey(self, hotkey: str) -> None:
        self._unregister_hotkey()
        try:
            self.hotkey_handle = keyboard.add_hotkey(hotkey, self.stop)
            self.hotkey_registered = True
        except Exception as e:
            self.hotkey_registered = False
            self.ui_queue.put(("error", f"Не удалось зарегистрировать hotkey '{hotkey}': {e}"))

    def _unregister_hotkey(self) -> None:
        try:
            if self.hotkey_handle is not None:
                keyboard.remove_hotkey(self.hotkey_handle)
        except Exception:
            pass
        self.hotkey_registered = False
        self.hotkey_handle = None

    def _save_detection_screenshot(self, image_bgr: np.ndarray, detections, save_dir: str) -> None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"detection_{timestamp}_{int(time.time() * 1000) % 1000:03d}.jpg"
        path = os.path.join(save_dir, filename)

        img = image_bgr.copy()
        for x1, y1, x2, y2, label, conf in detections:
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(
                img,
                f"{label} {conf:.2f}",
                (x1, max(20, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2,
                cv2.LINE_AA
            )

        cv2.imwrite(path, img)
        self.ui_queue.put(("screenshot_saved", path))

    def _run_detection_loop(self, cfg: AppConfig) -> None:
        try:
            model = YOLO(cfg.model_path)
            sct = mss.mss()

            if cfg.monitor_index < 1 or cfg.monitor_index >= len(sct.monitors):
                raise ValueError(
                    f"Неверный monitor_index={cfg.monitor_index}. Доступно мониторов: {len(sct.monitors) - 1}"
                )

            monitor = sct.monitors[cfg.monitor_index]

            self.ui_queue.put(("overlay_create", {
                "geometry": monitor,
                "show_labels": cfg.show_labels,
                "line_thickness": cfg.line_thickness
            }))

            frame_index = 0
            last_fps_time = time.time()
            fps_counter = 0

            while not self.stop_event.is_set():
                frame_index += 1

                if frame_index % max(1, cfg.process_every_n_frame) != 0:
                    time.sleep(0.001)
                    continue

                shot = sct.grab(monitor)
                frame = np.array(shot)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                original_h, original_w = frame.shape[:2]
                input_frame = frame
                scale_x = 1.0
                scale_y = 1.0

                if cfg.capture_width > 0 and original_w > cfg.capture_width:
                    new_w = cfg.capture_width
                    new_h = int(original_h * (new_w / original_w))
                    input_frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
                    scale_x = original_w / new_w
                    scale_y = original_h / new_h

                results = model.predict(
                    source=input_frame,
                    conf=cfg.confidence,
                    verbose=False
                )

                parsed_detections = []

                if results:
                    result = results[0]
                    boxes = result.boxes
                    names = result.names

                    if boxes is not None and len(boxes) > 0:
                        for box in boxes:
                            cls_id = int(box.cls[0].item())
                            conf = float(box.conf[0].item())
                            x1, y1, x2, y2 = box.xyxy[0].tolist()

                            x1 = int(x1 * scale_x) + monitor["left"]
                            y1 = int(y1 * scale_y) + monitor["top"]
                            x2 = int(x2 * scale_x) + monitor["left"]
                            y2 = int(y2 * scale_y) + monitor["top"]

                            label = names.get(cls_id, str(cls_id))
                            parsed_detections.append((x1, y1, x2, y2, label, conf))

                self.ui_queue.put(("detections", parsed_detections))

                if cfg.save_screenshots and parsed_detections:
                    now = time.time()
                    if now - self.last_screenshot_time >= cfg.screenshot_cooldown_sec:
                        self.last_screenshot_time = now
                        self._save_detection_screenshot(
                            frame,
                            [
                                (
                                    int((x1 - monitor["left"])),
                                    int((y1 - monitor["top"])),
                                    int((x2 - monitor["left"])),
                                    int((y2 - monitor["top"])),
                                    label,
                                    conf
                                )
                                for x1, y1, x2, y2, label, conf in parsed_detections
                            ],
                            cfg.screenshot_dir
                        )

                fps_counter += 1
                now = time.time()
                if now - last_fps_time >= 1.0:
                    fps = fps_counter / (now - last_fps_time)
                    fps_counter = 0
                    last_fps_time = now
                    self.ui_queue.put(("fps", round(fps, 2)))

        except Exception as e:
            self.ui_queue.put(("error", str(e)))
        finally:
            self.running = False
            self._unregister_hotkey()
            self.ui_queue.put(("overlay_destroy", None))
            self.ui_queue.put(("stopped", None))


# =========================
# GUI
# =========================

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("YOLO Screen Detection GUI")
        self.root.geometry("760x620")
        self.root.minsize(720, 580)

        self.cfg = load_config()
        self.ui_queue = queue.Queue()
        self.engine = DetectionEngine(self.ui_queue)
        self.overlay: Optional[OverlayWindow] = None

        self.monitor_options = self._get_monitor_options()

        self._build_ui()
        self._load_values_to_ui()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(50, self.process_ui_queue)

    def _get_monitor_options(self):
        options = []
        try:
            with mss.mss() as sct:
                for i, mon in enumerate(sct.monitors):
                    if i == 0:
                        continue
                    text = f"{i}: {mon['width']}x{mon['height']} (left={mon['left']}, top={mon['top']})"
                    options.append((i, text))
        except Exception:
            options = [(1, "1: primary")]
        return options

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        row = 0

        ttk.Label(main, text="YOLO модель (.pt):").grid(row=row, column=0, sticky="w", pady=6)
        self.model_var = tk.StringVar()
        self.model_entry = ttk.Entry(main, textvariable=self.model_var, width=60)
        self.model_entry.grid(row=row, column=1, sticky="ew", pady=6, padx=6)
        ttk.Button(main, text="Выбрать", command=self.choose_model).grid(row=row, column=2, pady=6)
        row += 1

        ttk.Label(main, text="Монитор:").grid(row=row, column=0, sticky="w", pady=6)
        self.monitor_var = tk.StringVar()
        self.monitor_combo = ttk.Combobox(main, textvariable=self.monitor_var, state="readonly", width=50)
        self.monitor_combo["values"] = [text for _, text in self.monitor_options]
        self.monitor_combo.grid(row=row, column=1, sticky="ew", pady=6, padx=6)
        ttk.Button(main, text="Обновить", command=self.refresh_monitors).grid(row=row, column=2, pady=6)
        row += 1

        ttk.Label(main, text="Confidence:").grid(row=row, column=0, sticky="w", pady=6)
        self.conf_var = tk.DoubleVar()
        ttk.Entry(main, textvariable=self.conf_var).grid(row=row, column=1, sticky="ew", pady=6, padx=6)
        row += 1

        ttk.Label(main, text="Ширина кадра для детекции:").grid(row=row, column=0, sticky="w", pady=6)
        self.capture_width_var = tk.IntVar()
        ttk.Entry(main, textvariable=self.capture_width_var).grid(row=row, column=1, sticky="ew", pady=6, padx=6)
        row += 1

        ttk.Label(main, text="Обрабатывать каждый N-й кадр:").grid(row=row, column=0, sticky="w", pady=6)
        self.process_n_var = tk.IntVar()
        ttk.Entry(main, textvariable=self.process_n_var).grid(row=row, column=1, sticky="ew", pady=6, padx=6)
        row += 1

        ttk.Label(main, text="Горячая клавиша остановки:").grid(row=row, column=0, sticky="w", pady=6)
        self.hotkey_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.hotkey_var).grid(row=row, column=1, sticky="ew", pady=6, padx=6)
        ttk.Label(main, text="пример: ctrl+shift+q").grid(row=row, column=2, sticky="w", pady=6)
        row += 1

        self.show_labels_var = tk.BooleanVar()
        ttk.Checkbutton(main, text="Показывать названия классов", variable=self.show_labels_var).grid(
            row=row, column=0, sticky="w", pady=6
        )
        row += 1

        ttk.Label(main, text="Толщина линии:").grid(row=row, column=0, sticky="w", pady=6)
        self.line_thickness_var = tk.IntVar()
        ttk.Entry(main, textvariable=self.line_thickness_var).grid(row=row, column=1, sticky="ew", pady=6, padx=6)
        row += 1

        self.save_shots_var = tk.BooleanVar()
        ttk.Checkbutton(main, text="Сохранять скриншоты при детекции", variable=self.save_shots_var).grid(
            row=row, column=0, sticky="w", pady=6
        )
        row += 1

        ttk.Label(main, text="Папка скриншотов:").grid(row=row, column=0, sticky="w", pady=6)
        self.shot_dir_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.shot_dir_var, width=60).grid(row=row, column=1, sticky="ew", pady=6, padx=6)
        ttk.Button(main, text="Выбрать", command=self.choose_screenshot_dir).grid(row=row, column=2, pady=6)
        row += 1

        ttk.Label(main, text="Кулдаун между скриншотами (сек):").grid(row=row, column=0, sticky="w", pady=6)
        self.shot_cooldown_var = tk.DoubleVar()
        ttk.Entry(main, textvariable=self.shot_cooldown_var).grid(row=row, column=1, sticky="ew", pady=6, padx=6)
        row += 1

        buttons = ttk.Frame(main)
        buttons.grid(row=row, column=0, columnspan=3, sticky="ew", pady=12)

        self.start_btn = ttk.Button(buttons, text="Старт", command=self.start_detection)
        self.start_btn.pack(side="left", padx=5)

        self.stop_btn = ttk.Button(buttons, text="Стоп", command=self.stop_detection)
        self.stop_btn.pack(side="left", padx=5)

        self.save_btn = ttk.Button(buttons, text="Сохранить настройки", command=self.save_settings)
        self.save_btn.pack(side="left", padx=5)

        row += 1

        status_frame = ttk.LabelFrame(main, text="Статус", padding=10)
        status_frame.grid(row=row, column=0, columnspan=3, sticky="nsew", pady=10)

        self.status_var = tk.StringVar(value="Готово")
        self.fps_var = tk.StringVar(value="FPS: -")
        self.last_shot_var = tk.StringVar(value="Последний скриншот: -")

        ttk.Label(status_frame, textvariable=self.status_var).pack(anchor="w")
        ttk.Label(status_frame, textvariable=self.fps_var).pack(anchor="w", pady=4)
        ttk.Label(status_frame, textvariable=self.last_shot_var, wraplength=680).pack(anchor="w", pady=4)

        help_frame = ttk.LabelFrame(main, text="Подсказки", padding=10)
        help_frame.grid(row=row + 1, column=0, columnspan=3, sticky="nsew", pady=10)

        help_text = (
            "1. Выбери модель .pt\n"
            "2. Выбери монитор\n"
            "3. Настрой hotkey остановки\n"
            "4. При необходимости включи скриншоты и выбери папку\n"
            "5. Нажми Старт\n\n"
            "Замечание: библиотека keyboard на Windows иногда требует запуск от имени администратора."
        )
        ttk.Label(help_frame, text=help_text, justify="left").pack(anchor="w")

        main.columnconfigure(1, weight=1)

    def _load_values_to_ui(self):
        self.model_var.set(self.cfg.model_path)
        self.conf_var.set(self.cfg.confidence)
        self.capture_width_var.set(self.cfg.capture_width)
        self.process_n_var.set(self.cfg.process_every_n_frame)
        self.hotkey_var.set(self.cfg.stop_hotkey)
        self.save_shots_var.set(self.cfg.save_screenshots)
        self.shot_dir_var.set(self.cfg.screenshot_dir)
        self.shot_cooldown_var.set(self.cfg.screenshot_cooldown_sec)
        self.show_labels_var.set(self.cfg.show_labels)
        self.line_thickness_var.set(self.cfg.line_thickness)

        idx = 0
        for i, (mon_index, _) in enumerate(self.monitor_options):
            if mon_index == self.cfg.monitor_index:
                idx = i
                break
        if self.monitor_options:
            self.monitor_combo.current(idx)

    def collect_config_from_ui(self) -> AppConfig:
        if not self.monitor_options:
            raise ValueError("Мониторы не найдены")

        selected_combo_index = self.monitor_combo.current()
        if selected_combo_index < 0:
            selected_combo_index = 0

        monitor_index = self.monitor_options[selected_combo_index][0]

        cfg = AppConfig(
            model_path=self.model_var.get().strip(),
            confidence=float(self.conf_var.get()),
            capture_width=int(self.capture_width_var.get()),
            process_every_n_frame=max(1, int(self.process_n_var.get())),
            monitor_index=monitor_index,
            save_screenshots=bool(self.save_shots_var.get()),
            screenshot_dir=self.shot_dir_var.get().strip(),
            screenshot_cooldown_sec=max(0.1, float(self.shot_cooldown_var.get())),
            stop_hotkey=self.hotkey_var.get().strip(),
            show_labels=bool(self.show_labels_var.get()),
            line_thickness=max(1, int(self.line_thickness_var.get()))
        )
        return cfg

    def choose_model(self):
        path = filedialog.askopenfilename(
            title="Выбери YOLO модель",
            filetypes=[("PyTorch model", "*.pt"), ("All files", "*.*")]
        )
        if path:
            self.model_var.set(path)

    def choose_screenshot_dir(self):
        path = filedialog.askdirectory(title="Выбери папку для скриншотов")
        if path:
            self.shot_dir_var.set(path)

    def refresh_monitors(self):
        self.monitor_options = self._get_monitor_options()
        self.monitor_combo["values"] = [text for _, text in self.monitor_options]
        if self.monitor_options:
            self.monitor_combo.current(0)

    def save_settings(self):
        try:
            self.cfg = self.collect_config_from_ui()
            save_config(self.cfg)
            messagebox.showinfo("Успех", "Настройки сохранены")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def start_detection(self):
        if self.engine.running:
            messagebox.showwarning("Внимание", "Детекция уже запущена")
            return

        try:
            self.cfg = self.collect_config_from_ui()
            save_config(self.cfg)
            self.engine.start(self.cfg)
            self.status_var.set(f"Запущено. Hotkey остановки: {self.cfg.stop_hotkey}")
        except Exception as e:
            messagebox.showerror("Ошибка запуска", str(e))

    def stop_detection(self):
        self.engine.stop()
        self.status_var.set("Остановлено")

    def create_overlay(self, payload):
        if self.overlay is not None:
            try:
                self.overlay.destroy()
            except Exception:
                pass
            self.overlay = None

        self.overlay = OverlayWindow(
            self.root,
            geometry=payload["geometry"],
            show_labels=payload["show_labels"],
            line_thickness=payload["line_thickness"]
        )

    def destroy_overlay(self):
        if self.overlay is not None:
            try:
                self.overlay.destroy()
            except Exception:
                pass
            self.overlay = None

    def process_ui_queue(self):
        try:
            while True:
                event, payload = self.ui_queue.get_nowait()

                if event == "overlay_create":
                    self.create_overlay(payload)

                elif event == "overlay_destroy":
                    self.destroy_overlay()

                elif event == "detections":
                    if self.overlay is not None:
                        self.overlay.set_detections(payload)

                elif event == "fps":
                    self.fps_var.set(f"FPS: {payload}")

                elif event == "screenshot_saved":
                    self.last_shot_var.set(f"Последний скриншот: {payload}")

                elif event == "error":
                    self.status_var.set(f"Ошибка: {payload}")
                    messagebox.showerror("Ошибка", payload)

                elif event == "stopped":
                    self.status_var.set("Остановлено")
                    if self.overlay is not None:
                        self.overlay.clear_detections()

        except queue.Empty:
            pass

        self.root.after(50, self.process_ui_queue)

    def on_close(self):
        try:
            self.engine.stop()
        except Exception:
            pass
        self.destroy_overlay()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()