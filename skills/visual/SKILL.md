---
name: visual
description: Make pictures that follow a Tactus work's time, in any form — a video, a page that plays, live visuals, a lyric video, an installation. Use when a picture must meet the music: taking bars, sections, levels, events and lyrics from a run, rendering frames or a playing page, measuring sync, choosing a tool (suggestions: Blender, three.js, a GLSL shader, anime.js, HyperFrames), and the people, places and licences the picture involves.
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
- **Browser and GPU traps.** Most failures here are silent: the frame is black, white, fogged or wrong and
  nothing reports an error. Look at frames extracted from the encoded file every time.
  - Headless Chrome with the GPU: `--use-angle=vulkan --enable-features=Vulkan --ignore-gpu-blocklist
    --disable-gpu-compositing`. Without the last flag the WebGL context was lost after a while (whole
    frames black or white); it can still drop once early and recover, so check each read-back frame (an
    alpha that is not 255 means a blank frame: wait and render it again). Log the WebGL renderer string;
    software GL is about 4 frames/s. Shadow maps can come out black; bake or fake shadows.
  - Drive time yourself: stop the library's own render loop and render once per captured frame from the
    song time you inject. Never rely on its clock, animation system or particle system.
  - Read frames back over a WebSocket or as a Blob: posting a typed array with `fetch` cost 0.5 s per
    1080p frame. Blobs fill Chrome's memory unless garbage is collected every few frames.
  - One render at a time on a GPU: two renders, or a leftover browser, slow to ~1 frame/s and corrupt the
    file. Take a lock (`flock -n .render.lock`) around every render.
  - A JavaScript module with a syntax error or a failed import stops a page silently and the render waits
    forever: check modules (`node --check`), forward console and page errors to the capture log, and give
    the capture a timeout.
  - Keep Chrome's temporary folder on a short path (a long one breaks its socket), and pin the port.
- **Audio and telemetry.** Do not let a video tool mux the sound: several resample, limit or re-encode it.
  Mux the run's original audio with ffmpeg yourself. Turn telemetry off in every tool that has it, and keep
  its home and cache folders inside the project.
- **Disk.** Frame folders and masters are large (a grainy 3-minute 1080p master can pass 1 GB). Delete frames
  after muxing; deliver a two-pass encode tuned to the picture (`-tune grain` keeps halftone dots).
- **Figures** read stiff when cut from single shapes; joint them (shoulder, elbow, wrist, fingers).
- **Projects.** Scripts must not depend on one session's scratch paths. A picture project created inside
  another uv project (for example under a Tactus checkout) joins that workspace silently: use
  `uv init --no-workspace`, or `tactus init` for a Tactus work.
- **Review and revise.** Review the cut against the plan (a video-watching model can report per shot; a
  person judges taste), fix, and show before/after stills of each change. Drop a direction that stays ugly
  after a few rounds: in one trial a realistic bell chamber kept looking like a game set, and the film
  became beautiful only after the agent switched to a calm lake.

## Suggested tools

Suggestions, not requirements: any tool that can render `frame(t)` offline works, and plain CPU drawing
(Skia, Cairo, Pillow piped to ffmpeg) needs no tool at all. Eighteen tools rendered the same 2:31 track in
trials, every one with strikes landing within a frame; these five lanes held the films the listener liked,
with tools that were practical for an agent. What made a film beautiful was the idea and the willingness to
drop a weak one, more than the tool.

A picture stacks layers: drawing (shader, 3D scene or 2D shapes), motion (when and how things move) and
output (video frames or a playing page). Some tools cover one layer, some all three.

| What you want | Main tool | Same lane | Speed seen (1080p30, RTX 4090) |
|---|---|---|---|
| Light, water, fog, reflections, depth of field: physically rendered beauty | Blender, scripted | — | ~0.7 s/frame (EEVEE) |
| A 3D space, materials and a moving camera; or 3D you may later make playable in a page | three.js | React Three Fiber when you think in React; A-Frame when you would rather write the scene as HTML tags; TSL for materials and shaders | 6–30 frames/s |
| A continuous space computed per pixel: sky, fog, water, terrain, light | a fragment shader (GLSL) run with moderngl, no browser | — | ~37 frames/s |
| 2D motion design: shapes, paths, easing, keyframes | anime.js on SVG or Canvas, captured by HyperFrames or a headless browser | — | ~9 frames/s (6 browsers) |
| Type, lyrics, letters, layout | HyperFrames | — | faster than real time |

