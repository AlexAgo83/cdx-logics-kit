---
name: logics-mockup-generator
description: Generate quick PNG UI mockups (dashboards/panels) and store them under logics/external. Use when the user asks for on-the-fly visual mockups or PNG previews.
---

# Mockup generator (PNG)

Use this skill to create fast, disposable UI mockups (PNG) directly in the repo. Output goes to `logics/external/mockup/` by default. Defaults are neutral (non-domain-specific); pass your own labels when you want domain-specific content.

Always generate **both** mobile and desktop variants unless the user explicitly asks for only one.  
For VS Code extensions, use the `vscode` preset and generate **desktop only**.

## Quick start (dashboard preset)

```bash
python3 logics/skills/logics-mockup-generator/scripts/mockup.py \
  --layout desktop \
  --out logics/external/mockup/dashboard-desktop.png

python3 logics/skills/logics-mockup-generator/scripts/mockup.py \
  --layout mobile \
  --out logics/external/mockup/dashboard-mobile.png
```

## VS Code extension preset (desktop only)

```bash
python3 logics/skills/logics-mockup-generator/scripts/mockup.py \
  --preset vscode \
  --out logics/external/mockup/logics-orchestrator-desktop.png \
  --title "LOGICS ORCHESTRATOR" \
  --columns "Requests|Backlog|Tasks|Specs" \
  --detail-title "Details" \
  --detail-lines "ID: req_000_kickoff|Stage: request|Status: draft|Owner: you|Updated: today"
```

## Breakdown tab (base + modifiers)

```bash
python3 logics/skills/logics-mockup-generator/scripts/mockup.py \
  --mode breakdown \
  --layout desktop \
  --out logics/external/mockup/breakdown-desktop.png

python3 logics/skills/logics-mockup-generator/scripts/mockup.py \
  --mode breakdown \
  --layout mobile \
  --out logics/external/mockup/breakdown-mobile.png
```

## Customize (optional)

You can override the title, cards, and top‑skills list:

```bash
python3 logics/skills/logics-mockup-generator/scripts/mockup.py \
  --out logics/external/mockup/dashboard-mock.png \
  --title "OVERVIEW" \
  --cards "Metric A|52,180|+9.1%;Metric B|8,340|+2.6%;Metric C|1,284|+3.4%;Metric D|9h 10m|-18m" \
  --action-time "Active time|6h 22m|+41m" \
  --skills "Category A|1h 32m|24%;Category B|1h 06m|17%;Category C|58m|15%;Category D|46m|12%;Category E|39m|10%" \
  --tabs "Overview|Breakdown" \
  --layout desktop
```

Formats:
- `--cards`: `Label|Value|Delta` entries separated by `;`.
- `--action-time`: single `Label|Value|Delta`.
- `--skills`: `Name|Time|Share` entries separated by `;`.

## Notes
- Outputs are placed under `logics/external/mockup/` unless you pass a different `--out`.
- Requires Python 3 and Pillow (`pip install pillow`) if not already available.
