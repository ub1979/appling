# Template: Landing Page

A one-page site for [OFFER — one line on what the visitor gets and who it is
for], built around a single call to action that repeats down the page.

## Stack
Vite + TypeScript, GSAP + ScrollTrigger. Static output, no server; the form
posts to the owner's mailing service (or shows a clear "not connected yet").

## Mood
Bold, warm and poster-like: a cream page, deep ink type, one hot tomato
accent used in colour blocks, never as a gradient. A heavy, slightly
condensed display face (e.g. Archivo at 800–900, condensed width) for huge
headlines, a plain text face (e.g. Public Sans) for reading. Big type,
hard edges, generous space — high energy, still calm to read.

## Sections
1. **Nav** — logo left, the one button right. No other links.
2. **Hero** — the offer as a headline, one sentence on who it is for, an
   email field with the button, a line on what happens next, and a key
   picture drawn in CSS/SVG (shapes in the palette, no stock photo).
3. **The problem** — two or three sentences in the visitor's words, set
   large on an ink block.
4. **What you get** — 3–5 numbered benefits, each a heading and two lines.
5. **Proof** — one real, attributed testimonial and one real result number
   with its source.
6. **How it works** — three steps from sign-up to result.
7. **Questions** — 4–6 objections answered with `<details>`.
8. **Final call to action** — the promise again and the same form and button.
9. **Footer** — brand, privacy and contact links.
On phones a slim bar with the button slides up once the hero has scrolled
away, and hides again at the final call to action.

## Effects to check
Hero words rise in a stagger on load and the key picture assembles · the
problem block slides in · benefit numbers and cards rise as they enter ·
the result number counts up once · the phone CTA bar appears after the hero
and hides near the final form · the form shows an inline error for a bad
email and a success message for a good one · reduced motion shows
everything at once, still.

## Motion rules
Easing power3/expo, never linear; one hero idea per section; at most two
ambient animations on screen; transitions 0.6–1.2 s. No countdowns, no fake
scarcity, no pop-ups.

## Quality
60 fps (animate only transform/opacity), respect prefers-reduced-motion with
a static version, fully responsive (390 px with no sideways scroll), visible
focus rings, labelled form fields with inline errors, every colour pair
passing `palette.py check`, meta description and share tags, Lighthouse
performance ≥ 85.

## Ask the owner (one question at a time)
The offer and who it is for · the single action (sign up, join the
waitlist, book a call) and its exact button label · where sign-ups go (their
mailing service or form address) · real testimonials and results they can
back up (otherwise placeholders) · any guarantee or real deadline they offer
· logo and brand colours.

## Process
The `website-builder` skill applies (landing page blueprint, copy and proof
rules, quality checklist). Write the copy before the layout; build one
section at a time and check it with the site check; finish with a taste
pass and fix the five weakest things. The live demo
(`.lyra/kit/reference/index.html` in an Appling project) is the reference
for every effect above.
