---
name: logics-mcp-terminal
description: Install, configure, and use the Terminal MCP (server-shell) for running shell commands in Codex/agents. Use when wiring MCP clients to terminal control, executing commands via MCP, or debugging shell access.
---

# Terminal MCP (server-shell)

## Quick start
1) Ensure Node.js and npm are available.
2) Add the MCP server config (below) to your client.
3) Use MCP tools to run commands safely (pwd, ls, rg, git status).

### Standard MCP config
```json
{
  "mcpServers": {
    "terminal": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-shell"]
    }
  }
}
```

### Codex CLI command
```bash
codex mcp add terminal -- npx -y @modelcontextprotocol/server-shell
```

## Usage flow (agent-side)
- Start with `pwd` and `ls` to confirm the repo root.
- Use `rg` for fast search.
- Prefer non-destructive commands; avoid `rm -rf`.
- Confirm before running long or risky commands.

## Safety
- Treat the shell as sensitive: it has full filesystem access.
- Avoid exporting secrets into logs or command history.
- For privileged commands, ask the user explicitly.

## Resources
- Client-specific setup: see `references/clients.md`.
