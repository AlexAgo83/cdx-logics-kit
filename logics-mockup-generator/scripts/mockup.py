#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import os
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont


def parse_triplets(raw: str, entry_label: str) -> List[Tuple[str, str, str]]:
    if not raw:
        return []
    items: List[Tuple[str, str, str]] = []
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split("|")]
        if len(parts) != 3:
            raise SystemExit(f"Invalid {entry_label} entry: '{chunk}'. Expected 3 fields separated by '|'.")
        items.append((parts[0], parts[1], parts[2]))
    return items


def safe_font(path: str, size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def round_rect(draw: ImageDraw.ImageDraw, xy, radius, fill, outline=None, width=1):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill, outline=outline, width=width)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a quick PNG UI mockup.")
    parser.add_argument("--out", required=True, help="Output PNG path (default: logics/external/...).")
    parser.add_argument("--title", default="PROGRESSION", help="Main title text.")
    parser.add_argument(
        "--cards",
        default="XP / 7D|52,180|+9.1%;GOLD / 7D|8,340|+2.6%;VIRTUAL SCORE|1,284|+3.4%;TOTAL IDLE|9h 10m|-18m",
        help="Semicolon-separated cards: Label|Value|Delta",
    )
    parser.add_argument(
        "--action-time",
        default="TOTAL ACTION TIME|6h 22m|+41m",
        help="Action time card: Label|Value|Delta",
    )
    parser.add_argument(
        "--skills",
        default="Hunting|1h 32m|24%;Cooking|1h 06m|17%;Mining|58m|15%;Tailoring|46m|12%;Fishing|39m|10%",
        help="Top skills list: Name|Time|Share;...",
    )

    args = parser.parse_args()

    cards = parse_triplets(args.cards, "card")
    action_card = parse_triplets(args.action_time, "action-time")
    skills = parse_triplets(args.skills, "skills")
    if not action_card:
        raise SystemExit("--action-time is required.")

    w, h = 1400, 900
    bg = Image.new("RGB", (w, h), "#0b1220")
    pix = bg.load()
    for y in range(h):
        t = y / (h - 1)
        r = int(8 + (12 - 8) * t)
        g = int(14 + (24 - 14) * t)
        b = int(26 + (42 - 26) * t)
        for x in range(w):
            pix[x, y] = (r, g, b)

    img = bg
    draw = ImageDraw.Draw(img)

    title_font = safe_font("/System/Library/Fonts/Supplemental/GillSans.ttc", 38)
    label_font = safe_font("/System/Library/Fonts/Supplemental/GillSans.ttc", 18)
    value_font = safe_font("/System/Library/Fonts/Supplemental/GillSans.ttc", 30)
    small_font = safe_font("/System/Library/Fonts/Supplemental/GillSans.ttc", 13)

    panel = (70, 60, 1330, 840)
    round_rect(draw, panel, 26, fill="#0f172a", outline="#223145", width=2)

    draw.text((120, 98), args.title, fill="#f0c878", font=title_font)

    for i, t in enumerate(["7d", "30d", "All"]):
        x = 430 + i * 80
        y = 108
        round_rect(draw, (x, y, x + 60, y + 26), 10, fill="#1f2937", outline="#334155", width=1)
        draw.text((x + 20, y + 5), t, fill="#d1d5db", font=small_font)

    card_w, card_h = 270, 110
    start_x, start_y = 120, 170
    pad_x = 22

    for idx, (label, val, delta) in enumerate(cards):
        x = start_x + idx * (card_w + pad_x)
        y = start_y
        round_rect(draw, (x, y, x + card_w, y + card_h), 18, fill="#111827", outline="#243047", width=1)
        draw.text((x + 18, y + 14), label, fill="#94a3b8", font=label_font)
        draw.text((x + 18, y + 48), val, fill="#e2e8f0", font=value_font)
        color = "#22c55e" if delta.startswith("+") else "#f97316"
        draw.text((x + 18, y + 86), delta, fill=color, font=small_font)

    # Action time card
    action_label, action_value, action_delta = action_card[0]
    round_rect(draw, (120, 300, 570, 390), 18, fill="#111827", outline="#243047", width=1)
    draw.text((140, 315), action_label, fill="#94a3b8", font=label_font)
    draw.text((140, 345), action_value, fill="#e2e8f0", font=value_font)
    action_color = "#22c55e" if action_delta.startswith("+") else "#f97316"
    draw.text((140, 370), action_delta, fill=action_color, font=small_font)

    # Action / idle split (static visual)
    round_rect(draw, (610, 300, 1220, 390), 18, fill="#111827", outline="#243047", width=1)
    draw.text((635, 315), "ACTION / IDLE SPLIT", fill="#94a3b8", font=label_font)
    bar_x, bar_y = 635, 350
    bar_w, bar_h = 520, 16
    round_rect(draw, (bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), 8, fill="#0b1220", outline="#1f2937", width=1)
    action_w = int(bar_w * 0.41)
    round_rect(draw, (bar_x, bar_y, bar_x + action_w, bar_y + bar_h), 8, fill="#38bdf8", outline=None, width=0)
    round_rect(draw, (bar_x + action_w, bar_y, bar_x + bar_w, bar_y + bar_h), 8, fill="#64748b", outline=None, width=0)
    draw.text((bar_x, bar_y + 24), "Action", fill="#cbd5f5", font=small_font)
    draw.text((bar_x + 120, bar_y + 24), "Idle", fill="#94a3b8", font=small_font)

    # Top skills list
    round_rect(draw, (120, 420, 570, 780), 18, fill="#111827", outline="#243047", width=1)
    draw.text((145, 445), "TOP SKILLS (TIME)", fill="#f8fafc", font=label_font)
    row_y = 480
    for name, value, share in skills[:5]:
        round_rect(draw, (145, row_y, 545, row_y + 48), 12, fill="#0b1220", outline="#1f2937", width=1)
        draw.text((165, row_y + 14), name, fill="#cbd5f5", font=label_font)
        draw.text((360, row_y + 14), value, fill="#e2e8f0", font=label_font)
        draw.text((475, row_y + 14), share, fill="#94a3b8", font=label_font)
        row_y += 60

    # Trend chart panel
    round_rect(draw, (610, 420, 1220, 780), 18, fill="#111827", outline="#243047", width=1)
    draw.text((635, 445), "XP + GOLD TREND", fill="#f8fafc", font=label_font)
    chart_x0, chart_y0 = 635, 485
    chart_x1, chart_y1 = 1195, 740
    round_rect(draw, (chart_x0, chart_y0, chart_x1, chart_y1), 12, fill="#0b1220", outline="#1f2937", width=1)

    xp_pts = []
    for i in range(8):
        x = chart_x0 + 30 + i * ((chart_x1 - chart_x0 - 60) / 7)
        y = chart_y1 - (30 + (math.sin(i / 2.2) + 1) * 0.44 * (chart_y1 - chart_y0 - 60))
        xp_pts.append((x, y))

    gold_pts = []
    for i in range(8):
        x = chart_x0 + 30 + i * ((chart_x1 - chart_x0 - 60) / 7)
        y = chart_y1 - (30 + (math.cos(i / 2.0) + 1) * 0.34 * (chart_y1 - chart_y0 - 60))
        gold_pts.append((x, y))

    for i in range(len(xp_pts) - 1):
        draw.line([xp_pts[i], xp_pts[i + 1]], fill="#38bdf8", width=3)
    for x, y in xp_pts:
        draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill="#38bdf8")

    for i in range(len(gold_pts) - 1):
        draw.line([gold_pts[i], gold_pts[i + 1]], fill="#f59e0b", width=3)
    for x, y in gold_pts:
        draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill="#f59e0b")

    round_rect(draw, (635, 750, 870, 775), 10, fill="#0b1220", outline="#1f2937", width=1)
    draw.text((650, 756), "XP (blue) / Gold (gold)", fill="#94a3b8", font=small_font)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    img.save(args.out)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
