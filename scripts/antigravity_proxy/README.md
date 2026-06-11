# Open Computer Use - Agent Proxy Middleware

This is a Python-based Stdio middleware proxy designed to wrap the `open-computer-use` MCP server.

## Features (Antigravity V8.0 Architecture)
1. **IPC Lock & Daemon Protection**: Prevents multiple instances from causing port collisions.
2. **Viewport Culling**: Filters out useless `Pane` and `Group` nodes from the UI Automation tree to save LLM tokens.
3. **Smart Locator**: Allows fuzzy fallback if UI indexes shift.
4. **DPI Awareness**: Auto-scales logical coordinates to physical pixels for cross-resolution clicking.
5. **Focus Assertion Guard**: Reads `GetLastInputInfo` to block AI from typing or clicking if the user is actively working on the machine (prevents focus stealing).

## Usage
Replace your standard MCP execution command with:
`python /path/to/mcp_proxy.py`
