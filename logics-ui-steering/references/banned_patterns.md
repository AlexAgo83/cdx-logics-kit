# Banned patterns and repeated failure modes

## Hard bans

- No oversized radii across every component.
- No pill overload.
- No detached floating shells as the default composition.
- No glassmorphism-first UI.
- No decorative blur haze or frosted panels as fake taste.
- No soft gradients used to simulate design quality.
- No generic dark SaaS dashboard composition by default.
- No dashboard hero strips inside internal tools without a real product reason.
- No decorative sidebar blobs, abstract glows, or ornamental background tricks.
- No fake charts, fake percentages, or fake KPI theater used only to fill space.
- No right-rail filler panels such as “today”, “focus”, or “schedule” unless product logic truly needs them.
- No quota widgets or progress bars that exist only to make the screen feel populated.
- No uppercase eyebrow labels or micro-headings as decoration.
- No ornamental helper cards that narrate obvious content.
- No fake premium copy or startup-style filler language.
- No transform-heavy hover effects, slide tricks, or bounce as the default interaction language.
- No dramatic shadows or glow-based hierarchy.
- No layouts that create dead space just to look expensive.
- No mobile collapse that becomes a repetitive stack of disconnected beige-sandwich cards.

## Repeated component mistakes

- Do not reuse the same rounded rectangle treatment for sidebar, cards, buttons, inputs, badges, and panels.
- Do not put a brand block at the top of a detached sidebar unless the information architecture needs it.
- Do not add nav badges such as counts or “live” labels without functional meaning.
- Do not decorate status with colored pseudo-dot theater unless that state really carries workflow meaning.
- Do not create nested panel taxonomies for style alone.
- Do not turn every table state into a badge collection.
- Do not use trend chips, trend colors, and up/down deltas unless there is real comparative product data.

## Copy and labeling bans

- Do not use labels such as `Live Pulse`, `Night Shift`, `Operator Checklist`, `Mission Control`, or similar invented tone unless the product voice genuinely uses them.
- Do not add explanatory mini-notes just to describe what the UI already shows.
- Do not rely on generic lines such as:
  - “one place to track what matters”
  - “operational clarity without the clutter”
  - “everything your team needs today”
- Do not use decorative `small` labels above normal headings as a default section pattern.

## Forbidden structures

Avoid structures like these unless the product explicitly calls for them.

```html
<div class="section-intro">
  <small>TEAM COMMAND</small>
  <h2>One place to track what matters today.</h2>
  <p>Decorative copy that narrates the interface instead of helping the user.</p>
</div>
```

```html
<div class="focus-note">
  <small>Focus</small>
  <strong>Keep blockers visible and updates brief.</strong>
</div>
```

## Visual failure modes to watch for

- Blue-black gradient backgrounds with cyan accents used as a shortcut for “premium”.
- Muted gray-blue text that weakens contrast and clarity.
- Hover transforms that shift nav items or cards by a few pixels for no good reason.
- Decorative schedule rails, activity sidebars, and non-functional status columns.
- Canvas charts inside glossy cards without product-specific data needs.
- Donut charts paired with hand-wavy percentages.
- Progress bars with gradient fills that carry no real task logic.
- Footer meta lines that only advertise the mockup, theme, or file type.

## Decision rule

If a choice feels like the easiest generic AI UI move, reject it and pick the cleaner, more ordinary option.
