"""Send commands to an open PuTTY window.

Delivers text either via clipboard paste (IDM_PASTE — reliable for long
lines) or WM_CHAR (needed for control characters such as Ctrl+C).
Messages go straight to the PuTTY hwnd, so the window is not restored,
raised, or focused. Requires pywin32 on Windows.
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
        import win32clipboard
        import win32con
        import win32gui
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

        WM_CHAR = 0x0102
        WM_SYSCOMMAND = 0x0112
        # PuTTY system-menu IDs from windows/window.c in upstream PuTTY.
        IDM_CLRSB = 0x0060
        IDM_PASTE = 0x01A0

        # Paste is used for normal text. Per-character WM_CHAR was truncating
        # long remote shell lines (tty line discipline / soft-wrap interaction),
        # which left ash waiting on a ">" continuation prompt.
        _PASTE_MIN_LEN = 1

        _CHAR_DELAY_S = 0.01
        _PASTE_DELAY_S = 0.15

        def _command_needs_wm_char(command: str) -> bool:
            """True when paste cannot represent the payload (control chars)."""
            if not command:
                return True
            for ch in command:
                code = ord(ch)
                # Allow tab/newline; everything else below space must be typed.
                if code < 32 and ch not in ("\t", "\n", "\r"):
                    return True
            return False

        def _clipboard_get_text() -> str | None:
            try:
                win32clipboard.OpenClipboard()
                try:
                    return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                except (TypeError, OSError):
                    return None
            except Exception:
                return None
            finally:
                try:
                    win32clipboard.CloseClipboard()
                except Exception:
                    pass

        def _clipboard_set_text(text: str) -> None:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
            finally:
                win32clipboard.CloseClipboard()

        def _send_with_wm_char(hwnd: int, command: str, append_newline: bool) -> None:
            text = command + ("\r" if append_newline else "")
            for c in text:
                win32gui.SendMessage(hwnd, WM_CHAR, 13 if c == "\n" else ord(c), 0)
                time.sleep(_CHAR_DELAY_S)

        def _send_with_paste(hwnd: int, command: str, append_newline: bool) -> str:
            """Paste via PuTTY IDM_PASTE; restore previous clipboard afterwards.

            Returns the delivery method label for the response payload.
            """
            old = _clipboard_get_text()
            try:
                _clipboard_set_text(command)
                # Same path as Copy All / Clear Scrollback: system-menu command ID.
                win32gui.PostMessage(hwnd, WM_SYSCOMMAND, IDM_PASTE, 0)
                # Give PuTTY time to read the clipboard and inject the paste buffer.
                # Scale slightly with length so very large pastes are not raced.
                time.sleep(_PASTE_DELAY_S + min(len(command), 4000) * 0.00005)
                if append_newline:
                    win32gui.SendMessage(hwnd, WM_CHAR, 13, 0)
                    time.sleep(_CHAR_DELAY_S)
            finally:
                if old is not None:
                    try:
                        _clipboard_set_text(old)
                    except Exception:
                        pass
            return "paste"

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
            method = "wm_char"
            # Paste and WM_CHAR are addressed to this hwnd. Do not restore,
            # raise, or focus the window: SW_RESTORE shrinks a maximized
            # PuTTY, and SetForegroundWindow steals the user's focus.
            try:
                activated = win32gui.GetForegroundWindow() == hwnd
            except Exception:
                activated = False
            try:
                # Prefer clipboard paste for normal text: bulk paste avoids the
                # mid-line truncation that WM_CHAR streams hit on long shell lines.
                if (
                    len(command) >= _PASTE_MIN_LEN
                    and not _command_needs_wm_char(command)
                ):
                    method = _send_with_paste(hwnd, command, append_newline)
                else:
                    _send_with_wm_char(hwnd, command, append_newline)
                    method = "wm_char"
            except Exception as e:
                return {"success": False, "error": f"Send failed: {e}"}
            return {
                "success": True,
                "window_title": title,
                "command_sent": command + ("\n" if append_newline else ""),
                "activated": activated,
                "delivery": method,
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
