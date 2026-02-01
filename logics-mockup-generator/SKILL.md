---
name: logics-mockup-generator
description: Generate quick PNG UI mockups (dashboards/panels) and store them under logics/external. Use when the user asks for on-the-fly visual mockups or PNG previews.
---

# Mockup generator (PNG)

Use this skill to create fast, disposable UI mockups (PNG) directly in the repo. Output goes to `logics/external/` by default.

## Quick start (stats dashboard preset)

```bash
python3 logics/skills/logics-mockup-generator/scripts/mockup.py \
  --out logics/external/stats-dashboard-mock.png
```

## Customize (optional)

You can override the title, cards, and top‑skills list:

```bash
python3 logics/skills/logics-mockup-generator/scripts/mockup.py \
  --out logics/external/stats-dashboard-mock.png \
  --title "PROGRESSION" \
  --cards "XP / 7D|52,180|+9.1%;GOLD / 7D|8,340|+2.6%;VIRTUAL SCORE|1,284|+3.4%;TOTAL IDLE|9h 10m|-18m" \
  --action-time "TOTAL ACTION TIME|6h 22m|+41m" \
  --skills "Hunting|1h 32m|24%;Cooking|1h 06m|17%;Mining|58m|15%;Tailoring|46m|12%;Fishing|39m|10%"
```

Formats:
- `--cards`: `Label|Value|Delta` entries separated by `;`.
- `--action-time`: single `Label|Value|Delta`.
- `--skills`: `Name|Time|Share` entries separated by `;`.

## Notes
- Outputs are placed under `logics/external/` unless you pass a different `--out`.
- Requires Python 3 and Pillow (`pip install pillow`) if not already available.
