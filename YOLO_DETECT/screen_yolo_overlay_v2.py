import os
import time
import json
import queue
import threading
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional, Dict

import cv2
import mss
import numpy as np
import keyboard
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from ultralytics import YOLO


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

    device: str = "auto"          # auto / cpu / cuda:0
    smoothing_alpha: float = 0.65 # 0..1, чем выше - тем плавнее
    min_match_iou: float = 0.30
    overlay_update_ms: int = 33   # ~30 FPS отрисовка overlay


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


def clamp(v, a, b):
    return max(a, min(b, v))


def compute_iou(box_a, box_b) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    inter = iw * ih

    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)

    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


class BoxSmoother:
    """
    Простое сглаживание:
    - пытается сопоставить новый бокс со старым по IoU и label
    - делает EMA по координатам
    """
    def __init__(self, alpha: float = 0.65, min_match_iou: float = 0.30):
        self.alpha = clamp(alpha, 0.0, 0.99)
        self.min_match_iou = clamp(min_match_iou, 0.0, 1.0)
        self.prev_boxes: List[Tuple[float, float, float, float, str, float]] = []

    def smooth(self, detections: List[Tuple[int, int, int, int, str, float]]) -> List[Tuple[int, int, int, int, str, float]]:
        if not detections:
            self.prev_boxes = []
            return []

        result = []
        used_prev = set()

        for det in detections:
            x1, y1, x2, y2, label, conf = det
            best_idx = -1
            best_iou = 0.0

            for i, prev in enumerate(self.prev_boxes):
                if i in used_prev:
                    continue
                px1, py1, px2, py2, plabel, pconf = prev
                if plabel != label:
                    continue

                iou = compute_iou((x1, y1, x2, y2), (px1, py1, px2, py2))
                if iou > best_iou:
                    best_iou = iou
                    best_idx = i

            if best_idx >= 0 and best_iou >= self.min_match_iou:
                used_prev.add(best_idx)
                px1, py1, px2, py2, plabel, pconf = self.prev_boxes[best_idx]

                a = self.alpha
                sx1 = a * px1 + (1 - a) * x1
                sy1 = a * py1 + (1 - a) * y1
                sx2 = a * px2 + (1 - a) * x2
                sy2 = a * py2 + (1 - a) * y2
                sconf = a * pconf + (1 - a) * conf

                result.append((int(sx1), int(sy1), int(sx2), int(sy2), label, float(sconf)))
            else:
                result.append((x1, y1, x2, y2, label, conf))

        self.prev_boxes = [(float(x1), float(y1), float(x2), float(y2), label, conf) for x1, y1, x2, y2, label, conf in result]
        return result


class OverlayWindow(tk.Toplevel):
    def __init__(self, master, geometry: dict, show_labels: bool = True, line_thickness: int = 3):
        super().__init__(master)

        self.left = geometry["left"]
        self.top = geometry["top"]
        self.width = geometry["width"]
        self.height = geometry["height"]

        self.show_labels = show_labels
        self.line_thickness = line_thickness
        self.detections: List[Tuple[int, int, int, int, str, float]] = []

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.config(bg="magenta")

        try:
            self.wm_attributes("-transparentcolor", "magenta")
        except Exception:
            pass

        self.geometry(f"{self.width}x{self.height}+{self.left}+{self.top}")

        self.canvas = tk.Canvas(
            self,
            width=self.width,
            height=self.height,
            bg="magenta",
            highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)

    def set_detections(self, detections: List[Tuple[int, int, int, int, str, float]]) -> None:
        self.detections = detections
        self.redraw()

    def clear_detections(self):
        self.detections = []
        self.redraw()

    def redraw(self):
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
                text_y = max(18, ry1 - 8)
                w = max(110, len(text) * 8)

                self.canvas.create_rectangle(
                    text_x,
                    text_y - 18,
                    text_x + w,
                    text_y + 2,
                    fill="lime",
                    outline="lime"
                )
                self.canvas.create_text(
                    text_x + 4,
                    text_y - 8,
                    text=text,
                    anchor="w",
                    fill="black",
                    font=("Arial", 10, "bold")
                )


