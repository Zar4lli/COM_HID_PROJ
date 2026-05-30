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
            "Основные команды:\n"
            "PING\nVERSION\nRELEASE_ALL\nKEY_DOWN CTRL\nKEY_UP CTRL\nKEY_PRESS ENTER\nMOUSE_MOVE 10 5\nMOVE_TO 500 300\n"
            "MOUSE_CLICK LEFT\nMOUSE_CLICK RIGHT\nMOUSE_PRESS LEFT\nMOUSE_RELEASE LEFT\nMOUSE_PRESS RIGHT\nMOUSE_RELEASE RIGHT\n\n"
            "YOLO команды:\n"
            "DETECT_MOVE Worm\nDETECT_CLICK Worm\nDETECT_DOUBLE_CLICK Worm\n"
            "DETECT_NEAREST_CURSOR Worm\nDETECT_NEAREST_SCREEN Worm\n"
            "DETECT_MOVE_OFFSET Worm 10 -5\nDETECT_CLICK_OFFSET Worm 0 12\nDETECT_LIST\n\n"
            "С областью:\n"
            "DETECT_MOVE Worm 100 100 900 700\n"
            "DETECT_CLICK Worm 100 100 900 700\n"
            "DETECT_NEAREST_CURSOR Worm 100 100 900 700\n"
            "DETECT_NEAREST_SCREEN Worm 100 100 900 700\n"
            "DETECT_MOVE_OFFSET Worm 10 -5 100 100 900 700\n"
            "DETECT_CLICK_OFFSET Worm 0 12 100 100 900 700\n"
            "DETECT_LIST 100 100 900 700\n\n"
            "Важно:\n"
            "- область работает как фильтр: сначала ищем на всём мониторе, потом отсекаем bbox по центру внутри области.\n"
            "- если включена галочка 'Если нет детекта — прервать', текущий набор шагов остановится, и при включённой очереди может открыться следующий скрипт.\n"
            "- очередь папки запускает следующий .json по порядку.\n"
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
