# Client setup commands

Use the standard MCP config if your client does not provide a CLI command.

## Codex CLI
```bash
codex mcp add chrome-devtools -- npx chrome-devtools-mcp@latest
```

## Claude Code
```bash
claude mcp add chrome-devtools npx chrome-devtools-mcp@latest
```

## VS Code

Preferred path: if you are not sure which shell quoting rules apply, add the MCP server through the VS Code MCP UI or settings JSON instead of the CLI.

POSIX shell:

```bash
code --add-mcp '{"name":"chrome-devtools","command":"npx","args":["-y","chrome-devtools-mcp@latest"]}'
```

PowerShell:

```powershell
code --add-mcp '{"name":"chrome-devtools","command":"npx","args":["-y","chrome-devtools-mcp@latest"]}'
```

`cmd.exe`:

```cmd
code --add-mcp "{\"name\":\"chrome-devtools\",\"command\":\"npx\",\"args\":[\"-y\",\"chrome-devtools-mcp@latest\"]}"
```

## Amp
```bash
amp mcp add chrome-devtools -- npx chrome-devtools-mcp@latest
```

## Gemini CLI
```bash
gemini mcp add chrome-devtools -c "npx chrome-devtools-mcp@latest"
```

## Cursor
Add a new MCP server in Cursor settings and set:
- command: npx
- args: -y chrome-devtools-mcp@latest
