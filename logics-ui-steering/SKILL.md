---
name: logics-ui-steering
description: Steer frontend UI generation away from generic AI-looking layouts and toward grounded, product-native interfaces. Use whenever generating or refining HTML, CSS, React, Vue, Svelte, or other frontend UI code, especially when the result looks too decorative, too glossy, too dashboard-templated, or when existing project styles and tokens must be preserved.
---

# UI steering

Use this skill whenever generating or refining frontend UI code.

This skill is not a broad UX strategy workflow. It is a narrow implementation-time guardrail for code generation and UI refinement.

## Quick start

1. Inspect the target project before choosing colors, spacing, or layout language.
   - Reuse existing tokens, CSS variables, theme files, components, and typography first.
2. If the project already has a design system, follow it.
   - Use this skill as a guardrail against lazy defaults, not as a replacement brand.
3. Apply the grounded baseline in `references/primitives.md`.
4. Reject the repeated anti-patterns in `references/banned_patterns.md`.
5. If no project palette exists, choose from `references/palettes.md`.
6. Check the result on desktop and mobile, and keep accessibility sanity intact.

## Activation

- Explicit activation:
  - use `$logics-ui-steering`
  - or select the paired agent from the Logics agent picker
- Automatic triggering:
  - this skill should match frontend-generation and UI-refinement requests because the metadata explicitly names HTML, CSS, React, Vue, Svelte, and generic frontend UI work

## Operating rules

- Prefer ordinary, believable UI structure over decorative flair.
- Keep hierarchy in layout, spacing, alignment, contrast, and content order.
- If a user explicitly asks for a stylistic exception, comply deliberately instead of drifting into default AI UI habits by accident.
- Landing pages can have real sections. Internal tools should not inherit landing-page theatrics without product reason.
- Do not invent fake metrics, fake charts, or filler content to make a screen look complete.

## Read these references

- `references/primitives.md`
  - Grounded defaults for common layout and component primitives.
- `references/banned_patterns.md`
  - Hard bans, repeated failure modes, and forbidden copy patterns.
- `references/palettes.md`
  - Project-first color policy and curated fallback light/dark palettes.
