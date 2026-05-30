import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import cv2
from ultralytics import YOLO


class YoloGuiApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("YOLO Detection GUI")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)

        self.model = None
        self.model_path = ""
        self.image_path = ""
        self.original_bgr = None
        self.result_bgr = None

        self._build_ui()

    def _build_ui(self) -> None:
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(top_frame, text="Загрузить модель (.pt)", command=self.load_model).grid(
            row=0, column=0, padx=5, pady=5, sticky="ew"
        )
        self.model_label = ttk.Label(top_frame, text="Модель не выбрана")
        self.model_label.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        ttk.Button(top_frame, text="Загрузить изображение", command=self.load_image).grid(
            row=1, column=0, padx=5, pady=5, sticky="ew"
        )
        self.image_label = ttk.Label(top_frame, text="Изображение не выбрано")
        self.image_label.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        ttk.Label(top_frame, text="Confidence:").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.conf_var = tk.DoubleVar(value=0.25)
        self.conf_scale = ttk.Scale(
            top_frame,
            from_=0.05,
            to=0.95,
            variable=self.conf_var,
            orient="horizontal",
            length=250,
            command=self._update_conf_label
        )
        self.conf_scale.grid(row=2, column=1, padx=5, pady=5, sticky="w")

        self.conf_value_label = ttk.Label(top_frame, text="0.25")
        self.conf_value_label.grid(row=2, column=2, padx=5, pady=5, sticky="w")

        ttk.Button(top_frame, text="Запустить детекцию", command=self.run_detection).grid(
            row=3, column=0, padx=5, pady=10, sticky="ew"
        )
        ttk.Button(top_frame, text="Сохранить результат", command=self.save_result).grid(
            row=3, column=1, padx=5, pady=10, sticky="w"
        )

        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        image_frame = ttk.LabelFrame(main_frame, text="Результат", padding=10)
        image_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.image_canvas = tk.Canvas(image_frame, bg="black")
        self.image_canvas.pack(fill=tk.BOTH, expand=True)
        self.image_canvas.bind("<Configure>", self._redraw_canvas)

        right_frame = ttk.LabelFrame(main_frame, text="Найденные объекты", padding=10)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))

        self.result_text = tk.Text(right_frame, width=40, height=30, state="disabled")
        self.result_text.pack(fill=tk.BOTH, expand=True)

    def _update_conf_label(self, _event=None) -> None:
        self.conf_value_label.config(text=f"{self.conf_var.get():.2f}")

    def load_model(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите YOLO модель",
            filetypes=[("PyTorch model", "*.pt"), ("All files", "*.*")]
        )
        if not path:
            return

        try:
            self.model = YOLO(path)
            self.model_path = path
            self.model_label.config(text=os.path.basename(path))
            messagebox.showinfo("Успех", "Модель успешно загружена.")
        except Exception as e:
            self.model = None
            self.model_path = ""
            messagebox.showerror("Ошибка", f"Не удалось загрузить модель:\n{e}")

    def load_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите изображение",
            filetypes=[
                ("Images", "*.jpg *.jpeg *.png *.bmp *.webp"),
                ("All files", "*.*")
            ]
        )
        if not path:
            return

        bgr = cv2.imread(path)
        if bgr is None:
            messagebox.showerror("Ошибка", "Не удалось открыть изображение.")
            return

        self.image_path = path
        self.original_bgr = bgr
        self.result_bgr = bgr.copy()
        self.image_label.config(text=os.path.basename(path))
        self._show_bgr_on_canvas(self.result_bgr)
        self._set_result_text("Изображение загружено. Можно запускать детекцию.\n")

    def run_detection(self) -> None:
        if self.model is None:
            messagebox.showwarning("Внимание", "Сначала загрузите модель YOLO.")
            return

        if self.original_bgr is None:
            messagebox.showwarning("Внимание", "Сначала загрузите изображение.")
            return

        try:
            conf = float(self.conf_var.get())
            results = self.model.predict(
                source=self.original_bgr,
                conf=conf,
                verbose=False
            )

            if not results:
                messagebox.showwarning("Внимание", "Модель не вернула результатов.")
                return

            result = results[0]
            plotted = result.plot()
            self.result_bgr = plotted
            self._show_bgr_on_canvas(self.result_bgr)

            lines = []
            boxes = result.boxes

            if boxes is None or len(boxes) == 0:
                lines.append("Объекты не найдены.")
            else:
                names = result.names
                for i, box in enumerate(boxes):
                    cls_id = int(box.cls[0].item())
                    score = float(box.conf[0].item())
                    x1, y1, x2, y2 = map(float, box.xyxy[0].tolist())
                    class_name = names.get(cls_id, str(cls_id))

                    lines.append(
                        f"{i + 1}. {class_name} | conf={score:.3f} | "
                        f"bbox=({x1:.1f}, {y1:.1f}, {x2:.1f}, {y2:.1f})"
                    )

            self._set_result_text("\n".join(lines))

        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка во время детекции:\n{e}")

    def save_result(self) -> None:
        if self.result_bgr is None:
            messagebox.showwarning("Внимание", "Нет результата для сохранения.")
            return

        path = filedialog.asksaveasfilename(
            title="Сохранить результат",
            defaultextension=".jpg",
            filetypes=[
                ("JPEG", "*.jpg"),
                ("PNG", "*.png"),
                ("All files", "*.*")
            ]
        )
        if not path:
            return

        try:
            ok = cv2.imwrite(path, self.result_bgr)
            if not ok:
                raise ValueError("cv2.imwrite вернул False")
            messagebox.showinfo("Успех", f"Результат сохранён:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{e}")

    def _show_bgr_on_canvas(self, bgr_image) -> None:
        rgb = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)

        canvas_width = max(self.image_canvas.winfo_width(), 1)
        canvas_height = max(self.image_canvas.winfo_height(), 1)

        image_copy = pil_image.copy()
        image_copy.thumbnail((canvas_width, canvas_height))

        self.tk_image = ImageTk.PhotoImage(image_copy)
        self.image_canvas.delete("all")
        self.image_canvas.create_image(
            canvas_width // 2,
            canvas_height // 2,
            image=self.tk_image,
            anchor="center"
        )

    def _redraw_canvas(self, _event=None) -> None:
        if self.result_bgr is not None:
            self._show_bgr_on_canvas(self.result_bgr)

    def _set_result_text(self, text: str) -> None:
        self.result_text.config(state="normal")
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert(tk.END, text)
        self.result_text.config(state="disabled")


def main() -> None:
    root = tk.Tk()
    app = YoloGuiApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()