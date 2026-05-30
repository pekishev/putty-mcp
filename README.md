# PuTTY MCP Server

Minimal [Model Context Protocol](https://modelcontextprotocol.io/) server for interacting with already opened PuTTY windows on Windows.

The server exposes 4 tools: list windows, read terminal output, send commands, and clear scrollback.

## Tools

| Tool | Description |
|------|-------------|
| `putty_list_windows` | List visible PuTTY windows with title and PID |
| `putty_read_window` | Read full text (screen + scrollback) from a selected PuTTY window |
| `putty_send_command` | Send text to a selected PuTTY window (optionally with Enter) |
| `putty_clear_window` | Clear scrollback/history in a selected PuTTY window |

### Window selection

When several PuTTY windows are open, pass one of these selectors to `putty_read_window`, `putty_send_command`, and `putty_clear_window`:

| Parameter | Description |
|-----------|-------------|
| `process_id` | PID from `putty_list_windows` (most reliable) |
| `host` | Substring matched against window title (case-insensitive) |
| `title_substring` | Same as `host`; alternative name for title matching |

If exactly one PuTTY window is open, the selector is optional.

### Tool parameters

**`putty_send_command`**

- `command` (required) — text to send
- `append_newline` (default: `true`) — append Enter after the command

**`putty_read_window`**, **`putty_clear_window`**, **`putty_send_command`**

- `process_id`, `host`, or `title_substring` — see [Window selection](#window-selection)

## Typical workflow

1. Call `putty_list_windows`.
2. Pick a window by `process_id` (preferred) or `title_substring`.
3. Optionally call `putty_clear_window` to remove old scrollback before reading.
4. Call `putty_send_command`.
5. Wait 1–2 seconds.
6. Call `putty_read_window` to get the command output.

For AI agents, see [AGENTS.md](AGENTS.md) for selection rules, diagnostic markers, and context-reduction tips.

## Requirements

- Python 3.10+
- Windows
- `pywin32` and `mcp[cli]` (see [Installation](#installation))
- One or more PuTTY GUI windows already open (`putty.exe`)

## Installation

```bash
git clone https://github.com/pekishev/putty-mcp.git
cd putty-mcp
pip install -r requirements.txt
```

Or install from `pyproject.toml`:

```bash
pip install .
```

## MCP configuration

Example MCP server entry for Cursor or other MCP clients:

```json
{
  "mcpServers": {
    "putty": {
      "command": "python",
      "args": ["C:/path/to/putty-mcp/putty_mcp.py"]
    }
  }
}
```

Use the absolute path to `putty_mcp.py` on your machine.

## How it works

- **Read** — sends PuTTY system command *Copy All to Clipboard* (`IDM_COPYALL`) via `PostMessage`, reads the clipboard, then restores the previous clipboard content.
- **Send** — resolves the target window, best-effort activation/focus, then sends characters with `WM_CHAR` directly to the PuTTY window. Delivery does not strictly depend on stealing OS foreground focus.
- **Clear** — sends PuTTY *Clear Scrollback* (`IDM_CLRSB`) via system menu command ID; works regardless of UI locale.

PuTTY windows are detected by process name (`putty.exe`), not by window title alone.

## Response format

All tools return JSON objects with a `success` field.

Examples:

- `putty_list_windows` → `{ "success": true, "windows": [{ "title": "...", "pid": 1234 }], "count": 1 }`
- `putty_read_window` → `{ "success": true, "content": "...", "window_title": "..." }`
- `putty_send_command` → `{ "success": true, "window_title": "...", "command_sent": "...\n", "activated": true }`
- `putty_clear_window` → `{ "success": true, "window_title": "...", "message": "PuTTY scrollback was cleared." }`

On errors, responses include `error` and, when relevant, a `windows` list to help pick the right target.

## Usage notes

- `putty_send_command` confirms that text was sent; it does **not** return command stdout. Read output with `putty_read_window`.
- Prefer `process_id` over title matching when multiple sessions are open.
- If activation is blocked by Windows focus rules, sending may still succeed (`activated: false`); bring PuTTY to the foreground manually if needed.
- Before diagnostics, use `putty_clear_window` or marker commands (`echo DIAG_START` / `echo DIAG_END`) to reduce noise in long scrollback.

## Project layout

```
putty_mcp.py          # MCP server entry point (FastMCP, stdio transport)
putty_lib/
  window_reader.py    # List/read PuTTY windows
  window_send.py      # Send commands and clear scrollback
```

## Limitations

- Windows only (`pywin32` required).
- Works with existing PuTTY GUI windows; the server does not create SSH sessions.
- Only `putty.exe` windows are supported (not KiTTY, PuTTYtel, or other forks unless they use the same executable name).
- Reading depends on PuTTY responding to *Copy All to Clipboard*.

## License

MIT
