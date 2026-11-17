# Video playbook

## Contents
- Story shapes
- Technique menu
- Timing defaults
- Captions and text
- AI pictures for video
- Audio

## Story shapes

**Launch clip (10–20 s, one feature).** Opening line (what is new) → the
starting state of the real screen → cursor on the one action → the result
appears and holds → logo + call to action. One feature, one action, one
result.

**App promo (15–30 s).** Hook: the problem in one line (≤ 2 s) → three
screens of the app at work → the payoff moment (a notification, a finished
task) → store badges + call to action.

**Social reel (9:16, 15–45 s).** Hook in the first second (a bold claim, a
surprising number, a before/after) → 3–5 fast beats, each one caption
line → payoff → call to action. Designed to work muted.

**Explainer (30–60 s).** The problem → how it works in three steps (a
diagram that builds, one step per beat) → what the viewer gets → call to
action. One idea per scene; diagrams instead of paragraphs.

**Announcement (6–15 s).** The news as a headline → one supporting detail
(date, number, picture) → brand close. Works as a loop.

**Data story (15–40 s).** The question → the chart builds to the answer →
the takeaway as a headline → source line → close.

## Technique menu

Pick the technique for the job, not the other way round.

| Job | Techniques |
|---|---|
| Reveal a product | Mask or clip-path wipe, scale-in from 0.92 with a soft shadow landing, device frame turning to face camera |
| Make a headline land | Kinetic type: per-word rise, weight shift, tracking-in, slam with a short settle |
| Guide through a UI | Cursor path with ease-in-out, click ripple, highlight box or spotlight dim on the rest, zoom to the area of action |
| Show numbers | Counters that settle on the final value, bars that grow, a line that draws, the key value in the accent colour |
| Explain a system | Nodes appearing in order, animated paths/arrows carrying a dot from step to step, a diagram that builds |
| Add depth | Parallax layers, slow camera push (scale 1.00 → 1.03 over 3 s), 3D card flip, perspective tilt |
| Move between scenes | Match cut on a shared object, push, mask wipe, zoom through; one family per video |

## Timing defaults

Starting values for a 30 fps film; tune in playback.

| Event | Seconds | Frames |
|---|---|---|
| Object entrance | 0.5–0.8 | 15–24 |
| Offset between headline and its label | 0.1 | 3 |
| Reading hold, short line | 1.5–2.0 | 45–60 |
| Cursor move to a target | 0.6–0.9 | 18–27 |
| Click → visible response | 0.15–0.3 | 5–9 |
| Result hold | ≥ 2.0 | ≥ 60 |
| Scene transition | 0.4–0.7 | 12–21 |
| Closing card | ≥ 2.0 | ≥ 60 |

Count the reading hold from the frame where the text is fully legible, not
from when its entrance starts. Read every line aloud at normal speed; if
the hold ends first, extend it.

## Captions and text

- One type system for the whole video: a display face for headlines, a
  clean sans for captions.
- Captions ≥ 48 px at 1080 wide, high contrast (solid or blurred pill
  behind), ≤ 2 lines, word-highlight style for social.
- Safe areas on 9:16: keep text and key action out of the top ~14% and the
  bottom ~20% (platform UI) and ~6% from each side.
- Check every interface label is still readable at phone size.

## AI pictures for video

Use `.lyra/kit/imagine` (owner's consent, their ChatGPT plan) for
backgrounds, textures, mood stills and illustrated scenes. Write prompts
as a shot brief: subject, lens, light, palette hexes, negative space for
type, "no text, no logos, no watermark". Make the key still first, then
`--ref` it for the others so light and palette match. Animate stills in
code (slow push, parallax split into layers, mask reveals). Moving AI
footage only when a video generation provider is configured — keep clips
short (4–5 s), camera moves small, and reject clips that warp.

Never present AI pictures as the real product, a real place or a real
customer.

## Audio

- Music the owner owns or licenses; or none. Keep it under the effects.
- One soft whoosh per real transition; UI sounds only on real actions,
  placed on the event frame.
- Mix to about −14 LUFS integrated, true peak ≤ −1 dBTP; check on
  headphones and a phone speaker.
- Deliver a version that works muted (captions carry the message).
