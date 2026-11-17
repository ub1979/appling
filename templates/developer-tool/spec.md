# Template: Developer Tool

A site for [PROJECT — one line on what the API, SDK, CLI or open-source tool
does and for which developers], where code is the main picture: a working
install command, a terminal that runs a real session and code samples next to
their output.

## Stack
Vite + TypeScript, GSAP + ScrollTrigger. Static output. Syntax highlighting
from hand-written token spans (or Shiki at build time) — no runtime
highlighter.

## Mood
Editor-like and precise. Dark by default, taken from a real IDE theme (the
demo uses a Tokyo Night-style ink blue, never pure black), with a light theme
toggle. One bright token colour as the accent (teal-green in the demo); syntax
colours as tokens that pass contrast in both themes. JetBrains Mono for code,
labels and numbers; a warm text sans (Hanken Grotesk in the demo) for prose.
No purple gradients, no glowing robots.

## Sections
1. **Nav** — wordmark, Docs / Features / Quick start / Community, a GitHub
   button and the theme toggle.
2. **Hero** — one-line value ("Background jobs as code."), a sub-line naming
   who it is for, the install command with a Copy button, two calls to
   action, and a terminal that types a short real session on load.
3. **One call** — a code sample in tabs (JavaScript / Python / cURL) beside
   the output it produces.
4. **Features** — three rows, each: name + two lines, a short code block,
   and its result (next runs, counts, a status pill).
5. **Quick start** — three numbered, copy-pastable commands.
6. **Ecosystem** — a ruled grid of language, framework and platform
   wordmarks (text only, real integrations only).
7. **Community** — four counters (stars, contributors, releases, SDKs) with
   a note while the numbers are samples.
8. **Docs** — three entry cards: Guides, API reference, Examples.
9. **Final call to action** — one line and the first command again; footer.

## Effects to check
Theme is right on first paint and the toggle remembers it · every Copy button
copies and says "Copied" (screen readers hear it) · tabs switch by click and
by arrow keys / Home / End · the terminal types its session, and shows it in
full with reduced motion · counters count once · code blocks scroll inside
their own box on phones; the page never scrolls sideways.

## Motion rules
Easing power3/expo, never linear; the terminal is the one hero idea; cards
rise in as they enter; nothing moves while code is being read. Transitions
0.8–1.2 s.

## Quality
Both themes pass `palette.py check` (text, muted, accent, dividers) and every
syntax colour is ≥ 4.5:1 on the code background. Keyboard: tabs, copy buttons
and links reachable with a visible focus ring. 60 fps (transform/opacity
only), respects prefers-reduced-motion, fully responsive down to 390 px,
Lighthouse performance ≥ 85. Every code sample must actually run against the
owner's real API.

## Ask the owner (one question at a time)
The real install command(s) and package names · two or three real code
samples and the output they print · which languages and tabs to show · the
repository link and licence · real community numbers (or hide the section) ·
the docs, API reference and examples links · brand colour, or pick from an
IDE theme they like.

## Process
Follow the `website-builder` skill (Developer site blueprint, copy and proof
rules, quality checklist). Section plan first; build one section at a time
and run the site check after each; finish with a taste pass and a senior
design critique, fixing the top five issues. The live demo
(`.lyra/kit/reference/index.html` in an Appling project) is the reference for
every effect above.
