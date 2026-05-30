"""Read text from an open PuTTY window via 'Copy All to Clipboard'.

Uses Windows API: find PuTTY windows, send WM_SYSCOMMAND with IDM_COPYALL (0x0170),
then read clipboard. Requires pywin32 on Windows.
"""

from __future__ import annotations

import sys
from typing import Any

if sys.platform != "win32":
    def list_putty_windows() -> list[dict[str, Any]]:
        return []

    def resolve_putty_window(
        host: str | None = None,
        title_substring: str | None = None,
        process_id: int | None = None,
    ) -> dict[str, Any]:
        return {"success": False, "error": "Windows only.", "windows": []}

    def read_putty_window(
        host: str | None = None,
        title_substring: str | None = None,
        process_id: int | None = None,
    ) -> dict[str, Any]:
        return {
            "success": False,
            "error": "Reading PuTTY window is supported only on Windows.",
            "content": None,
        }
else:
    try:
        import win32clipboard
        import win32con
        import win32gui
        import win32process
    except ImportError:
        def list_putty_windows() -> list[dict[str, Any]]:
            return []

        def resolve_putty_window(
            host: str | None = None,
            title_substring: str | None = None,
            process_id: int | None = None,
        ) -> dict[str, Any]:
            return {"success": False, "error": "pywin32 required.", "windows": []}

        def read_putty_window(
            host: str | None = None,
            title_substring: str | None = None,
            process_id: int | None = None,
        ) -> dict[str, Any]:
            return {
                "success": False,
                "error": "pywin32 is required. Install with: pip install pywin32",
                "content": None,
            }
    else:
        # PuTTY system menu: "Copy All to Clipboard" = IDM_COPYALL 0x0170
        IDM_COPYALL = 0x0170
        WM_SYSCOMMAND = 0x0112

        def _is_putty_window(hwnd: int) -> bool:
            if not win32gui.IsWindowVisible(hwnd):
                return False
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                import ctypes
                from ctypes import wintypes
                kernel32 = ctypes.windll.kernel32
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if not h:
                    return False
                try:
                    size = wintypes.DWORD(260)
                    buf = (wintypes.WCHAR * 260)()
                    if not kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                        return False
                    name = buf.value.replace("\\", "/").split("/")[-1].lower()
                    return name == "putty.exe"
                finally:
                    kernel32.CloseHandle(h)
            except Exception:
                return False

        def list_putty_windows() -> list[dict[str, Any]]:
            result: list[dict[str, Any]] = []

            def enum_cb(hwnd: int, _: None) -> None:
                if _is_putty_window(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    result.append({"hwnd": hwnd, "title": title, "pid": pid})

            win32gui.EnumWindows(enum_cb, None)
            return result

        def resolve_putty_window(
            host: str | None = None,
            title_substring: str | None = None,
            process_id: int | None = None,
        ) -> dict[str, Any]:
            """Pick one PuTTY window. Returns dict with hwnd, title, and optional error."""
            candidates = list_putty_windows()
            if not candidates:
                return {"success": False, "error": "No PuTTY windows found.", "windows": []}
            hwnd = None
            title = None
            if process_id is not None:
                for w in candidates:
                    if w["pid"] == process_id:
                        hwnd, title = w["hwnd"], w["title"]
                        break
            if hwnd is None and (host is not None or title_substring is not None):
                needle = (host or title_substring or "").lower()
                for w in candidates:
                    if needle in (w["title"] or "").lower():
                        hwnd, title = w["hwnd"], w["title"]
                        break
            if hwnd is None and len(candidates) == 1:
                hwnd, title = candidates[0]["hwnd"], candidates[0]["title"]
            if hwnd is None:
                return {
                    "success": False,
                    "error": "Multiple PuTTY windows; specify host, title_substring, or process_id.",
                    "windows": [{"title": w["title"], "pid": w["pid"]} for w in candidates],
                }
            return {"success": True, "hwnd": hwnd, "title": title or ""}

        def read_putty_window(
            host: str | None = None,
            title_substring: str | None = None,
            process_id: int | None = None,
        ) -> dict[str, Any]:
            candidates = list_putty_windows()
            if not candidates:
                return {
                    "success": False,
                    "error": "No PuTTY windows found.",
                    "content": None,
                    "windows": [],
                }
            hwnd = None
            if process_id is not None:
                for w in candidates:
                    if w["pid"] == process_id:
                        hwnd = w["hwnd"]
                        break
            if host is not None or title_substring is not None:
                needle = (host or title_substring or "").lower()
                for w in candidates:
                    if needle in (w["title"] or "").lower():
                        hwnd = w["hwnd"]
                        break
            if hwnd is None and len(candidates) == 1:
                hwnd = candidates[0]["hwnd"]
            if hwnd is None:
                return {
                    "success": False,
                    "error": "Multiple PuTTY windows found; specify host, title_substring, or process_id.",
                    "content": None,
                    "windows": [{"title": w["title"], "pid": w["pid"]} for w in candidates],
                }
            # Save current clipboard
            try:
                win32clipboard.OpenClipboard()
                try:
                    old = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                except (TypeError, OSError):
                    old = None
            except Exception:
                old = None
            finally:
                try:
                    win32clipboard.CloseClipboard()
                except Exception:
                    pass
            # Ask PuTTY to copy all
            import time as _time
            win32gui.PostMessage(hwnd, WM_SYSCOMMAND, IDM_COPYALL, 0)
            _time.sleep(0.3)
            content = None
            try:
                win32clipboard.OpenClipboard()
                try:
                    content = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                except (TypeError, OSError):
                    content = None
            except Exception:
                pass
            finally:
                try:
                    win32clipboard.CloseClipboard()
                except Exception:
                    pass
            # Restore previous clipboard
            if old is not None:
                try:
                    win32clipboard.OpenClipboard()
                    try:
                        win32clipboard.EmptyClipboard()
                        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, old)
                    finally:
                        win32clipboard.CloseClipboard()
                except Exception:
                    pass
            if content is None:
                return {
                    "success": False,
                    "error": "Failed to read clipboard after Copy All (window may not have responded).",
                    "content": None,
                }
            return {
                "success": True,
                "content": content,
                "window_title": win32gui.GetWindowText(hwnd),
            }