- **Blender (bpy, headless).** Unpack an official release inside the project and run `blender -b -P
  scene.py`. Build and light the scene in Python, set every animated value from `t` (keyframes computed from
  the map, or a frame-change handler). Use EEVEE unless you need Cycles (several seconds per frame).
  - Fits: beauty from light and matter, with the music driving a few parameters (a flash, a ripple, a sky).
  - Does not fit: text and layout, pages that play live, objects that need careful modelling you have no
    time for.
  - Traps: a handler is not saved in the .blend; load it with `-P` on every render or the scene stays still
    without an error. Blender 5 changed the animation API (F-curves through a channelbag). Compare decoded
    pixels, not file hashes. Keep its cache folders inside the project.
- **three.js (and React Three Fiber, A-Frame, TSL).** three.js for direct control; React Three Fiber when you
  think in components (less scene code, the same three.js underneath); A-Frame when the scene's objects,
  lights and camera read well as HTML tags, with the music in a few components; TSL (Three Shading Language) to write materials
  and shaders as JavaScript, compiled for WebGPU or WebGL. Render on demand (`frameloop="never"` and
  `advance`, or set everything from `t`), capture with the browser recipe above.
  - Fits: 3D space, metal, glass, sand, light shafts, camera moves; the same scene can later run in an
    interactive page.
  - Does not fit: a quick beautiful result without writing shaders and lighting; flat 2D.
  - Traps: postprocessing in React Three Fiber merges adjacent effects into one pass, so depth of field or
    bloom can read the image before your own effect (wrap it in an `EffectGroup`); `ShaderPass` can drop a
    render target texture with only a warning; GLSL `smoothstep` with reversed edges is undefined. TSL
    coerces mismatched types silently and a JavaScript `if` inside a TSL function is not a shader branch
    (use `If`): keep a reference frame known to be right and compare. WebGPU read-back rows run top-down
    (WebGL bottom-up); the first frame of a new browser can be wrong, so render twice before capturing.
    Props built from primitives read as plastic: spend effort on materials and light. A-Frame runs its own
    loop: after `renderstart` call `renderer.setAnimationLoop(null)`, then for each frame call
    `sceneEl.tick(t * 1000, dt)` and render; compute every component from `time` (no `animation` component,
    no `Math.random`). Its camera entity is a group looking down −z, so `lookAt` on the group points it
    backwards; once custom shaders and geometry dominate, plain three.js has fewer traps.
- **A fragment shader (GLSL) with moderngl.** One shader computes each pixel from its position, `t` and
  uniforms (recent strikes, row, section, level, passed from the map); a standalone EGL context renders on
  the GPU without a browser, and frames go to ffmpeg. Several passes are fine; feedback between frames is not
  (it breaks `frame(t)`).
  - Fits: one continuous space — sky, sea of cloud, fog, water, terrain, light over the whole piece — with
    the music moving a few parameters and a slow arc of light.
  - Does not fit: text, characters, many recognisable objects, or anything that must accumulate the past.
  - Traps: compile errors arrive with line numbers (`#line` per file), but wrong results are silent:
    render stills after each change and add debug views (draw one term as colour). Check helper libraries'
    licences (much of lygia is not open source).
- **anime.js.** Timelines built from the map and never played: seek the timeline to `t` for each captured
  frame. It draws nothing itself; pair it with SVG or Canvas, and capture with HyperFrames or the browser
  recipe above. MIT licence.
  - Fits: 2D vector motion design with fine easing and keyframes, motion paths, hundreds to thousands of
    events.
  - Does not fit: masses of particles, full-screen filters, 3D or physical light.
  - Traps: adding the same property of the same target to a timeline more than once gives wrong values when
    seeking backwards, silently; give each event its own element or one tween per property. CSS-scaled
    layers can rasterise differently depending on earlier seeks; avoid CSS zoom for camera moves. Heavy SVG
    blur is CPU-bound; run several browsers in parallel.
- **HyperFrames.** HTML, CSS and JavaScript compositions captured frame by frame (it bundles GSAP).
  - Fits: title cards, type and lyrics; or wrapping a `draw(t)` you already wrote in Canvas/WebGL/SVG (for
    example with anime.js) to capture it fast and repeatably.
  - Does not fit: a single full-screen shader with nothing else (it only opens the browser for you).
  - Traps: it limits and resamples audio (remux the original); telemetry is on by default and it sends
    snapshots to a model when a key is set (turn both off, keep `HOME` inside the project); `-o` is relative
    to the project; some preview and check commands have hung, so keep your own screenshot script; it picks
    its own port.

**Writing a brief for another agent or yourself.** Named examples become templates: when a brief quoted a
favourite film with lamps, two of three new films drew lamps. Describe the qualities wanted (depth,
atmosphere, a structure that grows) and name the motifs already used enough, rather than the films liked.

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
