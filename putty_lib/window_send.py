"""Send commands to an open PuTTY window.

Activates the window, sets focus to the terminal area, then sends WM_CHAR
synchronously with throttling. Requires pywin32 on Windows.
"""

from __future__ import annotations

import sys
import time
from typing import Any

if sys.platform != "win32":
    def send_putty_command(
        command: str,
        host: str | None = None,
        title_substring: str | None = None,
        process_id: int | None = None,
        append_newline: bool = True,
    ) -> dict[str, Any]:
        return {
            "success": False,
            "error": "Sending to PuTTY window is supported only on Windows.",
        }

    def clear_putty_window(
        host: str | None = None,
        title_substring: str | None = None,
        process_id: int | None = None,
    ) -> dict[str, Any]:
        return {
            "success": False,
            "error": "Clearing PuTTY window is supported only on Windows.",
        }
else:
    try:
        import ctypes
        from ctypes import wintypes
        import win32gui
        import win32process
    except ImportError:
        def send_putty_command(
            command: str,
            host: str | None = None,
            title_substring: str | None = None,
            process_id: int | None = None,
            append_newline: bool = True,
        ) -> dict[str, Any]:
            return {
                "success": False,
                "error": "pywin32 is required. Install with: pip install pywin32",
            }

        def clear_putty_window(
            host: str | None = None,
            title_substring: str | None = None,
            process_id: int | None = None,
        ) -> dict[str, Any]:
            return {
                "success": False,
                "error": "pywin32 is required. Install with: pip install pywin32",
            }
    else:
        from putty_lib import window_reader

        user32 = ctypes.windll.user32
        WM_CHAR = 0x0102
        WM_SYSCOMMAND = 0x0112
        SW_RESTORE = 9
        # PuTTY system-menu IDs from windows/window.c in upstream PuTTY.
        IDM_CLRSB = 0x0060

        def _get_putty_focus_hwnd(main_hwnd: int) -> int | None:
            """Return the hwnd that has keyboard focus in PuTTY's thread, or None."""
            GUITHREADINFO = type("GUITHREADINFO", (ctypes.Structure,), {
                "_fields_": [
                    ("cbSize", wintypes.DWORD),
                    ("flags", wintypes.DWORD),
                    ("hwndActive", ctypes.c_void_p),
                    ("hwndFocus", ctypes.c_void_p),
                    ("hwndCapture", ctypes.c_void_p),
                    ("hwndMenuOwner", ctypes.c_void_p),
                    ("hwndMoveSize", ctypes.c_void_p),
                    ("hwndCaret", ctypes.c_void_p),
                    ("rcCaret", wintypes.RECT),
                ]
            })
            putty_tid, _ = win32process.GetWindowThreadProcessId(main_hwnd)
            gti = GUITHREADINFO()
            gti.cbSize = ctypes.sizeof(GUITHREADINFO)
            if not user32.GetGUIThreadInfo(putty_tid, ctypes.byref(gti)):
                return None
            target = gti.hwndFocus or gti.hwndActive
            return int(target) if target else None

        # Retry and timing constants for window activation
        _ACTIVATE_ATTEMPTS = 3
        _ACTIVATE_DELAY_S = 0.5
        _FOCUS_DELAY_S = 0.4
        _CHAR_DELAY_S = 0.01

        def _send_with_wm_char(hwnd: int, command: str, append_newline: bool) -> None:
            text = command + ("\r" if append_newline else "")
            for c in text:
                win32gui.SendMessage(hwnd, WM_CHAR, 13 if c == "\n" else ord(c), 0)
                time.sleep(_CHAR_DELAY_S)

        def _activate_and_focus(hwnd: int, focus_hwnd: int) -> bool:
            """Best-effort PuTTY activation.

            Windows can deny SetForegroundWindow when another process owns the
            foreground lock. That must not block command sending because WM_CHAR
            below is addressed directly to PuTTY's hwnd, not to the foreground
            window.
            """
            activated = False
            for attempt in range(_ACTIVATE_ATTEMPTS):
                try:
                    user32.ShowWindow(hwnd, SW_RESTORE)
                    user32.BringWindowToTop(hwnd)
                    win32gui.SetForegroundWindow(hwnd)
                except Exception:
                    pass
                time.sleep(_ACTIVATE_DELAY_S)
                try:
                    user32.SetFocus(focus_hwnd)
                except Exception:
                    pass
                time.sleep(_FOCUS_DELAY_S)
                if win32gui.GetForegroundWindow() == hwnd:
                    activated = True
                    break
                if attempt < _ACTIVATE_ATTEMPTS - 1:
                    time.sleep(0.3)
            return activated

        def send_putty_command(
            command: str,
            host: str | None = None,
            title_substring: str | None = None,
            process_id: int | None = None,
            append_newline: bool = True,
        ) -> dict[str, Any]:
            resolved = window_reader.resolve_putty_window(
                host=host,
                title_substring=title_substring,
                process_id=process_id,
            )
            if not resolved.get("success"):
                return {
                    "success": False,
                    "error": resolved.get("error", "No PuTTY window selected."),
                    "windows": resolved.get("windows", []),
                }
            hwnd = resolved["hwnd"]
            title = resolved.get("title", "")
            putty_tid, _ = win32process.GetWindowThreadProcessId(hwnd)
            kernel32 = ctypes.windll.kernel32
            our_tid = kernel32.GetCurrentThreadId()
            attached = False
            focus_hwnd = _get_putty_focus_hwnd(hwnd) or hwnd
            try:
                if putty_tid != our_tid:
                    attached = user32.AttachThreadInput(our_tid, putty_tid, 1)
                activated = _activate_and_focus(hwnd, focus_hwnd)
                # Send directly to the PuTTY top-level window. PuTTY handles
                # WM_CHAR there, so delivery does not depend on Windows granting
                # foreground focus to this automation process.
                _send_with_wm_char(hwnd, command, append_newline)
            except Exception as e:
                return {"success": False, "error": f"Send failed: {e}"}
            finally:
                if attached:
                    user32.AttachThreadInput(our_tid, putty_tid, 0)
            return {
                "success": True,
                "window_title": title,
                "command_sent": command + ("\n" if append_newline else ""),
                "activated": activated,
            }

        def clear_putty_window(
            host: str | None = None,
            title_substring: str | None = None,
            process_id: int | None = None,
        ) -> dict[str, Any]:
            """Clear PuTTY scrollback/history in a locale-independent way."""
            resolved = window_reader.resolve_putty_window(
                host=host,
                title_substring=title_substring,
                process_id=process_id,
            )
            if not resolved.get("success"):
                return {
                    "success": False,
                    "error": resolved.get("error", "No PuTTY window selected."),
                    "windows": resolved.get("windows", []),
                }

            hwnd = resolved["hwnd"]
            title = resolved.get("title", "")

            try:
                # Locale-independent: call PuTTY's clear-scrollback command ID directly.
                win32gui.PostMessage(hwnd, WM_SYSCOMMAND, IDM_CLRSB, 0)
                time.sleep(0.1)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to clear PuTTY scrollback: {e}",
                    "window_title": title,
                }

            return {
                "success": True,
                "window_title": title,
                "message": "PuTTY scrollback was cleared.",
            }

