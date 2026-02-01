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


def parse_rows(raw: str, entry_label: str, fields: int) -> List[Tuple[str, ...]]:
    if not raw:
        return []
    items: List[Tuple[str, ...]] = []
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split("|")]
        if len(parts) != fields:
            raise SystemExit(
                f"Invalid {entry_label} entry: '{chunk}'. Expected {fields} fields separated by '|'."
            )
        items.append(tuple(parts))
    return items


def safe_font(path: str, size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def round_rect(draw: ImageDraw.ImageDraw, xy, radius, fill, outline=None, width=1):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill, outline=outline, width=width)


def render_vscode(args) -> int:
    w, h = 1280, 800
    img = Image.new("RGB", (w, h), "#1e1e1e")
    draw = ImageDraw.Draw(img)

    title_font = safe_font("/System/Library/Fonts/Supplemental/GillSans.ttc", 16)
    label_font = safe_font("/System/Library/Fonts/Supplemental/GillSans.ttc", 13)
    small_font = safe_font("/System/Library/Fonts/Supplemental/GillSans.ttc", 11)

    title = args.title if args.title != "OVERVIEW" else "LOGICS ORCHESTRATOR"
    columns = [c.strip() for c in args.columns.split("|") if c.strip()]
    detail_lines = [l.strip() for l in args.detail_lines.split("|") if l.strip()]

    def default_items(name: str) -> List[str]:
        lowered = name.lower()
        if "request" in lowered:
            return ["req_000_kickoff", "req_001_new_flow", "req_002_import"]
        if "backlog" in lowered:
            return ["item_001_scope", "item_002_ui", "item_003_parser"]
        if "task" in lowered:
            return ["task_001_index", "task_002_views", "task_003_actions"]
        if "spec" in lowered:
            return ["spec_001_kickoff", "spec_002_mvp", "spec_003_ux"]
        return ["item_001", "item_002", "item_003"]

    # Title bar
    draw.rectangle([0, 0, w, 28], fill="#3c3c3c")
    draw.text((12, 6), title, fill="#d4d4d4", font=label_font)

    # Activity bar + side bar
    draw.rectangle([0, 28, 52, h], fill="#333333")
    draw.rectangle([52, 28, 302, h], fill="#252526")
    draw.text((70, 40), "LOGICS", fill="#c8c8c8", font=label_font)

    sidebar_y = 70
    for col in columns[:6]:
        draw.text((70, sidebar_y), f"- {col}", fill="#9aa0a6", font=small_font)
        sidebar_y += 18

    # Editor area + tab bar
    editor_x = 302
    draw.rectangle([editor_x, 28, w, h], fill="#1e1e1e")
    draw.rectangle([editor_x, 28, w, 64], fill="#2d2d2d")
    draw.text((editor_x + 12, 38), "Logics Board", fill="#e5e5e5", font=label_font)

    # Detail panel
    detail_w = 320
    detail_x0 = w - detail_w - 16
    detail_y0 = 80
    detail_x1 = w - 16
    detail_y1 = h - 16
    round_rect(draw, (detail_x0, detail_y0, detail_x1, detail_y1), 10, fill="#1f1f1f", outline="#3a3a3a", width=1)
    draw.text((detail_x0 + 12, detail_y0 + 12), args.detail_title, fill="#e5e5e5", font=label_font)

    line_y = detail_y0 + 36
    for line in detail_lines[:8]:
        draw.text((detail_x0 + 12, line_y), line, fill="#b9bbbe", font=small_font)
        line_y += 16

    # Board area
    board_x0 = editor_x + 12
    board_y0 = 80
    board_x1 = detail_x0 - 12
    board_y1 = h - 16

    col_gap = 12
    col_count = max(1, len(columns))
    col_w = int((board_x1 - board_x0 - col_gap * (col_count - 1)) / col_count)

    for idx, col in enumerate(columns):
        col_x0 = board_x0 + idx * (col_w + col_gap)
        col_x1 = col_x0 + col_w
        round_rect(draw, (col_x0, board_y0, col_x1, board_y1), 10, fill="#202020", outline="#333333", width=1)
        draw.text((col_x0 + 10, board_y0 + 10), col, fill="#e5e5e5", font=label_font)

        card_y = board_y0 + 38
        for item in default_items(col)[:4]:
            round_rect(draw, (col_x0 + 8, card_y, col_x1 - 8, card_y + 44), 8, fill="#252526", outline="#3a3a3a", width=1)
            draw.text((col_x0 + 16, card_y + 14), item, fill="#cfd2d6", font=small_font)
            card_y += 54

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    img.save(args.out)
    print(args.out)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a quick PNG UI mockup.")
    parser.add_argument("--out", required=True, help="Output PNG path (default: logics/external/...).")
    parser.add_argument(
        "--preset",
        choices=["default", "vscode"],
        default="default",
        help="Preset style to generate.",
    )
    parser.add_argument(
        "--mode",
        choices=["overview", "breakdown"],
        default="overview",
        help="Mockup layout to generate.",
    )
    parser.add_argument(
        "--layout",
        choices=["desktop", "mobile"],
        default="desktop",
        help="Viewport layout.",
    )
    parser.add_argument("--title", default="OVERVIEW", help="Main title text.")
    parser.add_argument(
        "--columns",
        default="Requests|Backlog|Tasks|Specs",
        help="Column labels for vscode preset, separated by '|'.",
    )
    parser.add_argument(
        "--detail-title",
        default="Details",
        help="Detail panel title for vscode preset.",
    )
    parser.add_argument(
        "--detail-lines",
        default="ID: req_000_kickoff|Stage: request|Status: draft|Owner: you|Updated: today",
        help="Detail panel lines for vscode preset, separated by '|'.",
    )
    parser.add_argument(
        "--tabs",
        default="Overview|Breakdown",
        help="Tab labels separated by '|', e.g. \"Overview|Breakdown\".",
    )
    parser.add_argument(
        "--cards",
        default="Metric A|52,180|+9.1%;Metric B|8,340|+2.6%;Metric C|1,284|+3.4%;Metric D|9h 10m|-18m",
        help="Semicolon-separated cards: Label|Value|Delta",
    )
    parser.add_argument(
        "--action-time",
        default="Active time|6h 22m|+41m",
        help="Action time card: Label|Value|Delta",
    )
    parser.add_argument(
        "--skills",
        default="Category A|1h 32m|24%;Category B|1h 06m|17%;Category C|58m|15%;Category D|46m|12%;Category E|39m|10%",
        help="Top skills list: Name|Time|Share;...",
    )
    parser.add_argument("--split-title", default="ACTIVE / INACTIVE SPLIT", help="Split bar title.")
    parser.add_argument("--top-title", default="TOP CATEGORIES (TIME)", help="Top list title.")
    parser.add_argument("--trend-title", default="METRIC A + METRIC B TREND", help="Trend chart title.")
    parser.add_argument("--trend-legend", default="Metric A / Metric B", help="Trend legend label.")
    parser.add_argument("--breakdown-title", default="Base + modifiers breakdown", help="Breakdown section title.")
    parser.add_argument(
        "--breakdown-headers",
        default="STAT|BASE|MOD A|MOD B|MOD C|TOTAL",
        help="Breakdown headers separated by '|'.",
    )
    parser.add_argument(
        "--stats",
        default="Attribute A|10|+2|+1|+1|14;Attribute B|9|+1|+0|+2|12;Attribute C|11|+0|+2|+0|13;Attribute D|8|+3|+1|+0|12;Attribute E|7|+0|+1|+2|10",
        help="Breakdown rows: Stat|Base|Mod A|Mod B|Mod C|Total;...",
    )

    args = parser.parse_args()

    if args.preset == "vscode":
        return render_vscode(args)

    cards = parse_triplets(args.cards, "card")
    action_card = parse_triplets(args.action_time, "action-time")
    skills = parse_triplets(args.skills, "skills")
    stats_rows = parse_rows(args.stats, "stats", 6)
    if not action_card:
        raise SystemExit("--action-time is required.")

    if args.layout == "mobile":
        w, h = 900, 1500
    else:
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

    title = args.title
    draw.text((120, 98), title, fill="#f0c878", font=title_font)

    tab_labels = [t.strip() for t in args.tabs.split("|") if t.strip()]
    tab_w = 120
    tab_step = 140
    for i, t in enumerate(tab_labels[:2]):
        x = 430 + i * tab_step
        y = 108
        round_rect(draw, (x, y, x + tab_w, y + 26), 10, fill="#1f2937", outline="#334155", width=1)
        draw.text((x + 16, y + 5), t, fill="#d1d5db", font=small_font)

    if args.mode == "breakdown":
        if args.layout == "mobile":
            round_rect(draw, (120, 170, 780, 1380), 20, fill="#111827", outline="#243047", width=1)
            draw.text((145, 195), args.breakdown_title, fill="#94a3b8", font=label_font)
            row_y = 240
            for stat, base, mod_a, mod_b, mod_c, total in stats_rows[:8]:
                round_rect(draw, (145, row_y, 755, row_y + 120), 12, fill="#0b1220", outline="#1f2937", width=1)
                draw.text((165, row_y + 14), stat, fill="#e2e8f0", font=label_font)
                draw.text((165, row_y + 44), f"Base {base}", fill="#cbd5f5", font=small_font)
                draw.text((280, row_y + 44), f"A {mod_a}", fill="#22c55e", font=small_font)
                draw.text((365, row_y + 44), f"B {mod_b}", fill="#38bdf8", font=small_font)
                draw.text((450, row_y + 44), f"C {mod_c}", fill="#f59e0b", font=small_font)
                draw.text((165, row_y + 76), f"Total {total}", fill="#f8fafc", font=label_font)
                row_y += 140
        else:
            round_rect(draw, (120, 170, 1220, 760), 20, fill="#111827", outline="#243047", width=1)
            draw.text((145, 195), args.breakdown_title, fill="#94a3b8", font=label_font)

            header_y = 235
            headers = [h.strip() for h in args.breakdown_headers.split("|") if h.strip()]
            col_x = [145, 360, 470, 580, 690, 800]
            for label, x in zip(headers, col_x):
                draw.text((x, header_y), label, fill="#cbd5f5", font=label_font)

            row_y = 275
            for stat, base, mod_a, mod_b, mod_c, total in stats_rows[:8]:
                round_rect(draw, (145, row_y, 1180, row_y + 56), 12, fill="#0b1220", outline="#1f2937", width=1)
                draw.text((160, row_y + 16), stat, fill="#e2e8f0", font=label_font)
                draw.text((360, row_y + 16), base, fill="#e2e8f0", font=label_font)
                draw.text((470, row_y + 16), mod_a, fill="#22c55e", font=label_font)
                draw.text((580, row_y + 16), mod_b, fill="#38bdf8", font=label_font)
                draw.text((690, row_y + 16), mod_c, fill="#f59e0b", font=label_font)
                draw.text((800, row_y + 16), total, fill="#f8fafc", font=label_font)
                row_y += 66

        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        img.save(args.out)
        print(args.out)
        return 0

    if args.layout == "mobile":
        card_w, card_h = 640, 110
        start_x, start_y = 120, 200
        pad_x = 0
        row_gap = 16
        for idx, (label, val, delta) in enumerate(cards[:6]):
            x = start_x
            y = start_y + idx * (card_h + row_gap)
            round_rect(draw, (x, y, x + card_w, y + card_h), 18, fill="#111827", outline="#243047", width=1)
            draw.text((x + 18, y + 14), label, fill="#94a3b8", font=label_font)
            draw.text((x + 18, y + 48), val, fill="#e2e8f0", font=value_font)
            color = "#22c55e" if delta.startswith("+") else "#f97316"
            draw.text((x + 18, y + 86), delta, fill=color, font=small_font)

        y_base = start_y + len(cards[:6]) * (card_h + row_gap) + 12
        action_label, action_value, action_delta = action_card[0]
        round_rect(draw, (120, y_base, 760, y_base + 90), 18, fill="#111827", outline="#243047", width=1)
        draw.text((140, y_base + 12), action_label, fill="#94a3b8", font=label_font)
        draw.text((140, y_base + 42), action_value, fill="#e2e8f0", font=value_font)
        action_color = "#22c55e" if action_delta.startswith("+") else "#f97316"
        draw.text((140, y_base + 70), action_delta, fill=action_color, font=small_font)

        split_y = y_base + 110
        round_rect(draw, (120, split_y, 760, split_y + 90), 18, fill="#111827", outline="#243047", width=1)
        draw.text((140, split_y + 12), args.split_title, fill="#94a3b8", font=label_font)
        bar_x, bar_y = 140, split_y + 46
        bar_w, bar_h = 560, 14
        round_rect(draw, (bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), 7, fill="#0b1220", outline="#1f2937", width=1)
        action_w = int(bar_w * 0.41)
        round_rect(draw, (bar_x, bar_y, bar_x + action_w, bar_y + bar_h), 7, fill="#38bdf8", outline=None, width=0)
        round_rect(draw, (bar_x + action_w, bar_y, bar_x + bar_w, bar_y + bar_h), 7, fill="#64748b", outline=None, width=0)

        list_y = split_y + 120
        round_rect(draw, (120, list_y, 760, list_y + 360), 18, fill="#111827", outline="#243047", width=1)
        draw.text((145, list_y + 18), args.top_title, fill="#f8fafc", font=label_font)
        row_y = list_y + 56
        for name, value, share in skills[:5]:
            round_rect(draw, (145, row_y, 735, row_y + 48), 12, fill="#0b1220", outline="#1f2937", width=1)
            draw.text((165, row_y + 14), name, fill="#cbd5f5", font=label_font)
            draw.text((440, row_y + 14), value, fill="#e2e8f0", font=label_font)
            draw.text((610, row_y + 14), share, fill="#94a3b8", font=label_font)
            row_y += 60

        chart_y = list_y + 390
        round_rect(draw, (120, chart_y, 760, chart_y + 360), 18, fill="#111827", outline="#243047", width=1)
        draw.text((145, chart_y + 18), args.trend_title, fill="#f8fafc", font=label_font)
        chart_x0, chart_y0 = 145, chart_y + 60
        chart_x1, chart_y1 = 735, chart_y + 310
        round_rect(draw, (chart_x0, chart_y0, chart_x1, chart_y1), 12, fill="#0b1220", outline="#1f2937", width=1)
        xp_pts = []
        for i in range(8):
            x = chart_x0 + 20 + i * ((chart_x1 - chart_x0 - 40) / 7)
            y = chart_y1 - (20 + (math.sin(i / 2.2) + 1) * 0.44 * (chart_y1 - chart_y0 - 40))
            xp_pts.append((x, y))
        gold_pts = []
        for i in range(8):
            x = chart_x0 + 20 + i * ((chart_x1 - chart_x0 - 40) / 7)
            y = chart_y1 - (20 + (math.cos(i / 2.0) + 1) * 0.34 * (chart_y1 - chart_y0 - 40))
            gold_pts.append((x, y))
        for i in range(len(xp_pts) - 1):
            draw.line([xp_pts[i], xp_pts[i + 1]], fill="#38bdf8", width=3)
        for x, y in xp_pts:
            draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill="#38bdf8")
        for i in range(len(gold_pts) - 1):
            draw.line([gold_pts[i], gold_pts[i + 1]], fill="#f59e0b", width=3)
        for x, y in gold_pts:
            draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill="#f59e0b")
        round_rect(draw, (145, chart_y + 320, 370, chart_y + 345), 10, fill="#0b1220", outline="#1f2937", width=1)
        draw.text((155, chart_y + 326), args.trend_legend, fill="#94a3b8", font=small_font)

        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        img.save(args.out)
        print(args.out)
        return 0

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

    # Active / inactive split (static visual)
    round_rect(draw, (610, 300, 1220, 390), 18, fill="#111827", outline="#243047", width=1)
    draw.text((635, 315), args.split_title, fill="#94a3b8", font=label_font)
    bar_x, bar_y = 635, 350
    bar_w, bar_h = 520, 16
    round_rect(draw, (bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), 8, fill="#0b1220", outline="#1f2937", width=1)
    action_w = int(bar_w * 0.41)
    round_rect(draw, (bar_x, bar_y, bar_x + action_w, bar_y + bar_h), 8, fill="#38bdf8", outline=None, width=0)
    round_rect(draw, (bar_x + action_w, bar_y, bar_x + bar_w, bar_y + bar_h), 8, fill="#64748b", outline=None, width=0)
    draw.text((bar_x, bar_y + 24), "Active", fill="#cbd5f5", font=small_font)
    draw.text((bar_x + 120, bar_y + 24), "Inactive", fill="#94a3b8", font=small_font)

    # Top skills list
    round_rect(draw, (120, 420, 570, 780), 18, fill="#111827", outline="#243047", width=1)
    draw.text((145, 445), args.top_title, fill="#f8fafc", font=label_font)
    row_y = 480
    for name, value, share in skills[:5]:
        round_rect(draw, (145, row_y, 545, row_y + 48), 12, fill="#0b1220", outline="#1f2937", width=1)
        draw.text((165, row_y + 14), name, fill="#cbd5f5", font=label_font)
        draw.text((360, row_y + 14), value, fill="#e2e8f0", font=label_font)
        draw.text((475, row_y + 14), share, fill="#94a3b8", font=label_font)
        row_y += 60

    # Trend chart panel
    round_rect(draw, (610, 420, 1220, 780), 18, fill="#111827", outline="#243047", width=1)
    draw.text((635, 445), args.trend_title, fill="#f8fafc", font=label_font)
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
    draw.text((650, 756), args.trend_legend, fill="#94a3b8", font=small_font)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    img.save(args.out)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
