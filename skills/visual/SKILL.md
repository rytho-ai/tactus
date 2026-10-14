---
name: visual
description: Make pictures that follow a Tactus work's time, in any form — a video, a page that plays, live visuals, a lyric video, an installation. Use when a picture must meet the music: taking bars, sections, levels, events and lyrics from a run, rendering frames or a playing page, measuring sync, and the people, places and licences the picture involves.
---

# Pictures that follow the music

Any form of picture is welcome; this skill is about joining it to the music and checking the join. The
form, the look and the tools are yours. Tactus does not draw pictures; it gives out the music's time. The
[interactive](../interactive/SKILL.md) skill covers the music side of a work that other code reads or
changes.

## Picture from the music's time

Make every frame a function of the song's time — `frame(t)` — and take that time from the run, never from
numbers copied into picture code.

- **Where the time comes from.** A run's `map.json` holds bars, author-named lanes (sections, lyrics, hits)
  and segments ([The time map](../references/runtime.md#the-time-map-optional)).
  `tactus export curves RUN --fps 30` gives values per video frame; `tactus export srt RUN --output mix
  --lane lyrics` gives subtitles; `tactus export web` gives a page the same map in frames and seconds
  ([Delivering with the map](../references/project-commands.md#delivering-with-the-map-web-srt-curves)).
  If the music is a finished recording rather than a Tactus run, make a small Tactus work that loads it as a
  material and returns a map (beats fitted with `timing.fit_tempo`, sections as a lane), so the timing still
  lives in one place. Do not restate a tempo, bar length or section time in the picture code; read it.
- **Reading curves.json.** Arrays have one value per video frame (`frames` of them, at each frame's
  `frame_time`, here its start):

  ```json
  {"fps": 30.0, "frames": 4526, "frame_time": "start",
   "measures": {"mix.rms_dbfs": {"values": [-17.4, -16.9, ...], "window_s": 0.0333}},
   "grid": {"output": "mix", "bar": [1, 1, ...], "bar_phase": [0.0, 0.0167, ...], "beat_phase": [...]},
   "spans": {"output": "mix", "sections": {"index": [0, 0, ...], "labels": ["intro", ...]}}}
  ```

  A measure is an object; its numbers are in `values` (silence is `null`). Point lanes given with
  `--events` are counted per frame, not described; read their fields from `map.json`.
- **When an event you need is not in the map.** A picture often needs finer events than the map carries
  (every strike, a layer's level). Ask whether the work can add them: if you own it, return them from
  `render` as a lane, or render the layer as its own output so `curves` measures it. Otherwise derive them
  from the map (grid positions, rows, beats per bar), then check the derived times against the audio and
  say in your notes that they are derived.
- **Deterministic frames.** Any seek must give the same pixels: seeded randomness, motion integrated ahead
  from `t` (a walk's distance, a camera path), no wall clock. Then a single frame can be rendered, compared
  and fixed alone.
- **Choose the look from the music and its subject.** Research what the piece is about before ideas: its
  words, its people, its places, its structure, what it sounds like. Make two or three concept frames that
  differ in kind and choose (ask the person you work for when one is available), then build. Try the
  hardest frames first. Keep one plan — moments or shots with their music time and why — that feeds the
  build, the review and any page about it. No look is a default: not a famous painter's homage, not 3D, not
  a rainy neon night; if earlier works used a look, consider differing deliberately. The music's own
  structure can be the picture.
- **Measure sync, do not only watch it.** Pick the visual events that should meet music events (a cut on a
  bar line, a flash on a hit, a word on its syllable) and check their frame times against the map or the
  onsets numerically, in the encoded file as well as in your renderer. Nearest-onset matching misleads on
  sounds with long tails (bells, pads): compare the average lag over all events with a shifted control.
  Extract stills at the moments that matter. A video-watching model sampling at a few frames per second
  cannot judge cuts against beats; use it for what it can see, and a person for the rest.
- **People and places.** Do not draw real people's faces or private lives (children above all); real crimes,
  families and shops stay out or are invented and labelled. Check licences of images, footage, fonts and
  maps (credit OpenStreetMap). Draft lyrics are labelled as drafts until checked. Research notes stay
  internal; what goes on a public page is decided by the person you work for.
- **Say what was not checked.** End with what nobody has watched in real time or heard.

## Rendering a video

Render offline, frame by frame, never by screen-recording real time.

- **Two pipelines.** Drawing on the CPU (Skia, Cairo, Pillow) and piping raw frames into ffmpeg is simple,
  fast for 2D work, parallel across worker processes and needs no GPU or browser. A browser program
  (Canvas, WebGL, three.js) renders `frame(t)` in a headless browser that posts each frame to a small local
  endpoint, or uses a frame-accurate capture tool. Either way mux with the run's audio unchanged.
- **Check the file.** Frame count against the duration; decoded audio identical to the run (hash it). MP4
  cannot carry the lossless PCM: keep a master in MKV or MOV with the run's PCM and share an MP4 with AAC.
  Some video tools limit or resample audio; remux the original. Extract frames from the encoded file, not
  only from your renderer: a whole film once came out blue because the drawing library's pixels were BGRA
  and ffmpeg was told RGB. Keep entry points for one frame at a given time, a contact sheet of chosen times,
  and the frame without titles. Load fonts before the first frame.
- **Browser and GPU traps.**
  - Log the WebGL renderer string; software GL is about 4 frames/s. Shadow maps can come out black in
    headless Vulkan; bake or fake shadows (a soft plane under each object).
  - One render at a time on a GPU: two renders, or a leftover browser, slow to ~1 frame/s and corrupt the
    file. Take a lock (`flock -n .render.lock`) around every render.
  - A JavaScript module with a syntax error stops a page silently and the render waits forever: check
    modules (`node --check`) after each edit and forward console errors to the capture log.
- **Disk.** Frame folders and masters are large (a grainy 3-minute 1080p master can pass 1 GB). Delete frames
  after muxing; deliver a two-pass encode tuned to the picture (`-tune grain` keeps halftone dots).
- **Figures** read stiff when cut from single shapes; joint them (shoulder, elbow, wrist, fingers).
- **Projects.** Scripts must not depend on one session's scratch paths. A picture project created inside
  another uv project (for example under a Tactus checkout) joins that workspace silently: use
  `uv init --no-workspace`, or `tactus init` for a Tactus work.
- **Review and revise.** Review the cut against the plan (a video-watching model can report per shot; a
  person judges taste), fix, and show before/after stills of each change.

## Pictures in a page that plays

A page plays the music live while it draws; its clock is the audio clock.

- **Time from the bundle.** Load `bundle.json` (from `tactus export web`, or a `tactus serve` request with
  `deliver`) and take bar lines, loop lengths and cues from `map_seconds`; nothing musical is restated in the
  page. Drive the picture from `audioContext.currentTime` against those times; an analyser's level may shape
  brightness, but timing comes from the map.
- **Scheduling.** Start sounds on the next bar line with a small lead: `next = t0 + ceil((now - t0)/bar)*bar`,
  scheduled a little ahead. Take a listener's choice a beat before the bar it changes. When the next part is
  rendered on request, budget render time against the time left before it must sound.
- **Checks.** Compare each decoded buffer's length with the bundle's frames. Add a capture hook that records
  what the page actually plays and compare it with the run rendered whole. Serve page and API from one
  origin (`tactus serve --static DIR`).
- **Gestures and layout.** Resume the audio context inside a real user gesture; headless synthetic clicks may
  not count, so test with real key or pointer presses. Test at a desktop size and a phone size: no horizontal
  scroll, and no invisible element catching clicks over a button.
- **Loading.** Prefer AAC or 16-bit FLAC; load what is needed first and the rest in the background.
