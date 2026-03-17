# Grounded UI primitives

Use these defaults when the project does not already define a stronger pattern.

## Layout

- Sidebars:
  - fixed practical width, usually `240px` to `260px`
  - solid surface, simple divider, no floating outer shell
- Headers:
  - plain hierarchy with real `h1`/`h2`
  - no decorative eyebrow labels or gradient text
- Sections:
  - ordinary padding, usually `20px` to `32px`
  - no hero strip inside a working dashboard without product reason
- Containers:
  - centered or application-native width
  - predictable padding, no “creative” widths for effect
- Grids and flex:
  - consistent columns and gaps
  - no overlap tricks, no asymmetry for fake premium feel
- Panels:
  - simple surface separation
  - border first, shadow second
- Toolbars:
  - straightforward horizontal actions
  - standard height, no decorative framing
- Footers and breadcrumbs:
  - keep them plain and functional

## Components

- Navigation:
  - simple links, clear active state, restrained hover
  - no count badges unless they are genuinely useful
- Buttons:
  - solid or outlined
  - radius usually `8px` to `10px`
  - no pill shapes by default
- Cards:
  - simple containers
  - radius usually `8px` to `12px`
  - no detached floating effect
- Forms:
  - labels above inputs
  - explicit helper/error text only when needed
- Inputs:
  - solid borders and direct focus states
  - no animated underlines or morphing shapes
- Modals:
  - centered overlay, simple backdrop, straightforward actions
- Dropdowns:
  - plain list, subtle elevation, clear selection state
- Tables:
  - left-aligned content, readable row density, subtle hover
  - avoid over-badging every cell
- Lists:
  - consistent spacing and visual rhythm
- Tabs:
  - underline or border indicator
  - avoid pill-tab styling as a default
- Badges:
  - small, restrained, functional only
- Avatars and icons:
  - simple shapes, no decorative rings or icon backgrounds

## Typography and spacing

- Typography:
  - use the project font stack first
  - otherwise use a restrained sans-serif choice already established in the codebase
  - prioritize readable body sizes and clear heading hierarchy
- Spacing:
  - stick to a stable scale such as `4/8/12/16/24/32`
  - use spacing to show grouping instead of decorative dividers
- Borders:
  - `1px` solid, low-drama colors
- Shadows:
  - subtle only, usually no stronger than a soft `0 2px 8px`
- Motion:
  - `100ms` to `200ms`
  - favor color, opacity, and border changes over transforms

## Content discipline

- Titles should name the screen or section directly.
- Labels should be concrete and product-specific.
- Helper text should explain a real ambiguity, not decorate the screen.
- Internal tools should feel operational and calm, not like a marketing landing page.

## Mobile

- Do not collapse everything into one long column of near-identical cards.
- Preserve grouping and hierarchy when reducing density.
- Keep actions discoverable without turning every section into an isolated floating block.
