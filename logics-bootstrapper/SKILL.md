---
name: logics-bootstrapper
description: Bootstrap the Logics directory structure in a new repository (create `logics/architecture`, `logics/request`, `logics/backlog`, `logics/tasks`, `logics/specs`) and add `.gitkeep` files for empty folders so the structure stays versioned. Use when setting up Logics in a fresh project or validating that required directories exist.
---

# Bootstrap Logics folders

## Run

Create missing Logics folders (and `.gitkeep` files for empty dirs):

```bash
python3 logics/skills/logics-bootstrapper/scripts/logics_bootstrap.py
```

This also creates a default `logics/instructions.md` if it does not exist.

Dry-run (print actions, no writes):

```bash
python3 logics/skills/logics-bootstrapper/scripts/logics_bootstrap.py --dry-run
```

Check mode (exit non-zero if bootstrapping is needed):

```bash
python3 logics/skills/logics-bootstrapper/scripts/logics_bootstrap.py --check
```

Specify a different repo root:

```bash
python3 logics/skills/logics-bootstrapper/scripts/logics_bootstrap.py --root /path/to/repo
```
