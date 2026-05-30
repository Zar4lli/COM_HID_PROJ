import platform
import threading
import time

try:
    import serial
    from serial.tools import list_ports
except Exception:
    serial = None
    list_ports = None

DEFAULT_BAUDRATE = 9600


class SerialManager:
    def __init__(self):
        self.ser = None
        self.lock = threading.Lock()

    @property
    def is_open(self):
        return self.ser is not None and self.ser.is_open

    def open(self, port: str, baudrate: int = DEFAULT_BAUDRATE, timeout: float = 1.0):
        if serial is None:
            raise RuntimeError("Модуль pyserial не установлен. Установи: pip install pyserial")
        self.close()
        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=timeout,
            write_timeout=timeout,
        )
        time.sleep(0.25)
        with self.lock:
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()

    def close(self):
        with self.lock:
            if self.ser is not None:
                try:
                    if self.ser.is_open:
                        self.ser.close()
                finally:
                    self.ser = None

    def send_command(self, command: str, expect_response: bool = True) -> str:
        if not self.is_open:
            raise RuntimeError("COM-порт не открыт")

        payload = command.strip() + "\n"
        with self.lock:
            self.ser.reset_input_buffer()
            self.ser.write(payload.encode("utf-8", errors="replace"))
            self.ser.flush()
            if not expect_response:
                return ""
            return self.ser.readline().decode("utf-8", errors="replace").strip()


class CursorController:
    MAX_REL_STEP = 20
    SETTLE_DELAY_S = 0.005
    MAX_ITERATIONS = 600
    TARGET_TOLERANCE = 1

    @staticmethod
    def get_position():
        if platform.system() == "Windows":
            import ctypes

            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            pt = POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)) == 0:
                raise RuntimeError("Не удалось получить позицию курсора")
            return int(pt.x), int(pt.y)
        raise RuntimeError("Управление курсором сейчас поддержано только на Windows")

    @staticmethod
    def _clamp_step(value: int) -> int:
        if value > CursorController.MAX_REL_STEP:
            return CursorController.MAX_REL_STEP
        if value < -CursorController.MAX_REL_STEP:
            return -CursorController.MAX_REL_STEP
        return value

    @staticmethod
    def move_to(serial_manager: "SerialManager", x: int, y: int):
        start_x, start_y = CursorController.get_position()
        commands_sent = 0
        last_response = ""

        for _ in range(CursorController.MAX_ITERATIONS):
            current_x, current_y = CursorController.get_position()
            dx = x - current_x
            dy = y - current_y

            if abs(dx) <= CursorController.TARGET_TOLERANCE and abs(dy) <= CursorController.TARGET_TOLERANCE:
                end_x, end_y = CursorController.get_position()
                return {
                    "start": (start_x, start_y),
                    "end": (end_x, end_y),
                    "target": (x, y),
                    "commands_sent": commands_sent,
                    "last_response": last_response or "OK",
                }

            step_x = CursorController._clamp_step(dx)
            step_y = CursorController._clamp_step(dy)
            last_response = serial_manager.send_command(
                f"MOUSE_MOVE {step_x} {step_y}",
                expect_response=True,
            )
            commands_sent += 1
            time.sleep(CursorController.SETTLE_DELAY_S)

        end_x, end_y = CursorController.get_position()
        raise RuntimeError(
            f"Не удалось точно дойти до ({x}, {y}). Текущая позиция: ({end_x}, {end_y})."
        )

    @staticmethod
    def left_press(serial_manager: "SerialManager"):
        return serial_manager.send_command("MOUSE_PRESS LEFT", expect_response=True)

    @staticmethod
    def left_release(serial_manager: "SerialManager"):
        return serial_manager.send_command("MOUSE_RELEASE LEFT", expect_response=True)

    @staticmethod
    def left_click(serial_manager: "SerialManager"):
        CursorController.left_press(serial_manager)
        time.sleep(0.03)
        CursorController.left_release(serial_manager)
        return "LEFT_CLICK"

    @staticmethod
    def right_press(serial_manager: "SerialManager"):
        return serial_manager.send_command("MOUSE_PRESS RIGHT", expect_response=True)

    @staticmethod
    def right_release(serial_manager: "SerialManager"):
        return serial_manager.send_command("MOUSE_RELEASE RIGHT", expect_response=True)

    @staticmethod
    def right_click(serial_manager: "SerialManager"):
        CursorController.right_press(serial_manager)
        time.sleep(0.03)
        CursorController.right_release(serial_manager)
        return "RIGHT_CLICK"

    @staticmethod
    def double_click(serial_manager: "SerialManager"):
        CursorController.left_click(serial_manager)
        time.sleep(0.08)
        CursorController.left_click(serial_manager)
        return "DOUBLE_CLICK"


def get_serial_ports():
    if list_ports is None:
        return []
    return [p.device for p in list_ports.comports()]
