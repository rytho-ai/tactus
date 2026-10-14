---
name: interactive
description: Make a Tactus work that other code reads or changes — an interactive or game-like piece, a walkable or votable set, a web player, a live trial, or music whose bars, sections and levels drive pictures or a video. Use when a work must give out its time structure, take a player's decisions or a performance as input, render on request while it plays, declare and check where it can loop or switch, or be delivered as a browser bundle, subtitles or per-frame curves.
---

# Music with an interface

A fixed song gives out only sound. A work that a page, a game, a room or a picture uses has
an interface with three parts, all in musical time:

1. **Give out time:** the work says what happens when — bars, sections, marks, where it can
   loop and leave — computed by the same code that made the audio.
2. **Take decisions:** a choice, a route or a whole performance comes in as an explicit
   input, kept with the run, so every sound can be rendered again from it.
3. **Join:** the places where it loops or switches are declared by the work and measured
   before anyone hears them.

Tactus owns the music side of this interface. Picture, game rules, state transitions, the
player and its UI belong to the work's own code or a downstream tool. A music video usually
needs only part 1; an interactive piece needs all three. Make the piece with
[compose](../compose/SKILL.md) as any other work: `tactus init`, `tactus run`, receipts.

## Decide what stays open

Write a piece worth hearing first, then ask which decision deserves to stay open. Interaction
added to a finished piece as a trigger or a slider tends to feel forced; a choice that changes
what the music means (which way, which version, whether to return) carries weight. Let the
music decide *when* a choice takes effect — at its own bar lines, phrase ends or joins — and
let the listener decide *which*.

No form is prescribed here. Loops, rooms, maps, tapes, votes, branching songs, endless
variations are examples of what earlier works chose, not a menu. Invent the form the piece
needs; only the three parts above are shared.

## 1. Give out time: return a map

