---
name: logics-mcp-notion
description: Install, configure, and use the Notion MCP server to connect MCP clients to Notion (read/query/update pages and databases). Use when wiring MCP clients to Notion.
---

# Notion MCP

## Quick start
1) Create a Notion integration and connect the target pages/databases to it.
2) Add the MCP server config to your client (below).
3) Restart the client and test a simple query (search or retrieve a page).

### Standard MCP config (official server)
```json
{
  "mcpServers": {
    "notionApi": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_TOKEN": "ntn_***"
      }
    }
  }
}
```

### Advanced auth (optional)
Use OpenAPI headers if you need custom auth/version headers:

```json
{
  "mcpServers": {
    "notionApi": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "OPENAPI_MCP_HEADERS": "{\"Authorization\": \"Bearer ntn_***\", \"Notion-Version\": \"2025-09-03\" }"
      }
    }
  }
}
```

### HTTP transport (optional)
If your client needs HTTP transport:

```bash
npx @notionhq/notion-mcp-server --transport http --auth-token "your-secret-token"
```

The server will be available at `http://0.0.0.0:<port>/mcp`.

### Community alternative (optional)
If you need Markdown conversion output:

```json
{
  "mcpServers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@suekou/mcp-notion-server"],
      "env": {
        "NOTION_API_TOKEN": "your-integration-token",
        "NOTION_MARKDOWN_CONVERSION": "true"
      }
    }
  }
}
```

## Usage flow (agent-side)
- Start with a safe read-only query: search or retrieve a known page.
- Validate permissions before attempting writes.
- Prefer small, targeted operations (avoid full-workspace scans).

## Safety
- Notion tokens grant workspace access; use least-privileged integrations.
- Prefer read-only integrations when possible.
- Avoid exposing tokens in logs or prompts.
