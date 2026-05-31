import json
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from serial_module import SerialManager, CursorController, get_serial_ports, DEFAULT_BAUDRATE
from yolo_detect import YoloDetector

from .models import APP_TITLE, APP_VERSION, MacroStep, RunResult, DEFAULT_STEP_DELAY_MS
from .windows import LogWindow, HelpWindow, StepEditor
from .hotkeys import HotkeyManager
from .runner import MacroRunner
from .script_queue import ScriptQueueManager
from .ui_helpers import ACTION_DEFS, CURSOR_ACTION_DEFS, parse_region_from_ui, parse_offset_from_ui, build_yolo_command_from_ui, build_cursor_command_from_ui, make_macro_step


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} {APP_VERSION}")
        self.geometry("1320x760")
        self.minsize(1120, 680)

        self.serial_manager = SerialManager()
        self.yolo_detector = YoloDetector(model_path="yolov8n.pt", conf=0.35, monitor_index=1, device="auto", capture_width=960)
        self.runner = MacroRunner(self, self.serial_manager, self.yolo_detector)
        self.hotkey_manager = HotkeyManager(self)
        self.log_window = LogWindow(self)
        self.log_window.withdraw()
        self.queue_manager = ScriptQueueManager()

        self.steps: list[MacroStep] = []
        self._manual_stop_requested = False

        self.port_var = tk.StringVar()
        self.baud_var = tk.StringVar(value=str(DEFAULT_BAUDRATE))
        self.cycles_var = tk.StringVar(value="1")
        self.progress_var = tk.DoubleVar(value=0)
        self.status_var = tk.StringVar(value="Готов")
        self.quick_command_var = tk.StringVar()

        self.hotkey_var = tk.StringVar(value="")
        self.hotkey_status_var = tk.StringVar(value="Горячая клавиша не назначена")
        self.listen_hotkey_active = False
        self.listen_modifiers = set()

        self.yolo_model_var = tk.StringVar(value="yolov8n.pt")
        self.yolo_conf_var = tk.StringVar(value="0.35")
        self.monitor_index_var = tk.StringVar(value="1")
        self.yolo_device_var = tk.StringVar(value="auto")
        self.yolo_capture_width_var = tk.StringVar(value="960")
        self.detect_class_var = tk.StringVar(value="")
        self.yolo_action_var = tk.StringVar(value="DETECT_MOVE")
        self.yolo_action_desc_var = tk.StringVar(value=ACTION_DEFS["DETECT_MOVE"])
        self.stop_on_no_detection_var = tk.BooleanVar(value=False)

        self.region_x1_var = tk.StringVar()
        self.region_y1_var = tk.StringVar()
        self.region_x2_var = tk.StringVar()
        self.region_y2_var = tk.StringVar()
        self.offset_dx_var = tk.StringVar(value="0")
        self.offset_dy_var = tk.StringVar(value="0")

        self.cursor_live_var = tk.StringVar(value="Курсор: X=0 Y=0")
        self.cursor_target_x_var = tk.StringVar()
        self.cursor_target_y_var = tk.StringVar()
        self.cursor_action_var = tk.StringVar(value="MOVE_TO")
        self.cursor_action_desc_var = tk.StringVar(value=CURSOR_ACTION_DEFS["MOVE_TO"])

        self.queue_enabled_var = tk.BooleanVar(value=False)
        self.queue_auto_run_var = tk.BooleanVar(value=False)
        self.queue_folder_var = tk.StringVar(value="")
        self.queue_cycles_var = tk.StringVar(value="1")

        self._build_ui()
        self.bind_all("<KeyPress>", self.on_key_press_for_hotkey_listen, add="+")
        self.bind_all("<KeyRelease>", self.on_key_release_for_hotkey_listen, add="+")
        self.refresh_ports()
        self.refresh_yolo_sources()
        self.start_cursor_tracking()
        self.log_start_help()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self):
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)

        top = ttk.LabelFrame(root, text="Подключение", padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="COM-порт").grid(row=0, column=0, sticky="w")
        self.port_combo = ttk.Combobox(top, textvariable=self.port_var, width=16, state="readonly")
        self.port_combo.grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Button(top, text="Обновить", command=self.refresh_ports).grid(row=1, column=1, sticky="w", padx=(0, 16))

        ttk.Label(top, text="Baudrate").grid(row=0, column=2, sticky="w")
        ttk.Entry(top, textvariable=self.baud_var, width=10).grid(row=1, column=2, sticky="w", padx=(0, 8))

        self.connect_btn = ttk.Button(top, text="Подключить", command=self.toggle_connection)
        self.connect_btn.grid(row=1, column=3, sticky="w", padx=(0, 8))

        ttk.Button(top, text="PING", command=self.send_ping).grid(row=1, column=4, sticky="w", padx=(0, 8))
        ttk.Button(top, text="Журнал", command=self.show_log_window).grid(row=1, column=5, sticky="w", padx=(12, 0))
        ttk.Button(top, text="Справка", command=lambda: HelpWindow(self)).grid(row=1, column=6, sticky="w", padx=(8, 0))

        middle = ttk.Panedwindow(root, orient="horizontal")
        middle.pack(fill="both", expand=True, pady=10)

        left = ttk.Frame(middle)
        right = ttk.Frame(middle)
        middle.add(left, weight=4)
        middle.add(right, weight=2)

        macro_box = ttk.LabelFrame(left, text="Набор действий", padding=8)
        macro_box.pack(fill="both", expand=True)

        tree_wrap = ttk.Frame(macro_box)
        tree_wrap.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(tree_wrap, columns=("command", "delay", "resp"), show="headings", height=18)
        self.tree.heading("command", text="Команда")
        self.tree.heading("delay", text="Задержка, мс")
        self.tree.heading("resp", text="Ответ")
        self.tree.column("command", width=670)
        self.tree.column("delay", width=95, anchor="center")
        self.tree.column("resp", width=70, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")

        ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview).grid(row=0, column=1, sticky="ns")
        ttk.Scrollbar(tree_wrap, orient="horizontal", command=self.tree.xview).grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=lambda *args: tree_wrap.grid_slaves(row=0, column=1)[0].set(*args),
                            xscrollcommand=lambda *args: tree_wrap.grid_slaves(row=1, column=0)[0].set(*args))
        tree_wrap.rowconfigure(0, weight=1)
        tree_wrap.columnconfigure(0, weight=1)

        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="Добавить", command=self.add_step).pack(side="left")
        ttk.Button(btns, text="Изменить", command=self.edit_step).pack(side="left", padx=6)
        ttk.Button(btns, text="Удалить", command=self.delete_step).pack(side="left")
        ttk.Button(btns, text="Вверх", command=lambda: self.move_step(-1)).pack(side="left", padx=(12, 6))
        ttk.Button(btns, text="Вниз", command=lambda: self.move_step(1)).pack(side="left")
        ttk.Button(btns, text="Очистить", command=self.clear_steps).pack(side="left", padx=(12, 0))

        io_btns = ttk.Frame(left)
        io_btns.pack(fill="x", pady=(8, 0))
        ttk.Button(io_btns, text="Импорт JSON", command=self.import_steps).pack(side="left")
        ttk.Button(io_btns, text="Экспорт JSON", command=self.export_steps).pack(side="left", padx=6)

        queue_box = ttk.LabelFrame(left, text="Очередь пользовательских скриптов", padding=8)
        queue_box.pack(fill="x", pady=(10, 0))

        ttk.Checkbutton(queue_box, text="Включить очередь папки", variable=self.queue_enabled_var).grid(row=0, column=0, sticky="w", columnspan=3)
        ttk.Checkbutton(queue_box, text="Автоматически запускать следующий скрипт", variable=self.queue_auto_run_var).grid(row=1, column=0, sticky="w", columnspan=3)

        ttk.Label(queue_box, text="Папка").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(queue_box, textvariable=self.queue_folder_var).grid(row=3, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(queue_box, text="Выбрать", command=self.pick_script_folder).grid(row=3, column=1, sticky="w")

        ttk.Label(queue_box, text="Циклы по папке").grid(row=2, column=2, sticky="w", pady=(6, 0))
        ttk.Entry(queue_box, textvariable=self.queue_cycles_var, width=8).grid(row=3, column=2, sticky="w")

        self.queue_list = tk.Listbox(queue_box, height=5)
        self.queue_list.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        queue_box.columnconfigure(0, weight=1)

        right_notebook = ttk.Notebook(right)
        right_notebook.pack(fill="both", expand=True)

        self.yolo_tab = ttk.Frame(right_notebook, padding=8)
        self.run_tab = ttk.Frame(right_notebook, padding=8)
        self.cursor_tab = ttk.Frame(right_notebook, padding=8)

        right_notebook.add(self.yolo_tab, text="YOLO")
        right_notebook.add(self.run_tab, text="Выполнение")
        right_notebook.add(self.cursor_tab, text="Курсор")

        self._build_yolo_tab()
        self._build_run_tab()
        self._build_cursor_tab()

    def _build_yolo_tab(self):
        tab = self.yolo_tab
        ttk.Label(tab, text="Модель").grid(row=0, column=0, sticky="w")
        model_frame = ttk.Frame(tab)
        model_frame.grid(row=1, column=0, columnspan=4, sticky="ew")
        model_frame.columnconfigure(0, weight=1)
        ttk.Entry(model_frame, textvariable=self.yolo_model_var).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(model_frame, text="Выбрать .pt", command=self.pick_yolo_model).grid(row=0, column=1, sticky="w")

        ttk.Label(tab, text="Confidence").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(tab, textvariable=self.yolo_conf_var, width=10).grid(row=3, column=0, sticky="w")

        ttk.Label(tab, text="Экран").grid(row=2, column=1, sticky="w", pady=(8, 0))
        self.monitor_combo = ttk.Combobox(tab, textvariable=self.monitor_index_var, state="readonly", width=14)
        self.monitor_combo.grid(row=3, column=1, sticky="w")

        ttk.Label(tab, text="Device").grid(row=2, column=2, sticky="w", pady=(8, 0))
        self.device_combo = ttk.Combobox(tab, textvariable=self.yolo_device_var, state="readonly", width=10)
        self.device_combo.grid(row=3, column=2, sticky="w")

        ttk.Label(tab, text="Ширина кадра").grid(row=2, column=3, sticky="w", pady=(8, 0))
        ttk.Entry(tab, textvariable=self.yolo_capture_width_var, width=10).grid(row=3, column=3, sticky="w")

        ttk.Button(tab, text="Применить", command=self.apply_yolo_settings).grid(row=4, column=3, sticky="e", pady=(8, 0))
        ttk.Button(tab, text="Классы модели", command=self.show_model_classes).grid(row=4, column=2, sticky="e", pady=(8, 0))

        ttk.Label(tab, text="Класс").grid(row=5, column=0, sticky="w", pady=(10, 0))
        self.class_combo = ttk.Combobox(tab, textvariable=self.detect_class_var)
        self.class_combo.grid(row=6, column=0, sticky="ew")

        ttk.Label(tab, text="Действие").grid(row=5, column=1, sticky="w", pady=(10, 0))
        self.yolo_action_combo = ttk.Combobox(tab, textvariable=self.yolo_action_var, state="readonly", values=list(ACTION_DEFS.keys()))
        self.yolo_action_combo.grid(row=6, column=1, sticky="ew")
        self.yolo_action_combo.bind("<<ComboboxSelected>>", self.on_yolo_action_changed)

        ttk.Button(tab, text="Что найдено сейчас → лог", command=self.quick_detect_list).grid(row=6, column=2, columnspan=2, sticky="ew")

        ttk.Label(tab, textvariable=self.yolo_action_desc_var, wraplength=360, justify="left").grid(row=7, column=0, columnspan=4, sticky="w", pady=(6, 0))

        ttk.Label(tab, text="X1").grid(row=8, column=0, sticky="w", pady=(10, 0))
        x1y1 = ttk.Frame(tab)
        x1y1.grid(row=9, column=0, columnspan=2, sticky="w")
        ttk.Entry(x1y1, textvariable=self.region_x1_var, width=8).pack(side="left")
        ttk.Label(x1y1, text="Y1").pack(side="left", padx=(6, 2))
        ttk.Entry(x1y1, textvariable=self.region_y1_var, width=8).pack(side="left")
        ttk.Button(x1y1, text="Считать", command=lambda: self.capture_cursor_to_region("x1y1")).pack(side="left", padx=(8, 0))

        ttk.Label(tab, text="X2").grid(row=10, column=0, sticky="w", pady=(8, 0))
        x2y2 = ttk.Frame(tab)
        x2y2.grid(row=11, column=0, columnspan=2, sticky="w")
        ttk.Entry(x2y2, textvariable=self.region_x2_var, width=8).pack(side="left")
        ttk.Label(x2y2, text="Y2").pack(side="left", padx=(6, 2))
        ttk.Entry(x2y2, textvariable=self.region_y2_var, width=8).pack(side="left")
        ttk.Button(x2y2, text="Считать", command=lambda: self.capture_cursor_to_region("x2y2")).pack(side="left", padx=(8, 0))

        ttk.Label(tab, text="dx").grid(row=8, column=2, sticky="w", pady=(10, 0))
        ttk.Entry(tab, textvariable=self.offset_dx_var, width=8).grid(row=9, column=2, sticky="w")
        ttk.Label(tab, text="dy").grid(row=8, column=3, sticky="w", pady=(10, 0))
        ttk.Entry(tab, textvariable=self.offset_dy_var, width=8).grid(row=9, column=3, sticky="w")

        ttk.Checkbutton(tab, text="Если нет детекта — прервать текущий скрипт", variable=self.stop_on_no_detection_var).grid(row=12, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Button(tab, text="Добавить действие в макрос", command=self.add_selected_yolo_action).grid(row=13, column=0, columnspan=4, sticky="ew", pady=(10, 0))

        for c in range(4):
            tab.columnconfigure(c, weight=1)

    def _build_run_tab(self):
        tab = self.run_tab
        ttk.Label(tab, text="Количество циклов текущего набора").grid(row=0, column=0, sticky="w")
        ttk.Entry(tab, textvariable=self.cycles_var, width=12).grid(row=1, column=0, sticky="w")

        ttk.Button(tab, text="Старт", command=self.start_macro).grid(row=1, column=1, sticky="w", padx=(8, 0))
        ttk.Button(tab, text="Стоп", command=self.stop_macro).grid(row=1, column=2, sticky="w", padx=(8, 0))

        ttk.Label(tab, text="Горячая клавиша / комбинация").grid(row=2, column=0, columnspan=3, sticky="w", pady=(14, 0))
        hot = ttk.Frame(tab)
        hot.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        hot.columnconfigure(0, weight=1)
        self.hotkey_entry = ttk.Entry(hot, textvariable=self.hotkey_var)
        self.hotkey_entry.grid(row=0, column=0, sticky="ew")
        self.listen_btn = ttk.Button(hot, text="Слушать", command=self.toggle_hotkey_listen)
        self.listen_btn.grid(row=0, column=1, padx=(8, 0))
        ttk.Button(hot, text="Применить", command=self.apply_hotkey).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(hot, text="Сбросить", command=self.clear_hotkey).grid(row=0, column=3, padx=(8, 0))
        ttk.Label(tab, textvariable=self.hotkey_status_var).grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))

        ttk.Label(tab, text="Быстрая команда").grid(row=5, column=0, sticky="w", pady=(12, 0))
        ttk.Entry(tab, textvariable=self.quick_command_var).grid(row=6, column=0, columnspan=2, sticky="ew")
        ttk.Button(tab, text="Отправить", command=self.send_quick_entry).grid(row=6, column=2, sticky="w", padx=(8, 0))

        ttk.Progressbar(tab, variable=self.progress_var, maximum=100).grid(row=7, column=0, columnspan=3, sticky="ew", pady=(16, 6))
        ttk.Label(tab, textvariable=self.status_var).grid(row=8, column=0, columnspan=3, sticky="w")
        for c in range(3):
            tab.columnconfigure(c, weight=1)

    def _build_cursor_tab(self):
        tab = self.cursor_tab
        ttk.Label(tab, textvariable=self.cursor_live_var).grid(row=0, column=0, columnspan=4, sticky="w")

        ttk.Label(tab, text="Действие").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.cursor_action_combo = ttk.Combobox(tab, textvariable=self.cursor_action_var, state="readonly", values=list(CURSOR_ACTION_DEFS.keys()))
        self.cursor_action_combo.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.cursor_action_combo.bind("<<ComboboxSelected>>", self.on_cursor_action_changed)

        ttk.Label(tab, textvariable=self.cursor_action_desc_var, wraplength=350, justify="left").grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 0))

        ttk.Label(tab, text="X").grid(row=4, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(tab, textvariable=self.cursor_target_x_var, width=10).grid(row=5, column=0, sticky="w")

        ttk.Label(tab, text="Y").grid(row=4, column=1, sticky="w", pady=(10, 0))
        ttk.Entry(tab, textvariable=self.cursor_target_y_var, width=10).grid(row=5, column=1, sticky="w")

        ttk.Button(tab, text="Считать координаты", command=self.capture_cursor_to_move_to).grid(row=5, column=2, sticky="w", padx=(8, 0))
        ttk.Button(tab, text="Выполнить сейчас", command=self.execute_cursor_action_now).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(tab, text="Добавить действие в макрос", command=self.add_selected_cursor_action).grid(row=6, column=2, columnspan=2, sticky="ew", pady=(10, 0), padx=(8, 0))

        for c in range(4):
            tab.columnconfigure(c, weight=1)

    def on_yolo_action_changed(self, _event=None):
        self.yolo_action_desc_var.set(ACTION_DEFS.get(self.yolo_action_var.get().strip(), ""))

    def on_cursor_action_changed(self, _event=None):
        self.cursor_action_desc_var.set(CURSOR_ACTION_DEFS.get(self.cursor_action_var.get().strip(), ""))

    def show_log_window(self):
        if not self.log_window.winfo_exists():
            self.log_window = LogWindow(self)
            
        self.log_window.deiconify()
        self.log_window.lift()
        self.log_window.focus_force()

    def log(self, text: str):
        self.after(0, lambda: self.log_window.append(text))

    def safe_messagebox(self, title, text, error=False):
        def _show():
            if error:
                messagebox.showerror(title, text)
            else:
                messagebox.showinfo(title, text)
        self.after(0, _show)

    def refresh_ports(self):
        ports = get_serial_ports()
        self.port_combo["values"] = ports
        if ports and self.port_var.get() not in ports:
            self.port_var.set(ports[0])
        self.log("Список COM-портов обновлён")

    def refresh_yolo_sources(self):
        try:
            monitors = self.yolo_detector.available_monitors()
            vals = [str(m["index"]) for m in monitors]
            self.monitor_combo["values"] = vals
            if vals and self.monitor_index_var.get() not in vals:
                self.monitor_index_var.set(vals[0])
        except Exception as exc:
            self.log(f"[YOLO] Не удалось получить список экранов: {exc}")

        try:
            devices = self.yolo_detector.available_devices()
            self.device_combo["values"] = devices
            if self.yolo_device_var.get() not in devices:
                self.yolo_device_var.set(devices[0])
        except Exception as exc:
            self.log(f"[YOLO] Не удалось получить список device: {exc}")

    def apply_yolo_settings(self):
        model_path = self.yolo_model_var.get().strip()
        if not model_path:
            raise RuntimeError("Не указан путь к YOLO модели")
        conf = float(self.yolo_conf_var.get().strip())
        monitor_index = int(self.monitor_index_var.get().strip())
        device = self.yolo_device_var.get().strip() or "auto"
        capture_width = int(self.yolo_capture_width_var.get().strip() or "960")

        self.yolo_detector.set_model_path(model_path)
        self.yolo_detector.set_conf(conf)
        self.yolo_detector.set_monitor_index(monitor_index)
        self.yolo_detector.set_device(device)
        self.yolo_detector.set_capture_width(capture_width)

        self.runner.stop_on_no_detection = self.stop_on_no_detection_var.get()

        self.log(f"[YOLO] model={model_path}")
        self.log(f"[YOLO] conf={conf}")
        self.log(f"[YOLO] monitor={monitor_index}")
        self.log(f"[YOLO] device={device}")
        self.log(f"[YOLO] capture_width={capture_width}")
        self.log(f"[YOLO] stop_on_no_detection={self.stop_on_no_detection_var.get()}")

    def _parse_region_from_ui(self):
        return parse_region_from_ui(
            self.region_x1_var.get(),
            self.region_y1_var.get(),
            self.region_x2_var.get(),
            self.region_y2_var.get(),
        )

    def _parse_offset_from_ui(self):
        return parse_offset_from_ui(
            self.offset_dx_var.get(),
            self.offset_dy_var.get(),
        )

    def _build_yolo_command_from_ui(self):
        return build_yolo_command_from_ui(
            self.yolo_action_var.get(),
            self.detect_class_var.get(),
            self._parse_region_from_ui(),
            self._parse_offset_from_ui(),
        )

    def _build_cursor_command_from_ui(self):
        return build_cursor_command_from_ui(
            self.cursor_action_var.get(),
            self.cursor_target_x_var.get(),
            self.cursor_target_y_var.get(),
        )

    def toggle_connection(self):
        if self.serial_manager.is_open:
            self.serial_manager.close()
            self.connect_btn.configure(text="Подключить")
            self.status_var.set("Отключено")
            self.log("COM-порт закрыт")
            return

        port = self.port_var.get().strip()
        if not port:
            messagebox.showwarning("Нет порта", "Выбери COM-порт")
            return

        try:
            baud = int(self.baud_var.get().strip())
        except Exception:
            messagebox.showwarning("Ошибка", "Baudrate должен быть числом")
            return

        try:
            self.serial_manager.open(port, baud)
            self.connect_btn.configure(text="Отключить")
            self.status_var.set(f"Подключено: {port} @ {baud}")
            self.log(f"Подключено к {port} @ {baud}")
        except PermissionError:
            msg = f"Не удалось открыть {port}. Скорее всего порт занят Arduino IDE, Serial Monitor или другой программой."
            messagebox.showerror("Ошибка подключения", msg)
            self.log(f"[ОШИБКА] {msg}")
        except Exception as exc:
            messagebox.showerror("Ошибка подключения", str(exc))
            self.log(f"[ОШИБКА] {exc}")

    def add_step(self):
        editor = StepEditor(self, "Добавить шаг")
        self.wait_window(editor)
        if editor.result:
            self.steps.append(editor.result)
            self.refresh_tree()

    def edit_step(self):
        idx = self.get_selected_index()
        if idx is None:
            return
        editor = StepEditor(self, "Изменить шаг", self.steps[idx])
        self.wait_window(editor)
        if editor.result:
            self.steps[idx] = editor.result
            self.refresh_tree(select_index=idx)

    def delete_step(self):
        idx = self.get_selected_index()
        if idx is None:
            return
        del self.steps[idx]
        self.refresh_tree(select_index=min(idx, len(self.steps) - 1))

    def clear_steps(self):
        if not self.steps:
            return
        if messagebox.askyesno("Очистить", "Удалить все шаги?"):
            self.steps.clear()
            self.refresh_tree()

    def move_step(self, delta: int):
        idx = self.get_selected_index()
        if idx is None:
            return
        new_idx = idx + delta
        if new_idx < 0 or new_idx >= len(self.steps):
            return
        self.steps[idx], self.steps[new_idx] = self.steps[new_idx], self.steps[idx]
        self.refresh_tree(select_index=new_idx)

    def refresh_tree(self, select_index: int | None = None):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, step in enumerate(self.steps):
            self.tree.insert("", "end", iid=str(i), values=(step.command, step.delay_ms, "Да" if step.expect_response else "Нет"))
        if select_index is not None and 0 <= select_index < len(self.steps):
            iid = str(select_index)
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)

    def get_selected_index(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Шаг не выбран", "Выбери шаг в списке")
            return None
        return int(sel[0])

    def import_steps(self):
        path = filedialog.askopenfilename(title="Импорт набора действий", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            steps_raw = data.get("steps", data)
            self.steps = [
                MacroStep(
                    command=item["command"],
                    delay_ms=int(item.get("delay_ms", DEFAULT_STEP_DELAY_MS)),
                    expect_response=bool(item.get("expect_response", True)),
                )
                for item in steps_raw
            ]

            self.hotkey_var.set(data.get("hotkey", ""))
            if data.get("yolo_model"): self.yolo_model_var.set(str(data["yolo_model"]))
            if data.get("yolo_conf") is not None: self.yolo_conf_var.set(str(data["yolo_conf"]))
            if data.get("monitor_index") is not None: self.monitor_index_var.set(str(data["monitor_index"]))
            if data.get("yolo_device"): self.yolo_device_var.set(str(data["yolo_device"]))
            if data.get("capture_width") is not None: self.yolo_capture_width_var.set(str(data["capture_width"]))
            if data.get("stop_on_no_detection") is not None: self.stop_on_no_detection_var.set(bool(data["stop_on_no_detection"]))

            self.apply_yolo_settings()

            hotkey = self.hotkey_var.get().strip()
            if hotkey:
                try:
                    self.hotkey_manager.register(hotkey)
                except Exception as exc:
                    self.hotkey_status_var.set(f"Не удалось назначить хоткей: {exc}")
                    self.log(f"[ОШИБКА] Не удалось назначить хоткей из файла: {exc}")

            self.refresh_tree(select_index=0 if self.steps else None)
            self.log(f"Импортировано шагов: {len(self.steps)} из {path}")
        except Exception as exc:
            messagebox.showerror("Ошибка импорта", str(exc))

    def export_steps(self):
        path = filedialog.asksaveasfilename(
            title="Экспорт набора действий",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile="macro_steps.json",
        )
        if not path:
            return

        try:
            payload = {
                "app": APP_TITLE,
                "version": APP_VERSION,
                "hotkey": self.hotkey_var.get().strip(),
                "yolo_model": self.yolo_model_var.get().strip(),
                "yolo_conf": self.yolo_conf_var.get().strip(),
                "monitor_index": self.monitor_index_var.get().strip(),
                "yolo_device": self.yolo_device_var.get().strip(),
                "capture_width": self.yolo_capture_width_var.get().strip(),
                "stop_on_no_detection": self.stop_on_no_detection_var.get(),
                "steps": [step.__dict__ for step in self.steps],
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self.log(f"Экспортировано шагов: {len(self.steps)} в {path}")
        except Exception as exc:
            messagebox.showerror("Ошибка экспорта", str(exc))

    def show_model_classes(self):
        try:
            self.apply_yolo_settings()
            classes = self.yolo_detector.available_model_classes()
            self.class_combo["values"] = classes
            self.log(f"[YOLO] Классов в модели: {len(classes)}")
            self.log("[YOLO] " + ", ".join(classes[:250]))
        except Exception as exc:
            self.log(f"[ОШИБКА] {exc}")
            self.safe_messagebox("Ошибка", str(exc), error=True)

    def add_selected_yolo_action(self):
        try:
            command = self._build_yolo_command_from_ui()
        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc))
            return
        self.steps.append(make_macro_step(command))
        self.refresh_tree(select_index=len(self.steps) - 1)
        self.log(f"[MACRO] Добавлен шаг: {command}")

    def add_selected_cursor_action(self):
        try:
            command = self._build_cursor_command_from_ui()
        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc))
            return
        self.steps.append(make_macro_step(command))
        self.refresh_tree(select_index=len(self.steps) - 1)
        self.log(f"[MACRO] Добавлен шаг: {command}")

    def _execute_quick_local(self, cmd: str):
        result, message = self.runner.execute_step(MacroStep(command=cmd, delay_ms=0, expect_response=False))
        self.log(message)
        return result

    def send_quick(self, cmd: str):
        if not self.serial_manager.is_open:
            messagebox.showwarning("Нет подключения", "Сначала подключись к COM-порту")
            return

        def worker():
            try:
                self.apply_yolo_settings()
                self._execute_quick_local(cmd)
            except Exception as exc:
                self.log(f"[ОШИБКА] {exc}")
                self.safe_messagebox("Ошибка", str(exc), error=True)

        threading.Thread(target=worker, daemon=True).start()

    def send_ping(self):
        self.send_quick("PING")

    def send_quick_entry(self):
        cmd = self.quick_command_var.get().strip()
        if cmd:
            self.send_quick(cmd)

    def execute_cursor_action_now(self):
        if not self.serial_manager.is_open:
            messagebox.showwarning("Нет подключения", "Сначала подключись к COM-порту")
            return
        try:
            cmd = self._build_cursor_command_from_ui()
        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc))
            return
        self.send_quick(cmd)

    def start_macro(self):
        if not self.serial_manager.is_open:
            messagebox.showwarning("Нет подключения", "Сначала подключись к COM-порту")
            return
        if not self.steps:
            messagebox.showwarning("Пусто", "Добавь хотя бы один шаг")
            return
        try:
            cycles = int(self.cycles_var.get().strip())
            if cycles <= 0:
                raise ValueError
        except Exception:
            messagebox.showwarning("Ошибка", "Количество циклов должно быть целым числом > 0")
            return

        try:
            self._manual_stop_requested = False
            self.apply_yolo_settings()
            self.progress_var.set(0)
            self.status_var.set("Выполняется...")
            self.runner.start(list(self.steps), cycles)
            self.log(f"Запуск макроса: шагов={len(self.steps)}, циклов={cycles}")
        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc))

    def stop_macro(self):
        if self.runner.running:
            self._manual_stop_requested = True
            self.runner.stop()
            self.log("Останов макроса запрошен")
            self.status_var.set("Остановка...")

    def on_macro_finished(self, reason: str):
        self.after(0, lambda: self._on_macro_finished_ui(reason))

    def _on_macro_finished_ui(self, reason: str):
        if reason == RunResult.COMPLETED:
            self.status_var.set("Готов")
            self.log("Макрос завершён")
        elif reason == RunResult.NO_DETECTION:
            self.status_var.set("Остановлено: нет детекта")
            self.log("Макрос остановлен: не найден объект")
        elif reason == RunResult.STOPPED:
            self.status_var.set("Остановлено")
            self.log("Макрос остановлен вручную")
        else:
            self.status_var.set("Ошибка")
            self.log("Макрос завершился с ошибкой")

        if self.queue_enabled_var.get() and self.queue_auto_run_var.get():
            if reason in (RunResult.COMPLETED, RunResult.NO_DETECTION) and not self._manual_stop_requested:
                self.start_next_script_from_queue()

    def set_progress(self, done: int, total: int):
        def _set():
            pct = 0 if total <= 0 else (done / total) * 100.0
            self.progress_var.set(pct)
            self.status_var.set(f"Выполнение: {done}/{total}")
        self.after(0, _set)

    def pick_script_folder(self):
        path = filedialog.askdirectory(title="Выбери папку со скриптами")
        if not path:
            return
        self.queue_folder_var.set(path)
        self.reload_script_folder()

    def reload_script_folder(self):
        folder = self.queue_folder_var.get().strip()
        if not folder:
            self.queue_list.delete(0, "end")
            return
        try:
            self.queue_manager.load_folder(folder)
            self.queue_list.delete(0, "end")
            for file_path in self.queue_manager.files:
                self.queue_list.insert("end", os.path.basename(file_path))
            self.log(f"[QUEUE] Загружено скриптов: {len(self.queue_manager.files)}")
        except Exception as exc:
            self.safe_messagebox("Ошибка", str(exc), error=True)

    def start_next_script_from_queue(self):
        try:
            folder = self.queue_folder_var.get().strip()
            if not folder:
                return
            if not self.queue_manager.files or self.queue_manager.folder_path != folder:
                self.reload_script_folder()
            self.queue_manager.folder_cycles = max(1, int(self.queue_cycles_var.get().strip() or "1"))
            self.queue_manager.enabled = self.queue_enabled_var.get()
            self.queue_manager.auto_run_next = self.queue_auto_run_var.get()

            next_file = self.queue_manager.next_file()
            if not next_file:
                self.log("[QUEUE] Очередь скриптов закончилась")
                return

            self.steps = self.queue_manager.load_steps_from_file(next_file)
            self.refresh_tree(select_index=0 if self.steps else None)
            self.log(f"[QUEUE] Автоматически загружен следующий скрипт: {os.path.basename(next_file)}")
            self.after(100, self.start_macro)
        except Exception as exc:
            self.log(f"[QUEUE][ОШИБКА] {exc}")
            self.safe_messagebox("Ошибка очереди", str(exc), error=True)

    def start_cursor_tracking(self):
        self._update_cursor_position_loop()

    def _update_cursor_position_loop(self):
        try:
            x, y = CursorController.get_position()
            self.cursor_live_var.set(f"Курсор: X={x} Y={y}")
        except Exception:
            self.cursor_live_var.set("Курсор: недоступно")
        self.after(100, self._update_cursor_position_loop)

    def capture_cursor_to_move_to(self):
        try:
            x, y = CursorController.get_position()
            self.cursor_target_x_var.set(str(x))
            self.cursor_target_y_var.set(str(y))
            self.log(f"[CURSOR] Считаны координаты MOVE_TO: {x}, {y}")
        except Exception as exc:
            self.safe_messagebox("Ошибка", str(exc), error=True)

    def capture_cursor_to_region(self, mode: str):
        try:
            x, y = CursorController.get_position()
            if mode == "x1y1":
                self.region_x1_var.set(str(x))
                self.region_y1_var.set(str(y))
                self.log(f"[REGION] Считаны X1/Y1: {x}, {y}")
            elif mode == "x2y2":
                self.region_x2_var.set(str(x))
                self.region_y2_var.set(str(y))
                self.log(f"[REGION] Считаны X2/Y2: {x}, {y}")
        except Exception as exc:
            self.safe_messagebox("Ошибка", str(exc), error=True)

    def quick_detect_list(self):
        def worker():
            try:
                self.apply_yolo_settings()
                cmd = "DETECT_LIST"
                region = self._parse_region_from_ui()
                if region is not None:
                    cmd += " " + " ".join(str(v) for v in region)
                self._execute_quick_local(cmd)
            except Exception as exc:
                self.log(f"[ОШИБКА] {exc}")
                self.safe_messagebox("Ошибка", str(exc), error=True)
        threading.Thread(target=worker, daemon=True).start()

    def pick_yolo_model(self):
        path = filedialog.askopenfilename(title="Выбери YOLO модель", filetypes=[("PyTorch model", "*.pt"), ("All files", "*.*")])
        if path:
            self.yolo_model_var.set(path)

    def toggle_hotkey_listen(self):
        self.listen_hotkey_active = not self.listen_hotkey_active
        self.listen_modifiers.clear()
        if self.listen_hotkey_active:
            self.listen_btn.configure(text="Отмена")
            self.hotkey_status_var.set("Нажми комбинацию клавиш.")
            self.log("Режим прослушивания горячей клавиши включён")
            self.hotkey_entry.focus_set()
        else:
            self.listen_btn.configure(text="Слушать")
            self.hotkey_status_var.set("Горячая клавиша не назначена" if not self.hotkey_var.get().strip() else f"Выбрано: {self.hotkey_var.get().strip()}")
            self.log("Режим прослушивания горячей клавиши выключен")

    def on_key_press_for_hotkey_listen(self, event):
        if not self.listen_hotkey_active:
            return
        keysym = (event.keysym or "").upper()
        modifier_map = {
            "CONTROL_L": "CTRL", "CONTROL_R": "CTRL", "CTRL_L": "CTRL", "CTRL_R": "CTRL",
            "ALT_L": "ALT", "ALT_R": "ALT",
            "SHIFT_L": "SHIFT", "SHIFT_R": "SHIFT",
            "SUPER_L": "WIN", "SUPER_R": "WIN", "WIN_L": "WIN", "WIN_R": "WIN",
        }
        special_map = {
            "RETURN": "ENTER", "ESCAPE": "ESC", "PRIOR": "PAGEUP", "NEXT": "PAGEDOWN",
            "SPACE": "SPACE", "UP": "UP", "DOWN": "DOWN", "LEFT": "LEFT", "RIGHT": "RIGHT",
            "HOME": "HOME", "END": "END", "INSERT": "INSERT", "DELETE": "DELETE", "TAB": "TAB",
        }
        if keysym in modifier_map:
            self.listen_modifiers.add(modifier_map[keysym])
            return "break"

        key_name = special_map.get(keysym, keysym)
        if len(key_name) == 1:
            key_name = key_name.upper()
        parts = [m for m in ("CTRL", "ALT", "SHIFT", "WIN") if m in self.listen_modifiers]
        parts.append(key_name)
        hotkey = HotkeyManager.normalize_hotkey_text("+".join(parts))
        self.hotkey_var.set(hotkey)
        self.hotkey_status_var.set(f"Выбрано: {hotkey}")
        self.log(f"Выбрана горячая клавиша: {hotkey}")
        self.listen_hotkey_active = False
        self.listen_modifiers.clear()
        self.listen_btn.configure(text="Слушать")
        return "break"

    def on_key_release_for_hotkey_listen(self, event):
        if not self.listen_hotkey_active:
            return
        keysym = (event.keysym or "").upper()
        modifier_map = {
            "CONTROL_L": "CTRL", "CONTROL_R": "CTRL", "CTRL_L": "CTRL", "CTRL_R": "CTRL",
            "ALT_L": "ALT", "ALT_R": "ALT", "SHIFT_L": "SHIFT", "SHIFT_R": "SHIFT",
            "SUPER_L": "WIN", "SUPER_R": "WIN", "WIN_L": "WIN", "WIN_R": "WIN",
        }
        if keysym in modifier_map:
            self.listen_modifiers.discard(modifier_map[keysym])
            return "break"

    def apply_hotkey(self):
        hotkey = self.hotkey_var.get().strip()
        if not hotkey:
            messagebox.showwarning("Пусто", "Сначала укажи горячую клавишу")
            return
        try:
            self.hotkey_manager.register(hotkey)
        except Exception as exc:
            messagebox.showerror("Ошибка хоткея", str(exc))
            self.hotkey_status_var.set(f"Ошибка: {exc}")
            self.log(f"[ОШИБКА] Хоткей: {exc}")

    def clear_hotkey(self):
        self.hotkey_manager.unregister()
        self.hotkey_var.set("")
        self.hotkey_status_var.set("Горячая клавиша не назначена")
        self.log("Горячая клавиша сброшена")

    def on_hotkey_registered(self, normalized: str):
        self.hotkey_status_var.set(f"Назначено: {normalized}")
        self.log(f"Глобальная горячая клавиша назначена: {normalized}")

    def on_hotkey_register_error(self, normalized: str):
        self.hotkey_status_var.set(f"Не удалось назначить: {normalized}")
        self.log(f"[ОШИБКА] Не удалось зарегистрировать горячую клавишу: {normalized}")
        self.safe_messagebox("Ошибка хоткея", f"Не удалось зарегистрировать горячую клавишу: {normalized}", error=True)

    def on_hotkey_pressed(self):
        self.log("Сработала горячая клавиша")
        if self.runner.running:
            self.stop_macro()
        else:
            self.start_macro()

    def log_start_help(self):
        self.log("=== Программа запущена ===")
        self.log("UI разбит на вкладки: YOLO / Выполнение / Курсор.")
        self.log("Галочка 'Если нет детекта — прервать текущий скрипт' находится во вкладке YOLO.")
        self.log("Если включена очередь папки, после завершения или остановки по no_detection может стартовать следующий JSON.")
        self.log("Область в YOLO работает как фильтр после общего поиска по монитору.")

    def on_close(self):
        try:
            self.runner.stop()
            self.hotkey_manager.unregister()
            self.serial_manager.close()
            try:
                self.log_window.destroy()
            except Exception:
                pass
        finally:
            self.destroy()
