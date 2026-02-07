---
name: logics-mcp-figma
description: Install, configure, and use a Figma MCP server to connect MCP clients to Figma (search files, read nodes, export assets). Use when wiring MCP clients to Figma.
---

# Figma MCP (official)

## Quick start
1) Enable the **desktop MCP server** in the Figma desktop app (Dev Mode).
2) Add the MCP server config to your client (below).
3) Restart the client and test a simple query (list pages or export a node).

### Desktop MCP server (local)
The desktop MCP server runs at:

```
http://127.0.0.1:3845/mcp
```

Example MCP config:
```json
{
  "mcpServers": {
    "figma-desktop": {
      "url": "http://127.0.0.1:3845/mcp"
    }
  }
}
```

### Remote MCP server (hosted by Figma)
The remote MCP server endpoint:

```
https://mcp.figma.com/mcp
```

Example MCP config:
```json
{
  "mcpServers": {
    "figma-remote": {
      "url": "https://mcp.figma.com/mcp"
    }
  }
}
```

## Usage flow (agent-side)
- Start with a read-only request (list pages, list nodes).
- Use node IDs to export assets.
- Keep exports small and scoped to the required nodes.

## Safety
- Treat tokens as secrets. Do not log them.
- Use least-privileged tokens where possible.
