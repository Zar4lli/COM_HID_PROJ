from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

try:
    import mss
except Exception:
    mss = None

try:
    from ultralytics import YOLO
except Exception:
    YOLO = None

try:
    import torch
except Exception:
    torch = None


@dataclass
class Detection:
    class_name: str
    confidence: float
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def center(self) -> Tuple[int, int]:
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)

    @property
    def area(self) -> int:
        return max(0, self.x2 - self.x1) * max(0, self.y2 - self.y1)


class YoloDetector:
    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        conf: float = 0.35,
        monitor_index: int = 1,
        device: str = "cpu",
        capture_width: int = 960,
    ):
        self.model_path = model_path
        self.conf = conf
        self.monitor_index = monitor_index
        self.device = device
        self.capture_width = capture_width
        self._model = None

    def _ensure_ready(self):
        if YOLO is None:
            raise RuntimeError("Ultralytics не установлен. Установи: pip install ultralytics")
        if mss is None:
            raise RuntimeError("mss не установлен. Установи: pip install mss")
        if self._model is None:
            self._model = YOLO(self.model_path)

    def set_model_path(self, model_path: str):
        if self.model_path != model_path:
            self.model_path = model_path
            self._model = None

    def set_conf(self, conf: float):
        if conf <= 0 or conf > 1:
            raise ValueError("Confidence должен быть в диапазоне (0, 1]")
        self.conf = conf

    def set_monitor_index(self, monitor_index: int):
        if monitor_index < 1:
            raise ValueError("monitor_index должен быть >= 1")
        self.monitor_index = monitor_index

    def set_device(self, device: str):
        self.device = device

    def set_capture_width(self, capture_width: int):
        self.capture_width = max(0, int(capture_width))

    def available_devices(self) -> list[str]:
        devices = ["auto", "cpu"]
        if torch is not None and torch.cuda.is_available():
            devices.append("cuda:0")
        return devices

    def _resolved_device(self) -> str:
        dev = (self.device or "cpu").strip().lower()
        if dev == "auto":
            if torch is not None and torch.cuda.is_available():
                return "cuda:0"
            return "cpu"
        return dev

    def available_model_classes(self) -> list[str]:
        self._ensure_ready()
        names = self._model.names
        if isinstance(names, dict):
            return [str(names[k]) for k in sorted(names.keys())]
        return [str(x) for x in names]

    def _normalized_key(self, value: str) -> str:
        return value.strip().lower().replace("_", "").replace("-", "").replace(" ", "")

    def resolve_class_name(self, requested_name: str) -> str:
        self._ensure_ready()
        requested_key = self._normalized_key(requested_name)
        classes = self.available_model_classes()
        for cls_name in classes:
            if self._normalized_key(cls_name) == requested_key:
                return cls_name
        raise RuntimeError(
            f"Класс '{requested_name}' не найден в модели. Используй кнопку 'Классы модели' и выбери точное имя."
        )

    def available_monitors(self) -> list[dict]:
        if mss is None:
            return []
        with mss.mss() as sct:
            result = []
            for idx, mon in enumerate(sct.monitors[1:], start=1):
                result.append({
                    "index": idx,
                    "left": mon["left"],
                    "top": mon["top"],
                    "width": mon["width"],
                    "height": mon["height"],
                })
            return result

    def _get_cursor_position(self) -> Tuple[int, int]:
        import platform
        if platform.system() != "Windows":
            raise RuntimeError("Определение позиции курсора поддержано только на Windows")
        import ctypes

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)) == 0:
            raise RuntimeError("Не удалось получить позицию курсора")
        return int(pt.x), int(pt.y)

    def grab_screen(self, monitor_index: Optional[int] = None):
        self._ensure_ready()
        idx = monitor_index if monitor_index is not None else self.monitor_index
        with mss.mss() as sct:
            monitors = sct.monitors
            if idx >= len(monitors):
                raise RuntimeError(f"Монитор {idx} недоступен. Доступно экранов: {len(monitors) - 1}")
            monitor = monitors[idx]
            shot = sct.grab(monitor)
        frame = np.array(shot)
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        return frame_bgr, monitor

    def _center_in_region(self, det: Detection, region: Tuple[int, int, int, int]) -> bool:
        x1, y1, x2, y2 = region
        left, right = min(x1, x2), max(x1, x2)
        top, bottom = min(y1, y2), max(y1, y2)
        cx, cy = det.center
        return left <= cx <= right and top <= cy <= bottom

    def detect(
        self,
        monitor_index: Optional[int] = None,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> List[Detection]:
        self._ensure_ready()
        frame, monitor = self.grab_screen(monitor_index=monitor_index)

        original_h, original_w = frame.shape[:2]
        input_frame = frame
        scale_x = 1.0
        scale_y = 1.0

        if self.capture_width > 0 and original_w > self.capture_width:
            new_w = self.capture_width
            new_h = int(original_h * (new_w / original_w))
            input_frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            scale_x = original_w / new_w
            scale_y = original_h / new_h

        results = self._model.predict(
            source=input_frame,
            conf=self.conf,
            device=self._resolved_device(),
            verbose=False,
        )

        names = results[0].names if results else self._model.names
        detections: List[Detection] = []

        if results:
            result = results[0]
            boxes = result.boxes
            if boxes is not None and len(boxes) > 0:
                for box in boxes:
                    cls_id = int(box.cls[0].item())
                    conf = float(box.conf[0].item())
                    x1, y1, x2, y2 = box.xyxy[0].tolist()

                    gx1 = int(x1 * scale_x) + monitor["left"]
                    gy1 = int(y1 * scale_y) + monitor["top"]
                    gx2 = int(x2 * scale_x) + monitor["left"]
                    gy2 = int(y2 * scale_y) + monitor["top"]

                    if isinstance(names, dict):
                        label = str(names.get(cls_id, str(cls_id)))
                    else:
                        label = str(names[cls_id])

                    detections.append(Detection(label, conf, gx1, gy1, gx2, gy2))

        if region is not None:
            detections = [d for d in detections if self._center_in_region(d, region)]

        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections

    def find_all(self, target_class: str, monitor_index=None, region=None) -> List[Detection]:
        resolved = self.resolve_class_name(target_class)
        return [d for d in self.detect(monitor_index=monitor_index, region=region) if d.class_name == resolved]

    def find_best(self, target_class: str, monitor_index=None, region=None) -> Optional[Detection]:
        candidates = self.find_all(target_class, monitor_index=monitor_index, region=region)
        return candidates[0] if candidates else None

    def find_largest(self, target_class: str, monitor_index=None, region=None) -> Optional[Detection]:
        candidates = self.find_all(target_class, monitor_index=monitor_index, region=region)
        return sorted(candidates, key=lambda d: d.area, reverse=True)[0] if candidates else None

    def find_nearest_to_cursor(self, target_class: str, monitor_index=None, region=None) -> Optional[Detection]:
        cursor_x, cursor_y = self._get_cursor_position()
        candidates = self.find_all(target_class, monitor_index=monitor_index, region=region)
        if not candidates:
            return None
        return sorted(candidates, key=lambda d: (d.center[0]-cursor_x)**2 + (d.center[1]-cursor_y)**2)[0]

    def find_nearest_to_screen_center(self, target_class: str, monitor_index=None, region=None) -> Optional[Detection]:
        if region is not None:
            x1, y1, x2, y2 = region
            center = ((x1 + x2) // 2, (y1 + y2) // 2)
        else:
            _, monitor = self.grab_screen(monitor_index=monitor_index)
            center = (monitor["left"] + monitor["width"] // 2, monitor["top"] + monitor["height"] // 2)

        candidates = self.find_all(target_class, monitor_index=monitor_index, region=region)
        if not candidates:
            return None
        return sorted(candidates, key=lambda d: (d.center[0]-center[0])**2 + (d.center[1]-center[1])**2)[0]