class DetectionEngine:
    def __init__(self, ui_queue: queue.Queue):
        self.ui_queue = ui_queue
        self.worker_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.running = False

        self.hotkey_handle = None
        self.last_screenshot_time = 0.0
        self.smoother: Optional[BoxSmoother] = None

    def start(self, cfg: AppConfig):
        if self.running:
            return

        if not os.path.exists(cfg.model_path):
            raise FileNotFoundError(f"Модель не найдена: {cfg.model_path}")

        if cfg.save_screenshots:
            os.makedirs(cfg.screenshot_dir, exist_ok=True)

        self.stop_event.clear()
        self.running = True
        self.last_screenshot_time = 0.0
        self.smoother = BoxSmoother(alpha=cfg.smoothing_alpha, min_match_iou=cfg.min_match_iou)

        self.worker_thread = threading.Thread(target=self._run_loop, args=(cfg,), daemon=True)
        self.worker_thread.start()

        self._register_hotkey(cfg.stop_hotkey)

    def stop(self):
        if not self.running:
            return
        self.stop_event.set()
        self.running = False
        self._unregister_hotkey()
        self.ui_queue.put(("stopped", None))

    def _register_hotkey(self, hotkey: str):
        self._unregister_hotkey()
        try:
            self.hotkey_handle = keyboard.add_hotkey(hotkey, self.stop)
        except Exception as e:
            self.ui_queue.put(("error", f"Не удалось зарегистрировать hotkey '{hotkey}': {e}"))

    def _unregister_hotkey(self):
        try:
            if self.hotkey_handle is not None:
                keyboard.remove_hotkey(self.hotkey_handle)
        except Exception:
            pass
        self.hotkey_handle = None

    def _resolve_device(self, cfg: AppConfig) -> str:
        dev = cfg.device.strip().lower()
        if dev == "auto":
            try:
                import torch
                return "cuda:0" if torch.cuda.is_available() else "cpu"
            except Exception:
                return "cpu"
        return dev

    def _save_detection_screenshot(self, image_bgr, detections, save_dir):
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

    def _run_loop(self, cfg: AppConfig):
        try:
            device = self._resolve_device(cfg)
            self.ui_queue.put(("device_info", device))

            model = YOLO(cfg.model_path)
            sct = mss.mss()

            if cfg.monitor_index < 1 or cfg.monitor_index >= len(sct.monitors):
                raise ValueError(f"Неверный monitor_index={cfg.monitor_index}. Доступно: {len(sct.monitors) - 1}")

            monitor = sct.monitors[cfg.monitor_index]

            self.ui_queue.put(("overlay_create", {
                "geometry": monitor,
                "show_labels": cfg.show_labels,
                "line_thickness": cfg.line_thickness
            }))

            frame_index = 0
            fps_counter = 0
            fps_time = time.time()
            last_overlay_push = 0.0
            overlay_interval = max(0.005, cfg.overlay_update_ms / 1000.0)

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
                    device=device,
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

                if self.smoother is not None:
                    parsed_detections = self.smoother.smooth(parsed_detections)

                now = time.time()
                if now - last_overlay_push >= overlay_interval:
                    self.ui_queue.put(("detections", parsed_detections))
                    last_overlay_push = now

                if cfg.save_screenshots and parsed_detections:
                    if now - self.last_screenshot_time >= cfg.screenshot_cooldown_sec:
                        self.last_screenshot_time = now
                        local_boxes = [
                            (
                                x1 - monitor["left"],
                                y1 - monitor["top"],
                                x2 - monitor["left"],
                                y2 - monitor["top"],
                                label,
                                conf
                            )
                            for x1, y1, x2, y2, label, conf in parsed_detections
                        ]
                        self._save_detection_screenshot(frame, local_boxes, cfg.screenshot_dir)

                fps_counter += 1
                if now - fps_time >= 1.0:
                    fps = fps_counter / (now - fps_time)
                    self.ui_queue.put(("fps", round(fps, 2)))
                    fps_counter = 0
                    fps_time = now

        except Exception as e:
            self.ui_queue.put(("error", str(e)))
        finally:
            self.running = False
            self._unregister_hotkey()
            self.ui_queue.put(("overlay_destroy", None))
            self.ui_queue.put(("stopped", None))


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("YOLO Screen Detection GUI v2")
        self.root.geometry("840x760")
        self.root.minsize(800, 700)

        self.cfg = load_config()
        self.ui_queue = queue.Queue()
        self.engine = DetectionEngine(self.ui_queue)
        self.overlay: Optional[OverlayWindow] = None

        self.monitor_options = self._get_monitor_options()
        self.is_listening_hotkey = False
        self.hotkey_listener_hook = None

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
        ttk.Entry(main, textvariable=self.model_var, width=70).grid(row=row, column=1, sticky="ew", padx=6, pady=6)
        ttk.Button(main, text="Выбрать", command=self.choose_model).grid(row=row, column=2, pady=6)
        row += 1

        ttk.Label(main, text="Монитор:").grid(row=row, column=0, sticky="w", pady=6)
        self.monitor_var = tk.StringVar()
        self.monitor_combo = ttk.Combobox(main, textvariable=self.monitor_var, state="readonly", width=55)
        self.monitor_combo["values"] = [text for _, text in self.monitor_options]
        self.monitor_combo.grid(row=row, column=1, sticky="ew", padx=6, pady=6)
        ttk.Button(main, text="Обновить", command=self.refresh_monitors).grid(row=row, column=2, pady=6)
        row += 1

        ttk.Label(main, text="Устройство:").grid(row=row, column=0, sticky="w", pady=6)
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(main, textvariable=self.device_var, state="readonly", width=20)
        self.device_combo["values"] = ["auto", "cpu", "cuda:0"]
        self.device_combo.grid(row=row, column=1, sticky="w", padx=6, pady=6)
        row += 1

        ttk.Label(main, text="Confidence:").grid(row=row, column=0, sticky="w", pady=6)
        self.conf_var = tk.DoubleVar()
        ttk.Entry(main, textvariable=self.conf_var).grid(row=row, column=1, sticky="ew", padx=6, pady=6)
        row += 1

        ttk.Label(main, text="Ширина кадра для детекции:").grid(row=row, column=0, sticky="w", pady=6)
        self.capture_width_var = tk.IntVar()
        ttk.Entry(main, textvariable=self.capture_width_var).grid(row=row, column=1, sticky="ew", padx=6, pady=6)
        row += 1

        ttk.Label(main, text="Обрабатывать каждый N-й кадр:").grid(row=row, column=0, sticky="w", pady=6)
        self.process_n_var = tk.IntVar()
        ttk.Entry(main, textvariable=self.process_n_var).grid(row=row, column=1, sticky="ew", padx=6, pady=6)
        row += 1

        ttk.Label(main, text="Горячая клавиша остановки:").grid(row=row, column=0, sticky="w", pady=6)
        self.hotkey_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.hotkey_var).grid(row=row, column=1, sticky="ew", padx=6, pady=6)
        self.record_hotkey_btn = ttk.Button(main, text="Записать hotkey", command=self.start_hotkey_recording)
        self.record_hotkey_btn.grid(row=row, column=2, pady=6)
        row += 1

        ttk.Label(main, text="Сглаживание alpha (0..0.99):").grid(row=row, column=0, sticky="w", pady=6)
        self.smoothing_alpha_var = tk.DoubleVar()
        ttk.Entry(main, textvariable=self.smoothing_alpha_var).grid(row=row, column=1, sticky="ew", padx=6, pady=6)
        row += 1

        ttk.Label(main, text="Минимальный IoU сопоставления:").grid(row=row, column=0, sticky="w", pady=6)
        self.min_match_iou_var = tk.DoubleVar()
        ttk.Entry(main, textvariable=self.min_match_iou_var).grid(row=row, column=1, sticky="ew", padx=6, pady=6)
        row += 1

        ttk.Label(main, text="Интервал обновления overlay (мс):").grid(row=row, column=0, sticky="w", pady=6)
        self.overlay_update_ms_var = tk.IntVar()
        ttk.Entry(main, textvariable=self.overlay_update_ms_var).grid(row=row, column=1, sticky="ew", padx=6, pady=6)
        row += 1

        self.show_labels_var = tk.BooleanVar()
        ttk.Checkbutton(main, text="Показывать названия классов", variable=self.show_labels_var).grid(
            row=row, column=0, sticky="w", pady=6
        )
        row += 1

        ttk.Label(main, text="Толщина линии:").grid(row=row, column=0, sticky="w", pady=6)
        self.line_thickness_var = tk.IntVar()
        ttk.Entry(main, textvariable=self.line_thickness_var).grid(row=row, column=1, sticky="ew", padx=6, pady=6)
        row += 1

        self.save_shots_var = tk.BooleanVar()
        ttk.Checkbutton(main, text="Сохранять скриншоты при детекции", variable=self.save_shots_var).grid(
            row=row, column=0, sticky="w", pady=6
        )
        row += 1

        ttk.Label(main, text="Папка скриншотов:").grid(row=row, column=0, sticky="w", pady=6)
        self.shot_dir_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.shot_dir_var).grid(row=row, column=1, sticky="ew", padx=6, pady=6)
        ttk.Button(main, text="Выбрать", command=self.choose_screenshot_dir).grid(row=row, column=2, pady=6)
        row += 1

        ttk.Label(main, text="Кулдаун между скриншотами (сек):").grid(row=row, column=0, sticky="w", pady=6)
        self.shot_cooldown_var = tk.DoubleVar()
        ttk.Entry(main, textvariable=self.shot_cooldown_var).grid(row=row, column=1, sticky="ew", padx=6, pady=6)
        row += 1

        btns = ttk.Frame(main)
        btns.grid(row=row, column=0, columnspan=3, sticky="ew", pady=12)
        self.start_btn = ttk.Button(btns, text="Старт", command=self.start_detection)
        self.start_btn.pack(side="left", padx=4)
        self.stop_btn = ttk.Button(btns, text="Стоп", command=self.stop_detection)
        self.stop_btn.pack(side="left", padx=4)
        self.save_btn = ttk.Button(btns, text="Сохранить настройки", command=self.save_settings)
        self.save_btn.pack(side="left", padx=4)
        row += 1

        status = ttk.LabelFrame(main, text="Статус", padding=10)
        status.grid(row=row, column=0, columnspan=3, sticky="nsew", pady=8)

        self.status_var = tk.StringVar(value="Готово")
        self.fps_var = tk.StringVar(value="FPS: -")
        self.device_info_var = tk.StringVar(value="Устройство: -")
        self.last_shot_var = tk.StringVar(value="Последний скриншот: -")

        ttk.Label(status, textvariable=self.status_var).pack(anchor="w")
        ttk.Label(status, textvariable=self.fps_var).pack(anchor="w", pady=3)
        ttk.Label(status, textvariable=self.device_info_var).pack(anchor="w", pady=3)
        ttk.Label(status, textvariable=self.last_shot_var, wraplength=760).pack(anchor="w", pady=3)

        main.columnconfigure(1, weight=1)

    def _load_values_to_ui(self):
        self.model_var.set(self.cfg.model_path)
        self.conf_var.set(self.cfg.confidence)
        self.capture_width_var.set(self.cfg.capture_width)
        self.process_n_var.set(self.cfg.process_every_n_frame)
        self.hotkey_var.set(self.cfg.stop_hotkey)

        self.show_labels_var.set(self.cfg.show_labels)
        self.line_thickness_var.set(self.cfg.line_thickness)

        self.save_shots_var.set(self.cfg.save_screenshots)
        self.shot_dir_var.set(self.cfg.screenshot_dir)
        self.shot_cooldown_var.set(self.cfg.screenshot_cooldown_sec)

        self.device_var.set(self.cfg.device)
        self.smoothing_alpha_var.set(self.cfg.smoothing_alpha)
        self.min_match_iou_var.set(self.cfg.min_match_iou)
        self.overlay_update_ms_var.set(self.cfg.overlay_update_ms)

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

        combo_idx = self.monitor_combo.current()
        if combo_idx < 0:
            combo_idx = 0

        monitor_index = self.monitor_options[combo_idx][0]

        return AppConfig(
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
            line_thickness=max(1, int(self.line_thickness_var.get())),

            device=self.device_var.get().strip(),
            smoothing_alpha=clamp(float(self.smoothing_alpha_var.get()), 0.0, 0.99),
            min_match_iou=clamp(float(self.min_match_iou_var.get()), 0.0, 1.0),
            overlay_update_ms=max(5, int(self.overlay_update_ms_var.get()))
        )

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

    def start_hotkey_recording(self):
        if self.is_listening_hotkey:
            return

        self.is_listening_hotkey = True
        self.status_var.set("Нажми клавишу или комбинацию для hotkey... Esc = отмена")
        self.record_hotkey_btn.config(text="Слушаю...")

        pressed = set()

        def on_event(event):
            nonlocal pressed

            if not self.is_listening_hotkey:
                return

            if event.event_type == "down":
                pressed.add(event.name)

                if event.name == "esc":
                    self.root.after(0, self.finish_hotkey_recording, None)
                    return

                combo = self.normalize_hotkey(pressed)
                self.root.after(0, self.finish_hotkey_recording, combo)

        self.hotkey_listener_hook = keyboard.hook(on_event)

    def finish_hotkey_recording(self, combo: Optional[str]):
        if not self.is_listening_hotkey:
            return

        self.is_listening_hotkey = False

        try:
            if self.hotkey_listener_hook is not None:
                keyboard.unhook(self.hotkey_listener_hook)
        except Exception:
            pass
        self.hotkey_listener_hook = None

        self.record_hotkey_btn.config(text="Записать hotkey")

        if combo:
            self.hotkey_var.set(combo)
            self.status_var.set(f"Hotkey записан: {combo}")
        else:
            self.status_var.set("Запись hotkey отменена")

    def normalize_hotkey(self, keys) -> str:
        order = ["ctrl", "alt", "shift", "windows"]
        keys = {k.lower() for k in keys}

        normalized = []
        for k in order:
            if k in keys:
                normalized.append(k)

        others = sorted(k for k in keys if k not in order)
        normalized.extend(others)

        return "+".join(normalized)

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
        self.destroy_overlay()
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

                elif event == "device_info":
                    self.device_info_var.set(f"Устройство: {payload}")

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

        if self.is_listening_hotkey:
            self.finish_hotkey_recording(None)

        self.destroy_overlay()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()