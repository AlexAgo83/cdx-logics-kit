---
name: logics-mcp-chrome-devtools
description: Install and configure the Chrome DevTools MCP server (chrome-devtools-mcp) in projects and control Chrome via MCP for UI automation, debugging, network/console inspection, and performance tracing. Use when wiring MCP clients (Codex, Claude, Cursor, VS Code, etc.) to Chrome DevTools.
---

# Chrome DevTools MCP

## Quick start
1) Verify prerequisites: Node.js v20.19+ (LTS), npm, and Chrome stable.
2) Add the MCP server config to your client (below).
3) Start or attach Chrome if your client requires it.
4) Open the local project URL in Chrome (see Local project flow).
5) Use MCP tools to control the browser (snapshot -> actions).

### Standard MCP config
```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest"]
    }
  }
}
```

### Control workflow (agent-side)
- List pages -> select page -> take snapshot.
- Use element uids with click/fill/press_key/evaluate_script.
- Inspect console and network for debugging.
- Record performance traces when needed.

## Advanced configuration
- Add flags to `args` for channel/headless/isolated/connect-url. See `references/options.md`.
- Client-specific install commands: `references/clients.md`.
- Codex on Windows notes: `references/windows-codex.md`.

## Safety
- Treat the browser as sensitive: MCP exposes page data to the client.
- If client sandboxing prevents Chrome from starting, disable sandboxing for this server or connect to an existing Chrome instance (see options).

## Local project flow
Goal: open the local app and keep a reliable page handle for further actions.

1) Ask for (or infer) the dev server URL (examples: `http://localhost:5173/`, `http://localhost:3000/`).
2) Create a new page and navigate to the URL.
3) Wait for a stable marker (title text or a key heading).
4) Take a snapshot and confirm the target UI is visible.

## Visual testing flow (Codex)
Goal: let Codex validate UI changes directly against the rendered page.

1) After each UI change, refresh the page and wait for the marker.
2) Take a snapshot to confirm structure and key labels.
3) Capture a full-page screenshot for visual diff/confirmation.
4) If an interaction is needed, use the snapshot uids to click/fill.
5) Record findings (what changed, what is verified, what is missing).
