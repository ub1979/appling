# Review and export

## Contents
- Stills before motion
- Contact sheet and playback
- Independent critique
- Writing fixes
- Export checks

## Stills before motion

Render three frames first (`npx hyperframes@latest snapshot`, or render
single frames at chosen times): the opening, the product result, the
closing card. Check each:

- Is the main text readable at phone size?
- Is the product result visible and the focus of the frame?
- Is anything cropped, overlapping or sitting in a platform safe zone?
- Is there room for the logo and call to action?

Fix layout and copy here; motion comes after.

## Contact sheet and playback

After each scene and after the full render:

```
mkdir -p frames
ffmpeg -v error -i out/film.mp4 -vf "fps=2,scale=480:-1,tile=6x5" -frames:v 1 frames/sheet.png
```

Open `frames/sheet.png`, then watch the MP4 at normal speed, twice: once
for the message, once for timing. Look at each scene boundary closely
(render the second either side of it) — the outgoing and incoming states
should hand over cleanly.

## Independent critique

The builder does not grade its own work. Start a fresh helper with only
the brief, the three stills, the contact sheet and the MP4, and ask for at
most five fixes, each tied to a time or frame. Accept, adapt or reject
each, then apply.

## Writing fixes

Every correction has four parts:

```
Where: scene 2, frames 180–210 (6.0–7.0 s)
Problem: the headline leaves before it can be read
Change: hold the headline until frame 240, start the card exit after it
Keep: card position, colours and entrance timing
```

Order of work: missing information and unreadable text → timing and
attention → visual polish. Keep frame references explicit when scenes are
nested (local frame 30 in a scene starting at frame 120 is global frame 150).

## Export checks

```
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate -show_entries format=duration -of default=nw=1 out/film.mp4
ffmpeg -hide_banner -i out/film.mp4 -af loudnorm=print_format=summary -f null - 2>&1 | grep -E "Input (Integrated|True Peak)"
```

- Size, frame rate and duration match the brief for every format.
- With audio: integrated loudness about −14 LUFS, true peak ≤ −1 dBTP.
- H.264 MP4, `yuv420p`, `+faststart` for the web; one file per aspect ratio.
- Cover image exported from an approved frame.
- The final file was watched end to end before delivery.
