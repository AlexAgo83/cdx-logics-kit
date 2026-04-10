---
name: logics-bootstrapper
description: Bootstrap the Logics directory structure in a new repository (create `logics/architecture`, `logics/product`, `logics/request`, `logics/backlog`, `logics/tasks`, `logics/specs`, `logics/external`) and add `.gitkeep` files for empty folders so the structure stays versioned. Use when setting up Logics in a fresh project or validating that required directories exist.
---

# Bootstrap Logics folders

## Run

Create missing Logics folders (and `.gitkeep` files for empty dirs):

```bash
python logics/skills/logics-bootstrapper/scripts/logics_bootstrap.py
```

This also creates `logics/instructions.md`, a minimal `LOGICS.md`, and a local `AGENTS.md`/`LOGICS.md` pairing when those files are missing.

Dry-run (print actions, no writes):

```bash
python logics/skills/logics-bootstrapper/scripts/logics_bootstrap.py --dry-run
```

Check mode (exit non-zero if bootstrapping is needed):

```bash
python logics/skills/logics-bootstrapper/scripts/logics_bootstrap.py --check
```

Specify a different repo root:

```bash
python logics/skills/logics-bootstrapper/scripts/logics_bootstrap.py --root /path/to/repo
```
