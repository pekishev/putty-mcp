# PuTTY MCP Server

Minimal [Model Context Protocol](https://modelcontextprotocol.io/) server for interacting with already opened PuTTY windows.

Current scope is intentionally small: only 3 tools for listing windows, reading terminal output, and sending commands.

## Tools

| Tool | Description |
|------|-------------|
| `putty_list_windows` | List visible PuTTY windows with title and PID |
| `putty_read_window` | Read full text (screen + scrollback) from a selected PuTTY window |
| `putty_send_command` | Send text command to a selected PuTTY window (optionally with Enter) |

## Requirements

- Python 3.10+
- Windows
- `pywin32` (`pip install -r requirements.txt`)
- PuTTY window(s) already opened

## Installation

```bash
git clone https://github.com/pekishev/putty-mcp.git
cd putty-mcp
pip install -r requirements.txt
```

## MCP Configuration

Example MCP server entry:

```json
{
  "mcpServers": {
    "putty": {
      "command": "python",
      "args": ["/path/to/putty-mcp/putty_mcp.py"]
    }
  }
}
```

## Usage Notes

- If several PuTTY windows are open, pass `host`, `title_substring`, or `process_id` to select the target window.
- `putty_read_window` uses PuTTY "Copy All to Clipboard", then restores previous clipboard content.
- `putty_send_command` needs window activation/foreground access; if Windows blocks focus stealing, bring PuTTY to foreground manually and retry.

## Limitations

- Windows-only behavior.
- Requires `pywin32`.
- Works with existing PuTTY GUI windows; this server does not create SSH sessions itself.

## License

MIT
