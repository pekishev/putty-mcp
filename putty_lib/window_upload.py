"""Chunked upload of text/binary payloads into a remote path via PuTTY.

Remote tty line length (often ~512 on BusyBox) cannot accept multi-KB one-liners.
This module writes the file in small `printf` chunks instead.
"""

from __future__ import annotations

import sys
import time
from typing import Any, Literal

Encoding = Literal["shell", "hex"]

# Keep each shell command well under typical BusyBox MAX_CANON (~512).
_DEFAULT_SHELL_CHUNK = 120
_DEFAULT_HEX_CHUNK = 40  # bytes -> 160 hex escape chars
_CHUNK_DELAY_S = 0.08
_SETTLE_S = 0.25


def _shell_single_quote(text: str) -> str:
    """Wrap text for a POSIX single-quoted string (no NULs)."""
    return "'" + text.replace("'", "'\\''") + "'"


def _hex_printf_payload(data: bytes) -> str:
    """Encode bytes as busybox-friendly printf %b escapes: \\xHH\\xHH..."""
    return "".join(f"\\x{b:02x}" for b in data)


if sys.platform != "win32":
    def upload_putty_text(
        content: str | bytes,
        remote_path: str,
        host: str | None = None,
        title_substring: str | None = None,
        process_id: int | None = None,
        encoding: Encoding = "shell",
        chunk_size: int | None = None,
        verify: bool = True,
    ) -> dict[str, Any]:
        return {
            "success": False,
            "error": "Uploading via PuTTY is supported only on Windows.",
        }
else:
    from putty_lib import window_reader, window_send

    def upload_putty_text(
        content: str | bytes,
        remote_path: str,
        host: str | None = None,
        title_substring: str | None = None,
        process_id: int | None = None,
        encoding: Encoding = "shell",
        chunk_size: int | None = None,
        verify: bool = True,
    ) -> dict[str, Any]:
        """Write content to remote_path using many short printf appends.

        encoding:
          - shell: UTF-8 text in single-quoted printf chunks (fast; no NUL bytes)
          - hex: binary-safe \\xHH escapes via printf %b (no remote base64 needed)
        """
        if not remote_path or remote_path.startswith("-"):
            return {"success": False, "error": "remote_path must be a non-empty absolute/relative path."}
        if encoding not in ("shell", "hex"):
            return {"success": False, "error": "encoding must be 'shell' or 'hex'."}

        selector = {
            "host": host,
            "title_substring": title_substring,
            "process_id": process_id,
        }

        if isinstance(content, str):
            raw = content.encode("utf-8")
        else:
            raw = content

        if encoding == "shell" and b"\x00" in raw:
            return {
                "success": False,
                "error": "shell encoding cannot carry NUL bytes; use encoding='hex'.",
            }

        path_q = _shell_single_quote(remote_path)
        clear = window_send.send_putty_command(f": > {path_q}", **selector)
        if not clear.get("success"):
            return clear
        time.sleep(_SETTLE_S)

        chunks_sent = 0
        if encoding == "shell":
            text = raw.decode("utf-8")
            size = chunk_size or _DEFAULT_SHELL_CHUNK
            for offset in range(0, len(text), size):
                piece = text[offset : offset + size]
                cmd = f"printf '%s' {_shell_single_quote(piece)} >> {path_q}"
                if len(cmd) > 480:
                    return {
                        "success": False,
                        "error": f"Chunk command too long ({len(cmd)}); reduce chunk_size.",
                        "chunks_sent": chunks_sent,
                    }
                result = window_send.send_putty_command(cmd, **selector)
                if not result.get("success"):
                    return {
                        "success": False,
                        "error": result.get("error", "chunk send failed"),
                        "chunks_sent": chunks_sent,
                    }
                chunks_sent += 1
                time.sleep(_CHUNK_DELAY_S)
        else:
            size = chunk_size or _DEFAULT_HEX_CHUNK
            for offset in range(0, len(raw), size):
                piece = raw[offset : offset + size]
                esc = _hex_printf_payload(piece)
                cmd = f"printf '%b' '{esc}' >> {path_q}"
                if len(cmd) > 480:
                    return {
                        "success": False,
                        "error": f"Chunk command too long ({len(cmd)}); reduce chunk_size.",
                        "chunks_sent": chunks_sent,
                    }
                result = window_send.send_putty_command(cmd, **selector)
                if not result.get("success"):
                    return {
                        "success": False,
                        "error": result.get("error", "chunk send failed"),
                        "chunks_sent": chunks_sent,
                    }
                chunks_sent += 1
                time.sleep(_CHUNK_DELAY_S)

        expected = len(raw)
        remote_size = None
        if verify:
            marker = f"UP{expected}"
            window_send.send_putty_command(
                f"wc -c < {path_q}; echo {marker}",
                **selector,
            )
            time.sleep(0.8)
            read = window_reader.read_putty_window(**selector)
            content_out = read.get("content") or ""
            # Parse the number on the line before the marker when possible.
            if marker in content_out:
                before = content_out.rsplit(marker, 1)[0]
                for line in reversed(before.splitlines()):
                    line = line.strip()
                    if line.isdigit():
                        remote_size = int(line)
                        break
            if remote_size != expected:
                return {
                    "success": False,
                    "error": f"Size mismatch after upload: remote={remote_size} expected={expected}",
                    "remote_path": remote_path,
                    "bytes": expected,
                    "remote_bytes": remote_size,
                    "chunks_sent": chunks_sent,
                    "encoding": encoding,
                }

        return {
            "success": True,
            "remote_path": remote_path,
            "bytes": expected,
            "remote_bytes": remote_size if verify else None,
            "chunks_sent": chunks_sent,
            "encoding": encoding,
        }
