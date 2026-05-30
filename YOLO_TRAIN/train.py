import os
import sys
import threading
import queue
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


def detect_devices():
    """Возвращает список доступных устройств для обучения."""
    devices = ["cpu"]

    try:
        import torch

        if torch.cuda.is_available():
            count = torch.cuda.device_count()
            for i in range(count):
                name = torch.cuda.get_device_name(i)
                devices.append(f"cuda:{i} ({name})")

        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            devices.append("mps")
    except Exception:
        pass

    return devices


class YoloTrainerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("YOLO Trainer GUI")
        self.root.geometry("980x760")
        self.root.minsize(900, 700)

        self.log_queue = queue.Queue()
        self.training_thread = None
        self.stop_requested = False
        self.process = None

        self.devices = detect_devices()
        self.create_variables()
        self.create_widgets()
        self.poll_log_queue()

    def create_variables(self):
        self.dataset_yaml = tk.StringVar()
        self.model_source = tk.StringVar(value="yolov8n.pt")
        self.project_dir = tk.StringVar(value="runs/train")
        self.run_name = tk.StringVar(value="exp")

        self.epochs = tk.IntVar(value=50)
        self.imgsz = tk.IntVar(value=640)
        self.batch = tk.IntVar(value=16)
        self.workers = tk.IntVar(value=8)
        self.patience = tk.IntVar(value=30)
        self.seed = tk.IntVar(value=42)

        self.device_display = tk.StringVar(value=self.devices[0])
        self.optimizer = tk.StringVar(value="auto")
        self.task = tk.StringVar(value="detect")

        self.cache = tk.BooleanVar(value=False)
        self.amp = tk.BooleanVar(value=True)
        self.pretrained = tk.BooleanVar(value=True)
        self.cos_lr = tk.BooleanVar(value=False)
        self.val = tk.BooleanVar(value=True)
        self.save = tk.BooleanVar(value=True)
        self.verbose = tk.BooleanVar(value=True)

    def create_widgets(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        title = ttk.Label(
            main,
            text="Обучение YOLO через GUI",
            font=("Arial", 16, "bold")
        )
        title.pack(anchor="w", pady=(0, 10))

        info = ttk.Label(
            main,
            text=(
                "Скрипт использует пакет ultralytics. "
                "Для датасета нужен путь к data.yaml. "
                "Можно выбрать устройство обучения: CPU / CUDA / MPS."
            ),
            wraplength=920,
            justify="left"
        )
        info.pack(anchor="w", pady=(0, 14))

        form = ttk.LabelFrame(main, text="Параметры", padding=12)
        form.pack(fill="x")

        self._row_file_picker(form, 0, "data.yaml", self.dataset_yaml, self.browse_dataset)
        self._row_file_picker(form, 1, "Модель / веса (.pt или .yaml)", self.model_source, self.browse_model)
        self._row_dir_picker(form, 2, "Папка проекта", self.project_dir, self.browse_project_dir)
        self._row_entry(form, 3, "Имя запуска", self.run_name)

        self._row_combo(form, 4, "Задача", self.task, ["detect", "segment", "classify", "pose", "obb"])
        self._row_combo(form, 5, "Устройство", self.device_display, self.devices)
        self._row_combo(form, 6, "Optimizer", self.optimizer, ["auto", "SGD", "Adam", "AdamW", "RMSProp"])

        grid2 = ttk.Frame(form)
        grid2.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        for i in range(8):
            grid2.columnconfigure(i, weight=1)

        self._small_spin(grid2, 0, "Epochs", self.epochs, 1, 10000)
        self._small_spin(grid2, 1, "Img size", self.imgsz, 32, 4096, increment=32)
        self._small_spin(grid2, 2, "Batch", self.batch, -1, 1024)
        self._small_spin(grid2, 3, "Workers", self.workers, 0, 64)
        self._small_spin(grid2, 4, "Patience", self.patience, 0, 1000)
        self._small_spin(grid2, 5, "Seed", self.seed, 0, 999999)

        options = ttk.LabelFrame(main, text="Опции", padding=12)
        options.pack(fill="x", pady=(12, 0))

        ttk.Checkbutton(options, text="Cache dataset", variable=self.cache).grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ttk.Checkbutton(options, text="AMP / mixed precision", variable=self.amp).grid(row=0, column=1, sticky="w", padx=6, pady=4)
        ttk.Checkbutton(options, text="Pretrained", variable=self.pretrained).grid(row=0, column=2, sticky="w", padx=6, pady=4)
        ttk.Checkbutton(options, text="Cosine LR", variable=self.cos_lr).grid(row=0, column=3, sticky="w", padx=6, pady=4)
        ttk.Checkbutton(options, text="Validation", variable=self.val).grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ttk.Checkbutton(options, text="Save checkpoints", variable=self.save).grid(row=1, column=1, sticky="w", padx=6, pady=4)
        ttk.Checkbutton(options, text="Verbose log", variable=self.verbose).grid(row=1, column=2, sticky="w", padx=6, pady=4)

        btns = ttk.Frame(main)
        btns.pack(fill="x", pady=(12, 0))

        self.start_btn = ttk.Button(btns, text="Запустить обучение", command=self.start_training)
        self.start_btn.pack(side="left")

        self.stop_btn = ttk.Button(btns, text="Остановить", command=self.stop_training, state="disabled")
        self.stop_btn.pack(side="left", padx=8)

        ttk.Button(btns, text="Очистить лог", command=self.clear_log).pack(side="left")
        ttk.Button(btns, text="Показать команду", command=self.show_command_preview).pack(side="right")

        log_frame = ttk.LabelFrame(main, text="Лог", padding=8)
        log_frame.pack(fill="both", expand=True, pady=(12, 0))

        self.log_text = tk.Text(log_frame, wrap="word", height=24)
        self.log_text.pack(side="left", fill="both", expand=True)
        self.log_text.configure(font=("Consolas", 10))

        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _row_entry(self, parent, row, label, variable):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=6)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", pady=6)
        parent.columnconfigure(1, weight=1)

    def _row_file_picker(self, parent, row, label, variable, command):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=6)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", pady=6)
        ttk.Button(parent, text="Выбрать", command=command).grid(row=row, column=2, padx=(8, 0), pady=6)
        parent.columnconfigure(1, weight=1)

    def _row_dir_picker(self, parent, row, label, variable, command):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=6)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", pady=6)
        ttk.Button(parent, text="Выбрать", command=command).grid(row=row, column=2, padx=(8, 0), pady=6)
        parent.columnconfigure(1, weight=1)

    def _row_combo(self, parent, row, label, variable, values):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=6)
        combo = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly")
        combo.grid(row=row, column=1, sticky="ew", pady=6)
        parent.columnconfigure(1, weight=1)

    def _small_spin(self, parent, col, label, variable, frm, to, increment=1):
        cell = ttk.Frame(parent)
        cell.grid(row=0, column=col, sticky="ew", padx=6)
        ttk.Label(cell, text=label).pack(anchor="w")
        ttk.Spinbox(cell, from_=frm, to=to, increment=increment, textvariable=variable, width=12).pack(anchor="w", pady=(4, 0))

    def browse_dataset(self):
        path = filedialog.askopenfilename(
            title="Выберите data.yaml",
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")]
        )
        if path:
            self.dataset_yaml.set(path)

    def browse_model(self):
        path = filedialog.askopenfilename(
            title="Выберите модель или веса",
            filetypes=[("Model files", "*.pt *.yaml *.yml"), ("All files", "*.*")]
        )
        if path:
            self.model_source.set(path)

    def browse_project_dir(self):
        path = filedialog.askdirectory(title="Выберите папку проекта")
        if path:
            self.project_dir.set(path)

    def normalize_device(self):
        value = self.device_display.get().strip()
        if value.startswith("cuda:"):
            return value.split(" ")[0]
        return value

    def build_command(self):
        dataset = self.dataset_yaml.get().strip()
        model = self.model_source.get().strip()
        project = self.project_dir.get().strip()
        name = self.run_name.get().strip()

        if not dataset:
            raise ValueError("Укажите путь к data.yaml")
        if not os.path.exists(dataset):
            raise ValueError("Файл data.yaml не найден")
        if not model:
            raise ValueError("Укажите модель или веса")
        if not name:
            raise ValueError("Укажите имя запуска")

        command = [
            sys.executable,
            "-m",
            "ultralytics",
            "train",
            f"task={self.task.get()}",
            f"data={dataset}",
            f"model={model}",
            f"epochs={self.epochs.get()}",
            f"imgsz={self.imgsz.get()}",
            f"batch={self.batch.get()}",
            f"workers={self.workers.get()}",
            f"project={project}",
            f"name={name}",
            f"device={self.normalize_device()}",
            f"optimizer={self.optimizer.get()}",
            f"patience={self.patience.get()}",
            f"seed={self.seed.get()}",
            f"cache={str(self.cache.get())}",
            f"amp={str(self.amp.get())}",
            f"pretrained={str(self.pretrained.get())}",
            f"cos_lr={str(self.cos_lr.get())}",
            f"val={str(self.val.get())}",
            f"save={str(self.save.get())}",
            f"verbose={str(self.verbose.get())}",
        ]
        return command

    def show_command_preview(self):
        try:
            cmd = self.build_command()
            preview = " ".join(f'"{x}"' if " " in x else x for x in cmd)
            self.append_log("\n[Команда]\n" + preview + "\n")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def start_training(self):
        if self.training_thread and self.training_thread.is_alive():
            messagebox.showwarning("Внимание", "Обучение уже запущено")
            return

        try:
            cmd = self.build_command()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
            return

        self.stop_requested = False
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.append_log("\n=== Запуск обучения ===\n")
        self.append_log("Команда: " + " ".join(cmd) + "\n\n")

        self.training_thread = threading.Thread(target=self.run_training, args=(cmd,), daemon=True)
        self.training_thread.start()

    def run_training(self, cmd):
        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"

            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=env
            )

            for line in self.process.stdout:
                if self.stop_requested:
                    break
                self.log_queue.put(line)

            if self.stop_requested and self.process.poll() is None:
                self.process.terminate()
                self.log_queue.put("\n[INFO] Отправлен сигнал остановки...\n")

            return_code = self.process.wait()
            if not self.stop_requested:
                self.log_queue.put(f"\n=== Обучение завершено. Код возврата: {return_code} ===\n")
            else:
                self.log_queue.put("\n=== Обучение остановлено пользователем ===\n")

        except FileNotFoundError:
            self.log_queue.put(
                "\n[ERROR] Не найден Python или модуль ultralytics. "
                "Установите зависимости: pip install ultralytics torch torchvision\n"
            )
        except Exception as e:
            self.log_queue.put(f"\n[ERROR] {e}\n")
        finally:
            self.process = None
            self.root.after(0, self.on_training_finished)

    def stop_training(self):
        self.stop_requested = True
        self.append_log("\n[INFO] Остановка обучения запрошена пользователем...\n")
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
            except Exception as e:
                self.append_log(f"[WARN] Не удалось остановить процесс: {e}\n")

    def on_training_finished(self):
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")

    def poll_log_queue(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.append_log(line)
        except queue.Empty:
            pass
        self.root.after(100, self.poll_log_queue)

    def append_log(self, text):
        self.log_text.insert("end", text)
        self.log_text.see("end")

    def clear_log(self):
        self.log_text.delete("1.0", "end")


def main():
    try:
        import ultralytics  # noqa: F401
    except Exception:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Не хватает зависимостей",
            "Не установлен пакет ultralytics.\n\n"
            "Установите зависимости командой:\n"
            "pip install ultralytics torch torchvision"
        )
        root.destroy()
        return

    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass

    app = YoloTrainerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
