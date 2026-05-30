"""PuTTY MCP Server with window interaction tools only."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from putty_lib import window_reader
from putty_lib import window_send

mcp = FastMCP("putty-mcp", json_response=True)


@mcp.tool()
def putty_list_windows() -> dict:
    """List all visible PuTTY windows (title and PID). Windows only; requires pywin32."""
    windows = window_reader.list_putty_windows()
    return {
        "success": True,
        "windows": [{"title": w["title"], "pid": w["pid"]} for w in windows],
        "count": len(windows),
    }


@mcp.tool()
def putty_read_window(
    host: str | None = None,
    title_substring: str | None = None,
    process_id: int | None = None,
) -> dict:
    """Read full text from an open PuTTY window (screen + scrollback) via Copy All to Clipboard.
    Specify host or title_substring to pick one window when several are open; or process_id.
    Windows only; requires pywin32. Restores the previous clipboard after reading."""
    return window_reader.read_putty_window(
        host=host,
        title_substring=title_substring,
        process_id=process_id,
    )


@mcp.tool()
def putty_send_command(
    command: str,
    host: str | None = None,
    title_substring: str | None = None,
    process_id: int | None = None,
    append_newline: bool = True,
) -> dict:
    """Send a command to an open PuTTY window (types the text and optionally Enter).
    The window is brought to foreground, then the string is sent as keystrokes.
    Specify host or title_substring to pick one window when several are open; or process_id.
    Windows only; requires pywin32."""
    return window_send.send_putty_command(
        command=command,
        host=host,
        title_substring=title_substring,
        process_id=process_id,
        append_newline=append_newline,
    )


@mcp.tool()
def putty_clear_window(
    host: str | None = None,
    title_substring: str | None = None,
    process_id: int | None = None,
) -> dict:
    """Clear old PuTTY scrollback/history in the selected window.
    Useful before reading window content to reduce noisy old context."""
    return window_send.clear_putty_window(
        host=host,
        title_substring=title_substring,
        process_id=process_id,
    )

if __name__ == "__main__":
    mcp.run(transport="stdio")
