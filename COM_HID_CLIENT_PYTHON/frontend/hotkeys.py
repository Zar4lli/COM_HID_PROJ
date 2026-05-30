import platform
import threading


class HotkeyManager:
    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008
    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012
    HOTKEY_ID = 1

    KEY_NAME_TO_VK = {
        "A": 0x41, "B": 0x42, "C": 0x43, "D": 0x44, "E": 0x45, "F": 0x46,
        "G": 0x47, "H": 0x48, "I": 0x49, "J": 0x4A, "K": 0x4B, "L": 0x4C,
        "M": 0x4D, "N": 0x4E, "O": 0x4F, "P": 0x50, "Q": 0x51, "R": 0x52,
        "S": 0x53, "T": 0x54, "U": 0x55, "V": 0x56, "W": 0x57, "X": 0x58,
        "Y": 0x59, "Z": 0x5A,
        "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
        "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
        "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73, "F5": 0x74,
        "F6": 0x75, "F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79,
        "F11": 0x7A, "F12": 0x7B,
        "SPACE": 0x20, "TAB": 0x09, "ENTER": 0x0D, "ESC": 0x1B,
        "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
        "HOME": 0x24, "END": 0x23, "PAGEUP": 0x21, "PAGEDOWN": 0x22,
        "INSERT": 0x2D, "DELETE": 0x2E,
    }

    def __init__(self, app):
        self.app = app
        self.enabled = platform.system() == "Windows"
        self._registered = False
        self._thread = None
        self._thread_id = None
        self._mods = 0
        self._vk = 0

    @staticmethod
    def normalize_hotkey_text(hotkey_text: str) -> str:
        parts = [p.strip().upper() for p in hotkey_text.split("+") if p.strip()]
        mods = []
        key = None
        aliases = {"CONTROL": "CTRL", "ESCAPE": "ESC", "RETURN": "ENTER", "PRIOR": "PAGEUP", "NEXT": "PAGEDOWN", " ": "SPACE"}
        for part in parts:
            part = aliases.get(part, part)
            if part in ("CTRL", "ALT", "SHIFT", "WIN"):
                if part not in mods:
                    mods.append(part)
            else:
                key = part
        if not key:
            return "+".join(mods)
        ordered_mods = [m for m in ("CTRL", "ALT", "SHIFT", "WIN") if m in mods]
        return "+".join(ordered_mods + [key])

    def parse_hotkey(self, hotkey_text: str):
        if not self.enabled:
            raise RuntimeError("Горячие клавиши сейчас поддержаны только на Windows")
        normalized = self.normalize_hotkey_text(hotkey_text)
        if not normalized:
            raise RuntimeError("Горячая клавиша не задана")
        parts = normalized.split("+")
        mods = 0
        key_name = None
        for part in parts:
            if part == "CTRL":
                mods |= self.MOD_CONTROL
            elif part == "ALT":
                mods |= self.MOD_ALT
            elif part == "SHIFT":
                mods |= self.MOD_SHIFT
            elif part == "WIN":
                mods |= self.MOD_WIN
            else:
                key_name = part
        if not key_name:
            raise RuntimeError("Нужно указать основную клавишу, например F6 или X")
        vk = self.KEY_NAME_TO_VK.get(key_name)
        if vk is None:
            raise RuntimeError(f"Неподдерживаемая клавиша: {key_name}")
        return normalized, mods, vk

    def register(self, hotkey_text: str):
        if not self.enabled:
            raise RuntimeError("Горячие клавиши сейчас поддержаны только на Windows")
        normalized, mods, vk = self.parse_hotkey(hotkey_text)
        self.unregister()

        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._mods = mods
        self._vk = vk

        def worker():
            self._thread_id = kernel32.GetCurrentThreadId()
            if not user32.RegisterHotKey(None, self.HOTKEY_ID, self._mods, self._vk):
                self.app.after(0, lambda: self.app.on_hotkey_register_error(normalized))
                return
            self._registered = True
            self.app.after(0, lambda: self.app.on_hotkey_registered(normalized))
            msg = wintypes.MSG()
            while True:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0 or ret == -1:
                    break
                if msg.message == self.WM_HOTKEY and msg.wParam == self.HOTKEY_ID:
                    self.app.after(0, self.app.on_hotkey_pressed)
            if self._registered:
                user32.UnregisterHotKey(None, self.HOTKEY_ID)
            self._registered = False

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    def unregister(self):
        if not self.enabled:
            return
        if self._thread_id is not None:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, self.WM_QUIT, 0, 0)
        self._registered = False
        self._thread = None
        self._thread_id = None
        self._mods = 0
        self._vk = 0
