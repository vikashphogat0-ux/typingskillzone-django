# DESIGN_SYSTEM.md — Stage 2 (tokens and components)

Source of truth: `static/css/site.css`, `:root` block.

## Colour

| Token | Value | Use |
|---|---|---|
| `--navy` | #101B36 | Footer, dark surfaces |
| `--navy-2` | #182849 | Secondary dark surfaces |
| `--brand` | #2563EB | Primary buttons, links, active states |
| `--brand-dark` | #1D4ED8 | Hover on brand |
| `--accent` | #3B82F6 | Gradients, highlights |
| `--bg-light` | #EFF6FF | Eyebrows, soft highlight panels |
| `--bg` | #F8FAFC | Page background |
| `--surface` | #FFFFFF | Cards, panels |
| `--ink` | #172033 | Main text and headings |
| `--ink-2` | #334155 | Body text |
| `--muted` | #64748B | Secondary text |
| `--line` | #E2E8F0 | Borders |
| `--success` | #16A34A | Verified, success |
| `--warn` | #B45309 | Warning text (readable on white) |
| `--warn-bg` | #F59E0B | Warning accent |
| `--error` | #DC2626 | Errors |

Contrast: `--ink` on `--surface` and `--muted` on `--surface` meet WCAG AA for body text. Re-check any new combination.

## Typography

- Font stack: Inter, Manrope, then system fonts. No web-font requests (keeps the security policy strict).
- Hindi: system Devanagari fonts render through the stack. Verify on Windows and Android before launch.
- Scale: H1 32–52px (800), H2 24–34px (800), H3 18px (700), body 16px / 1.65.

## Spacing and shape

- Container: `min(100% − 40px, 1160px)`, 14px on phones.
- Radius: 16px cards, 12px controls, 999px pills.
- Shadows: `--shadow-sm` for resting cards, `--shadow` for hover and feature panels.

## Components (in site.css)

- Layout: `.site-header`, `.site-main`, `.site-footer`, `.container`, `.section`, `.section-head`.
- Buttons: `.btn`, `.btn-primary`, `.btn-ghost`.
- Cards and grids: `.card`, `.grid`, `.grid-2`, `.grid-3`, `.step`, `.steps`.
- Forms: `.auth-panel`, `.form-field`, `.error-box`, `.error`.
- Exams: `.exam-card`, `.exam-grid`, `.exam-badge`, `.status.ok`, `.status.warn`, `.pattern-grid`, `.passage-list`.
- Filters: `.chip`, `.chip-row`, `.chip.active`, `.field-label`.
- Pills and eyebrows: `.pill`, `.eyebrow`, `.kicker`.

## Responsive rules

- 900px: two-column hero collapses to one column.
- 640px: cards and grids reduce padding; exam grid shows two columns.
- Motion: `prefers-reduced-motion` disables transitions.

## Rules for new code

1. Use tokens, never raw hex values in templates.
2. No inline `<style>` blocks; add classes to `site.css`.
3. No external fonts, scripts or CDNs (Content-Security-Policy).
4. Icons: text or inline SVG only.
