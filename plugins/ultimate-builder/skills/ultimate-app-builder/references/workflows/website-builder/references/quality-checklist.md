# Quality checklist

Run every section on the built site before QA, after any large change, and
before launch. Fix, rebuild, re-run; report any line left open as a known
gap. Sources: web.dev Core Web Vitals, WCAG 2.2 AA, and recurring design
audit prompts (performance slim-down, theming with AA contrast, scannable
semantic pages).

## Contents
- Speed and weight
- Theme and contrast
- Responsive
- Accessibility
- SEO and sharing
- Forms and links
- Final look

## Speed and weight

- [ ] Audit file size and loading: list unused CSS, unused JS imports,
      uncompressed images and render-blocking scripts; fix the five with
      the biggest effect and say what each saved.
- [ ] Scripts load `type="module"` or `defer`; nothing blocks first paint
      except critical CSS.
- [ ] Images in WebP/AVIF at display size with width/height; hero ≤ 250 KB.
- [ ] At most two font families, subset where possible, `font-display: swap`.
- [ ] Targets: LCP ≤ 2.5 s, CLS ≤ 0.1, INP ≤ 200 ms (Lighthouse mobile
      performance ≥ 85 when Lighthouse is available).
- [ ] 3D, video and heavy effects load only when near the viewport and stop
      when off-screen.

## Theme and contrast

- [ ] All colours come from CSS custom properties; no stray hex values in
      components.
- [ ] Light/dark: when both exist, the theme is applied before first paint
      (no flash) and respects `prefers-color-scheme`, with a toggle that
      remembers the choice.
- [ ] `palette.py check` (from `color-and-ux`) passes for every text /
      background pair in **every** theme: body text ≥ 4.5:1, large text and
      UI parts ≥ 3:1.
- [ ] Text over pictures sits on a scrim or a calm area and still passes.

## Responsive

- [ ] 390, 768, 1024 and 1440 px: no sideways scroll, nothing clipped.
- [ ] Tap targets ≥ 24 × 24 px (44 px preferred) with spacing.
- [ ] Phone hero shows the headline and call to action without scrolling.
- [ ] Use `svh`/`dvh` instead of `100vh` for full-height sections.

## Accessibility

- [ ] One `<h1>`, headings in order, landmarks (`header`, `nav`, `main`,
      `footer`).
- [ ] Every interactive element reachable and usable by keyboard, with a
      visible focus ring.
- [ ] Meaningful `alt` text; decorative images `alt=""`.
- [ ] `prefers-reduced-motion`: animations off or reduced; nothing important
      only appears through motion.
- [ ] Language set on `<html lang>`; link text says where it goes.

## SEO and sharing

- [ ] Unique `<title>` (≤ 60 characters) and meta description (≤ 155) per page.
- [ ] Open Graph and Twitter card tags with a 1200 × 630 share image.
- [ ] Favicon set (SVG + 180 px Apple touch icon).
- [ ] Semantic HTML that is easy to scan; JSON-LD `Organization` or
      `SoftwareApplication` when the site is public.
- [ ] `robots.txt` and `sitemap.xml` for a public multi-page site.

## Forms and links

- [ ] Labels on every field, clear errors next to the field, success state.
- [ ] No dead links or `href="#"` left behind; external links open safely.
- [ ] Form submission goes somewhere real (the owner's service or email) or
      is clearly marked as not connected yet.

## Final look

- [ ] Spacing rhythm consistent (one scale), alignments line up across
      sections.
- [ ] Nothing looks generic: no default purple gradient, no centred-
      everything layout, no stock icon row, no lorem ipsum.
- [ ] Every placeholder is visible as a placeholder and listed in the report.
