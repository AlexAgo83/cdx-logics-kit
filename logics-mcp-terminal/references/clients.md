# Client setup commands

Use the standard MCP config if your client does not provide a CLI command.

## Codex CLI
```bash
codex mcp add terminal -- npx -y @modelcontextprotocol/server-shell
```

## Claude Code
```bash
claude mcp add terminal npx -y @modelcontextprotocol/server-shell
```

## VS Code

Preferred path: if you are not sure which shell quoting rules apply, add the MCP server through the VS Code MCP UI or settings JSON instead of the CLI.

POSIX shell:

```bash
code --add-mcp '{"name":"terminal","command":"npx","args":["-y","@modelcontextprotocol/server-shell"]}'
```

PowerShell:

```powershell
code --add-mcp '{"name":"terminal","command":"npx","args":["-y","@modelcontextprotocol/server-shell"]}'
```

`cmd.exe`:

```cmd
code --add-mcp "{\"name\":\"terminal\",\"command\":\"npx\",\"args\":[\"-y\",\"@modelcontextprotocol/server-shell\"]}"
```

## Amp
```bash
amp mcp add terminal -- npx -y @modelcontextprotocol/server-shell
```

## Gemini CLI
```bash
gemini mcp add terminal -c "npx -y @modelcontextprotocol/server-shell"
```

## Cursor
Add a new MCP server in Cursor settings and set:
- command: npx
- args: -y @modelcontextprotocol/server-shell
