---
name: color-and-ux
description: Choose colours and UI/UX patterns that work.
---

# Colour and UX Skill

The rules every screen Lyra builds must pass: how to pick a palette that
fits the brand and reads well, and the interface and experience basics that
keep people from getting lost. It decides colour, layout, type and
interaction defaults; it does not replace the brand or an approved template.

## When to Use

- Before any UI is built (with `ui-designer`), and again before QA signs off.
- Whenever a colour, font size, spacing or interaction is being chosen.
- When a template or brand palette is adapted to new content or a dark mode.

## Prerequisites

- The approved requirements and, when present, the template spec or brand.
- `scripts/palette.py` (standard library; `from-image` needs Pillow).

## How to Run

Pick the palette with the rules below, write it as tokens (CSS custom
properties), then measure it — never judge contrast by eye:

```
python scripts/palette.py check bg=#… surface=#… text=#… muted=#… accent=#… on-accent=#… success=#… danger=#…
python scripts/palette.py ramp "#brand"        # 50…950 shades, even in lightness
python scripts/palette.py from-image hero.jpg  # colours to echo from the hero picture
```

Exit code 1 is a failed palette: fix it before building.

## Quick Reference

| Rule | Value |
|---|---|
| Body text contrast | ≥ 4.5:1 (aim 7:1 for long reading) |
| Large text (≥ 24 px, or ≥ 19 px bold) and UI parts | ≥ 3:1 |
| Colour proportions | ~60% neutral base · 30% supporting · 10% accent |
| Accent colours | one per page (two only with a clear reason) |
| Line length | 45–75 characters; line height 1.5–1.7 for body |
| Type scale | one ratio (1.2–1.333); 3–5 sizes per page |
| Spacing | a 4/8 px scale; more space between groups than inside them |
| Touch targets | ≥ 44 × 44 px, ≥ 8 px apart |
| Motion | 150–300 ms for UI feedback, 0.6–1.4 s for storytelling |

## Procedure

### 1. Choose the palette

1. **Start from what exists.** Brand colours, the template palette, the hero
   picture (`from-image`): echo its dominant warm or cool tone in neutrals and
   take the accent from it or its complement. Never fight the photography.
2. **Pick a harmony on purpose.** Monochrome (one hue, many lightnesses:
   calm, premium); analogous (neighbours on the wheel: warm and natural);
   complementary (opposites: energy, use the second colour sparingly);
   split-complementary (safer contrast). Name the choice in the brief.
3. **Neutrals carry the page.** Tint greys slightly toward the brand hue
   (never pure #000 or flat #808080). Dark mode base: near-black like
   #0b0d12, not #000; light mode base: off-white like #f7f5f0 or pure white
   for products.
4. **Build shades in OKLCH** (`ramp`), not by mixing with black/white, so
   steps look even. Use 500–700 shades for text and buttons on light
   backgrounds, 200–400 on dark ones.
5. **Meaning colours are fixed jobs**: success green, warning amber, danger
   red, info blue — never reused as decoration, never the only signal (add an
   icon or word; check colour-blind warnings).
6. **Mood by audience** (a starting point, not a law): finance/health — calm
   blues, greens, generous white; luxury — dark base, one metallic or deep
   accent, lots of space; food — warm reds, oranges, creams; kids/play —
   bright, high-chroma but still contrast-checked; tech/AI — dark base, one
   luminous accent; eco/charity — natural greens, sand, sea blues.
7. **Dark mode** is its own palette: lower saturation, lighter accents,
   elevation by lighter surfaces (not shadows), re-run `check`.

### 2. Lay out for scanning

- One clear focal point per screen; the primary action is the most
  contrasting element; secondary actions are quieter (outline or text).
- Visual hierarchy by size, weight and space before colour. Left-aligned
  text for reading; centre only short headings.
- Group related things (proximity), align to a grid, keep consistent gaps.
- Mobile first: single column, thumb-reachable actions, no hover-only
  information, no sideways scroll.

### 3. Make every interaction answer back

- Every control has hover, focus-visible (a clear ring ≥ 3:1), active,
  disabled and loading states; every list has empty, loading and error states
  with a way forward.
- Forms: visible labels (not placeholder-only), inline errors next to the
  field in words ("Enter an email like name@example.com"), keep what the user
  typed, one column, sensible keyboard types.
- Feedback within 100 ms; anything over 1 s shows progress; destructive
  actions confirm or offer undo.
- Navigation: say where the user is, keep the same place for the same thing
  on every page, at most 7 top-level items.
- Respect `prefers-reduced-motion` and `prefers-color-scheme`; never move
  content the user is reading.

### 4. Check before handing over

Run `palette.py check` on the final tokens, open the page at 390 px and
1440 px, tab through it with the keyboard, and compare against the template
or brief. Record the palette and its check result in the design brief.

## Pitfalls

- Grey text on coloured backgrounds (fails contrast); use a tint of the
  background's hue instead.
- White text on mid-tone brand colours (blue #3b82f6, orange, green): it
  usually fails 4.5:1 — darken the button one or two shades.
- Many accents: if everything is highlighted, nothing is.
- Pure black backgrounds with pure white text cause glare; soften both.
- Colour alone for status, links in body text without underline, or charts
  that only differ by hue.
- Changing the template's palette without re-checking it.

## Verification

- `palette.py check` exits 0 on the shipped tokens; colour-blind warnings
  were handled with icons or labels.
- Every interactive element has visible focus and its states; forms show
  inline errors in words.
- At 390 px nothing scrolls sideways and every tap target is ≥ 44 px.
