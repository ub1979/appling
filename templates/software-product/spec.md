# Template: Software Product

A product site for [PRODUCT — one line on what it does and for whom]: light
and crisp, with real product screens as the main picture, a bento grid of
capabilities and a working light/dark switch.

## Stack
Vite + TypeScript, GSAP + ScrollTrigger. Static output. Both themes are CSS
custom properties; a tiny inline script in `<head>` applies the saved or
system theme before first paint.

## Mood
Confident and calm: warm off-white, graphite text, one electric-orange
accent (dark text on it), a green for "done". A characterful display face
(e.g. Bricolage Grotesque) for headings, a friendly sans (e.g. Figtree) for
text. Rounded cards, generous spacing, soft shadows; the dark theme mirrors
it on near-black.

## Sections
1. **Nav** — logo, four links, theme switch, primary button.
2. **Hero** — outcome headline with one accented phrase, one-line subhead,
   two calls to action, then a large product screen in browser chrome
   (drawn in HTML or a real screenshot) that rises into place.
3. **Logo strip** — customer wordmarks (real ones only).
4. **Problem → outcome** — "Before" and "With [PRODUCT]" cards side by side.
5. **Three feature rows** — alternating sides; each has a small UI vignette
   that acts out the job when it scrolls in (rows tick to matched, approval
   stamps land, bars grow).
6. **Bento grid** — 7 capabilities in tiles of mixed size: one big dark
   tile, a big number, an integrations marquee, a code snippet, short
   text tiles.
7. **Testimonial** — one real quote with name, role and company.
8. **Pricing** — three plans, recommended one highlighted, monthly / yearly
   switch.
9. **FAQ** — 4–8 questions as `<details>`.
10. **Final call to action** — dark panel, headline, two buttons; footer.

## Effects to check
Theme switch works, remembers the choice and shows no flash on reload ·
both themes readable everywhere · hero screen rises, rows slide in, the
match bar fills · each vignette plays once when it arrives · marquee loops
· pricing switch changes every price · bento becomes one column on phones ·
reduced motion shows everything at once, marquee still.

## Motion rules
Easing power3/expo, never linear on objects; one orchestrated page load;
each section animates once on arrival; at most two ambient animations on
screen; transitions 0.4–1.3 s.

## Quality
Animate only transform/opacity; contrast passes in BOTH themes
(`palette.py check` per theme); fully responsive with no sideways scroll at
390 px; tap targets ≥ 24 px; visible focus rings; one `<h1>`; meta
description and share tags; Lighthouse performance ≥ 85.

## Ask the owner (one question at a time)
The product's real screens (attach with 📎) or permission to draw a
simplified UI; the one-line promise and who it is for; the three jobs the
product does; real customers, logos and a quote they may show (otherwise
placeholders); plans and prices; brand colours and logo; light, dark or
both.

## Process
The `website-builder` skill applies: message first (headline, proof, call to
action), section plan, then one section at a time with the site check after
each, its quality checklist, and a final design-director pass fixing the
top five issues. The live demo (`.lyra/kit/reference/index.html` in an
Appling project) is the reference for every effect above. The demo's
company, customers, quote and numbers are fictional — never ship them.
