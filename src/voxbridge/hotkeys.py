"""Windows global hotkeys backed by RegisterHotKey."""

from __future__ import annotations

import ctypes
import threading
from collections.abc import Callable


WM_QUIT = 0x0012
WM_HOTKEY = 0x0312
PM_NOREMOVE = 0x0000
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000

HOTKEYS = {
    1: (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x36, "clone", "Ctrl+Alt+6"),
    2: (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x37, "send", "Ctrl+Alt+7"),
}


class HotkeyError(RuntimeError):
    """The Windows global-hotkey service could not be started."""


class HotkeyManager:
    """Register hotkeys on a dedicated Windows message-loop thread."""

    def __init__(self, callback: Callable[[str], None]) -> None:
        self._callback = callback
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()
        self._registration_errors: tuple[str, ...] = ()
        self._registered_ids: tuple[int, ...] = ()

    def start(self) -> tuple[str, ...]:
        """Register clone/send hotkeys and return any safe failure messages."""

        if not hasattr(ctypes, "WinDLL"):
            raise HotkeyError("全局快捷键仅支持 Windows。")
        if self._thread is not None and self._thread.is_alive():
            return self._registration_errors

        self._ready.clear()
        self._thread = threading.Thread(
            target=self._message_loop,
            name="VoxBridgeHotkeys",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=5):
            self.stop()
            raise HotkeyError("Windows 快捷键消息线程无法启动。")
        return self._registration_errors

    def _message_loop(self) -> None:
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        user32.RegisterHotKey.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.UnregisterHotKey.restype = wintypes.BOOL
        user32.PeekMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.GetMessageW.restype = ctypes.c_int

        self._thread_id = int(kernel32.GetCurrentThreadId())
        message = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, PM_NOREMOVE)

        registered: list[int] = []
        errors: list[str] = []
        for hotkey_id, (modifiers, virtual_key, _, label) in HOTKEYS.items():
            if user32.RegisterHotKey(None, hotkey_id, modifiers, virtual_key):
                registered.append(hotkey_id)
            else:
                errors.append(f"{label} 无法注册，可能已被其他程序占用。")

        self._registered_ids = tuple(registered)
        self._registration_errors = tuple(errors)
        self._ready.set()

        if not registered:
            return

        try:
            while True:
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    break
                if message.message != WM_HOTKEY:
                    continue
                hotkey = HOTKEYS.get(int(message.wParam))
                if hotkey is None:
                    continue
                try:
                    self._callback(hotkey[2])
                except Exception:
                    # Keep the Windows message loop alive if the consumer closes.
                    continue
        finally:
            for hotkey_id in registered:
                user32.UnregisterHotKey(None, hotkey_id)
            self._registered_ids = ()

    def stop(self) -> None:
        """Unregister any successful hotkeys and stop the message thread."""

        thread = self._thread
        thread_id = self._thread_id
        if thread is None:
            return

        if thread.is_alive() and thread_id is not None and hasattr(ctypes, "WinDLL"):
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            from ctypes import wintypes

            user32.PostThreadMessageW.argtypes = [
                wintypes.DWORD,
                wintypes.UINT,
                wintypes.WPARAM,
                wintypes.LPARAM,
            ]
            user32.PostThreadMessageW.restype = wintypes.BOOL
            user32.PostThreadMessageW(
                thread_id,
                WM_QUIT,
                0,
                0,
            )
            thread.join(timeout=3)

        self._thread = None
        self._thread_id = None
