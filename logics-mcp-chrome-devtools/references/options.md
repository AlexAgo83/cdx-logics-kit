# Server options

## Example args
```json
["-y", "chrome-devtools-mcp@latest", "--channel=canary", "--headless=true", "--isolated=true"]
```

## Connect to an existing Chrome instance
Add `--connect-url` to attach to a running Chrome instance instead of launching a new one.

## Sandbox note
Launching Chrome can fail inside sandboxed environments. If this happens, disable sandboxing for this server or use `--connect-url` to attach to an existing browser.
