import time
import tkinter as tk
from tkinter import ttk, messagebox

from .models import MacroStep, DEFAULT_STEP_DELAY_MS


class LogWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Журнал")
        self.geometry("900x420")
        self.minsize(680, 260)
        
        self.protocol("WM_DELETE_WINDOW", self.withdraw)

        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)

        self.text = tk.Text(root, wrap="word")
        self.text.grid(row=0, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(root, orient="vertical", command=self.text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scroll.set)

        btns = ttk.Frame(root)
        btns.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(btns, text="Очистить", command=self.clear).pack(side="left")
        ttk.Button(btns, text="Скрыть", command=self.withdraw).pack(side="left", padx=(8, 0))

        root.rowconfigure(0, weight=1)
        root.columnconfigure(0, weight=1)

    def append(self, text: str):
        timestamp = time.strftime("%H:%M:%S")
        self.text.insert("end", f"[{timestamp}] {text}\n")
        self.text.see("end")

    def clear(self):
        self.text.delete("1.0", "end")


class HelpWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Справка")
        self.geometry("920x560")
        self.minsize(720, 420)

        txt = tk.Text(self, wrap="word")
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        txt.insert(
            "1.0",
            "КОМАНДЫ УСТРОЙСТВА\n\n"

            "PING\n"
            "Проверка связи. Ответ: PONG\n\n"

            "VERSION\n"
            "Показать версию прошивки.\n\n"

            "RELEASE_ALL\n"
            "Отпустить все зажатые клавиши и кнопки мыши. Полезно, если что-то зависло.\n\n"

            "KEY_DOWN CTRL\n"
            "Зажать клавишу. Например CTRL, SHIFT, ALT, W, A, ENTER.\n\n"

            "KEY_UP CTRL\n"
            "Отпустить клавишу. Это НЕ KEY_RELEASE. Правильная команда именно KEY_UP.\n\n"

            "KEY_PRESS ENTER\n"
            "Нажать и отпустить клавишу.\n\n"

            "HOTKEY CTRL C\n"
            "Нажать комбинацию: зажать CTRL, нажать C, отпустить CTRL.\n\n"

            "TYPE_TEXT hello\n"
            "Напечатать текст через клавиатуру.\n\n"

            "MOUSE_MOVE 10 5\n"
            "Сдвинуть мышь относительно текущей позиции. X/Y не абсолютные, а относительные.\n\n"

            "MOUSE_SCROLL -3\n"
            "Прокрутка колеса мыши. Отрицательное значение — вниз, положительное — вверх.\n\n"

            "MOUSE_CLICK LEFT\n"
            "Клик мышью. Кнопки: LEFT, RIGHT, MIDDLE.\n\n"

            "MOUSE_PRESS LEFT\n"
            "Зажать кнопку мыши.\n\n"

            "MOUSE_RELEASE LEFT\n"
            "Отпустить кнопку мыши.\n\n"

            "КЛИЕНТСКИЕ КОМАНДЫ\n\n"

            "MOVE_TO 500 300\n"
            "Навести курсор в абсолютные координаты экрана. Это делает Python-клиент через серию MOUSE_MOVE.\n\n"

            "DETECT_LIST\n"
            "Показать в журнале найденные YOLO-объекты.\n\n"

            "DETECT_MOVE Fish\n"
            "Найти объект класса Fish и навести курсор в центр bbox.\n\n"

            "DETECT_CLICK Fish\n"
            "Найти объект Fish, навести курсор и кликнуть.\n\n"

            "DETECT_DOUBLE_CLICK Fish\n"
            "Найти объект Fish и сделать двойной клик.\n\n"

            "DETECT_NEAREST_CURSOR Fish\n"
            "Выбрать объект Fish, ближайший к текущему курсору.\n\n"

            "DETECT_NEAREST_SCREEN Fish\n"
            "Выбрать объект Fish, ближайший к центру экрана или заданной области.\n\n"

            "DETECT_MOVE_OFFSET Fish 10 -5\n"
            "Навести курсор не в центр объекта, а со смещением dx/dy.\n\n"

            "DETECT_CLICK_OFFSET Fish 0 12\n"
            "Кликнуть по объекту со смещением от центра bbox.\n\n"

            "ОБЛАСТЬ ДЕТЕКЦИИ\n\n"

            "К YOLO-командам можно добавить область:\n"
            "DETECT_MOVE Fish 100 100 900 700\n"
            "DETECT_CLICK Fish 100 100 900 700\n"
            "DETECT_LIST 100 100 900 700\n\n"

            "Формат области: X1 Y1 X2 Y2.\n"
            "Область работает как фильтр: сначала YOLO ищет объекты на экране, потом клиент оставляет только те, чей центр находится внутри области.\n\n"

            "ВАЖНО\n\n"

            "- KEY_RELEASE не существует. Используй KEY_UP.\n"
            "- MOUSE_MOVE использует относительное смещение, а MOVE_TO — абсолютные координаты.\n"
            "- DETECT_* команды выполняются клиентом, а не прошивкой устройства.\n"
            "- Для DETECT_* нужна загруженная YOLO-модель с нужными классами.\n"
            "- Если включена галочка 'Если нет детекта — прервать', макрос остановится при NOT_FOUND.\n"
        )
        txt.configure(state="disabled")


class StepEditor(tk.Toplevel):
    def __init__(self, master, title: str, initial: MacroStep | None = None):
        super().__init__(master)
        self.title(title)
        self.geometry("760x190")
        self.resizable(True, False)
        self.result = None
        self.transient(master)
        self.grab_set()

        self.command_var = tk.StringVar(value=initial.command if initial else "")
        self.delay_var = tk.StringVar(value=str(initial.delay_ms if initial else DEFAULT_STEP_DELAY_MS))
        self.expect_var = tk.BooleanVar(value=initial.expect_response if initial else True)

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Команда").grid(row=0, column=0, sticky="w")
        cmd_entry = ttk.Entry(frm, textvariable=self.command_var)
        cmd_entry.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 8))

        ttk.Label(frm, text="Задержка после шага (мс)").grid(row=2, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.delay_var, width=16).grid(row=3, column=0, sticky="w", pady=(0, 8))

        ttk.Checkbutton(frm, text="Ждать ответ от устройства", variable=self.expect_var).grid(row=3, column=1, sticky="w")
        ttk.Button(frm, text="Справка", command=lambda: HelpWindow(self)).grid(row=3, column=2, sticky="e")

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=3, sticky="e", pady=(8, 0))
        ttk.Button(btns, text="OK", command=self.on_ok).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="left")

        frm.columnconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)
        frm.columnconfigure(2, weight=1)

        cmd_entry.focus_set()
        self.bind("<Return>", lambda e: self.on_ok())
        self.bind("<Escape>", lambda e: self.destroy())

    def on_ok(self):
        command = self.command_var.get().strip()
        if not command:
            messagebox.showwarning("Пустая команда", "Нужно указать команду")
            return
        try:
            delay_ms = int(self.delay_var.get().strip())
            if delay_ms < 0:
                raise ValueError
        except Exception:
            messagebox.showwarning("Ошибка", "Задержка должна быть целым числом >= 0")
            return
        self.result = MacroStep(command=command, delay_ms=delay_ms, expect_response=self.expect_var.get())
        self.destroy()