Have `render` return `"map"` beside its outputs: per output a `grid` (bar-start frames),
author-named `lanes` (spans or points: sections, lyrics, kicks, cues) and `segments` (regions a
player can loop, enter or leave, with `joins`: where it may leave and to what). Positions are
integer frames of that output. Build bars with `Clock.grid(first, last)`
(`from tactus.timing import Clock`; a 3/4 clock is `Clock(..., meter=3)`) or give your own
frame lists; a work without bars returns lanes only. Contract and example:
[The time map](../references/runtime.md#the-time-map-optional).

- Derive the map in the same code path as the audio, never as a second hand-written file.
  When a downstream page or check needs a bar length, a loop length or a cue, it reads the map,
  not a constant copied into JavaScript or a script.
- Render everything a player can reach in one run where you can: every clip as a named
  output, every join as a segment. One receipt then covers all of it.
- A segment names one output. Parallel stems that loop together share one segment on one of
  them; the work's own data names the rest.
- A map error fails the run only after rendering (`invalid_output`). For a long render, test
  the map first: `tactus.timemap.validate(map, outputs)` accepts frame counts in place of
  arrays, e.g. `{name: entry["frames"]}` from a previous run's manifest.
- Keep the source unchanged while a long render runs: an edit is recorded as
  `source_changed` and the run no longer cleanly matches a commit.
- `tactus prune` removes a run's original arrays and `render.json`; scripts that check a run
  later read the sample rate and lengths from `manifest.json` and `map.json`.
- Tactus validates structure and references only. It gives lane names no meaning and does
  not judge a join; rules that depend on state (an hour, what was played before) stay in the
  work's player.

## 2. Take decisions: parameters and performances

- A small choice is a keyword parameter of `render` (`--params`).
- A performance — a tape, a route, a list of moves or votes — is a JSON file:
  `tactus run song.py --out runs/t1 --param-file tape=tapes/t1.json`. The run keeps the exact
  bytes as `parameters/tape.json`, so that copy renders the same performance again. See
  [render parameters](../references/runtime.md#the-render-contract).
- Validate a performance at the start of `render` and raise `tactus.InvalidParameters` with
  a message for the player; it is reported as `invalid_parameters` (HTTP 400 under serve),
  separate from a crash.
- Keep state in the performance, not in a long-lived process: the next part is
  `render(performance so far, choice)`. History-dependent music (places that remember visits,
  a theme that returns) is then reproducible and testable.

## Choose how it renders

| The piece | Render | Deliver |
|---|---|---|
| Every reachable clip can be enumerated | everything ahead of time, in one run | `tactus export web` |
| The next part depends on history, or the states are too many | the next bars on request while the current ones play | `tactus serve` |
| Heavy processing, light live mixing | heavy parts offline; the player only levels, filters or crossfades rendered stems | `tactus export web` |

[`tactus serve`](../references/serve.md) keeps the work loaded and answers `POST /render`
with an ordinary receipted run per request (Island: 1.4 s per step against 3.9 s for a cold
`tactus run`). Budget a request against the music: it must finish before the bar that needs
it, so ask one step ahead. Real-time DSP inside the player and exporting Tactus DSP to plug-ins
are outside Tactus today.

## 3. Join: declare and check every path

Offline rendering lets you hear and measure every way the piece can go before anyone plays it.

- Declare each loop and switch point in the map's segments and joins.
- Measure both kinds: a loop's own wrap, and every exit into another segment joined as the
  player joins it. The switches are often where the click is (a clip ending on a held value
  into one starting at another); the measure skill's `switches` helper builds them.
- Measure them with the `join` analyses (`tactus analyze join --help`): the step and
  residual across each seam or loop wrap, levels through a crossfade, onset phase after a
  switch. Measure the same things at ordinary bar lines (`reference_s`) and compare: one
  sample's prediction error varies 10–20 dB across real music, and the largest step inside a
  loop is usually a drum hit, not a standard for a wrap. They report numbers; what counts as a
  click or a late entry is your decision. The analyses do not read the map;
  [Check joins and loop wraps](../measure/SKILL.md#check-joins-and-loop-wraps) shows how to turn
  a run's map into positions.
- Check what analysis cannot: that every state reaches an end (or deliberately does not),
  that two renders agree sample for sample up to a switch point, that a delivered file plays
  the same length in the browser as in the run.
- Sample-exact agreement needs a reproducible render. Free-running plug-ins (OB-Xf's
  oscillators in 《門》) differ on every render; check by rendering the same
  source twice, and keep such parts as [saved takes](../references/runtime.md#saved-takes) when
  a switch or a later re-render must match.
- Listen to the joins that matter; a passing check is a fact, not a musical verdict.

## Deliver

- **A page:** `tactus export web RUN --codec flac|wav|aac|opus [--bitrate 224k] --out DIR`
  writes browser audio and `bundle.json` (lengths in frames and seconds, levels, waveform
  peaks, the map in frames and seconds, the run's hashes, the length each file decodes to).
  The page loads `bundle.json` and schedules from its map; titles, credits and art stay in the
  work's own files beside it. File paths in the bundle are relative to its directory, so the
  page prefixes them with where the bundle is served. `--out` must be a new directory: export
  each run once, to a directory named after the run, and point the page at it. Lossless keeps
  loops sample-exact (FLAC is PCM24; `--bit-depth 16` rounds it, often under half the size); AAC's reported length equals
  what browsers play. The waveform outline is about 1 MB with 30 outputs at the default
  `--peaks 2000`; `--peaks 0` leaves it out when the page draws no waveform. See
  [Delivering with the map](../references/project-commands.md#delivering-with-the-map-web-srt-curves).
- **Pictures or a video:** `tactus export srt` turns a spans lane into subtitles;
  `tactus export curves --fps 30` gives levels, map events, bars and sections per video frame.
  Visual smoothing and style stay with the picture code.
- **On request:** run `tactus serve` beside the page; each request is a run directory that
  `export`, `analyze` and `prune` read like any other. Keep `--retain` bounded; published PCM
  grows with every request.

Test the delivery where it is meant to work: open the page in a browser, walk or play every
kind of path at least once, capture the audio if you cannot listen, and say what remains
unheard. Report friction you meet as a finding. Prune candidate runs once results are
recorded.
