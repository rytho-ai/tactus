# The Space Between Replies

An original instrumental pop-ballad study. The reference is Fish Leong's "Acceptance"
(`https://www.youtube.com/watch?v=NV3M1LHSr_s`), used only to study tempo, form, and emotional
arc. No audio, melody, lyrics, or sampled material from the reference enters the render.

The arrangement is ordinary Python: harmony, melody, performance, timbre selection, section timing
and mixing are defined by `song.py`'s `render(*, palette, drums, sfz_piano)`. A fixed seed controls
the authored randomness; external instruments can still vary between runs. `tactus run` publishes
the outputs and a receipt; nothing is written
by this example itself.

## Import the pinned inputs

The `sampled` palette and the `one-shots`/`loop` drum modes read pinned bytes through
`tactus.material`. Import them once into the shared pool (paths below assume the local Rytho
Library and the host FluidR3 soundfont; adjust if yours live elsewhere):

```sh
uv run tactus material add \
  /usr/share/sounds/sf2/FluidR3_GM.sf2 \
  "<rytho-library>/assets/audio/gamut-library/sample-library/audio/splice/sounds/packs/Tape/TAPE/SAMPLES/KICKS/CDS_TAPE_KICK_ONE_SHOT_TRIXON.wav" \
  "<rytho-library>/assets/audio/gamut-library/sample-library/audio/splice/sounds/packs/Jazzfeezy X Sikky Beats - Verified Bounce/Jazzfeezy_-_Verified_Bounce/one_shots/drums/rims/JSB_VB_rim_soft.wav" \
  "<rytho-library>/assets/audio/gamut-library/opensource-sounds/drums/boochi44/drum-samples/03-soulful-vintage/hi-hats/ch-lofi.wav" \
  "<rytho-library>/assets/audio/gamut-library/opensource-sounds/drums/boochi44/drum-samples/03-soulful-vintage/open-hats/oh00-lofi.wav" \
  "<rytho-library>/assets/audio/gamut-library/sample-library/audio/splice/sounds/packs/Lofi By Nature/CPA_Lofi_By_Nature/Drum_&_Perc_Loops/Drum_Loops/LBN_120_drum_loop_bottled_rolla.wav"
```

The printed `sha256:…` refs must match the `SOUNDFONT`/`DRUM_MATERIALS`/`LOFI_DRUM_LOOP`
constants in `song.py`. No environment variables or path overrides are read.

## Produce

From the `tactus` repository root:

```sh
uv run tactus run examples/phonon-ballad/song.py --out /tmp/phonon-sampled \
  --params '{"palette": "sampled", "drums": "one-shots"}'
uv run tactus run examples/phonon-ballad/song.py --out /tmp/phonon-synthetic \
  --params '{"palette": "synthetic"}'
uv run tactus run examples/phonon-ballad/song.py --out /tmp/phonon-sfz \
  --params '{"palette": "sfz", "sfz_piano": "/path/to/UprightPiano.sfz"}'
uv run tactus run examples/phonon-ballad/song.py --out /tmp/phonon-sfz-loop \
  --params '{"palette": "sfz", "sfz_piano": "/path/to/UprightPiano.sfz", "drums": "loop"}'
```

The `sampled` palette uses the host-installed FluidR3 General MIDI soundfont (MIT) through the
small `soundfont.py` bridge, plus four one-shot drum samples already in the local Rytho Library.
`libfluidsynth` is declared via `tactus.tool` using the path Linux actually mapped for it
(Linux-only resolution; see the comment in `soundfont.py`). The `synthetic` palette recreates the
earlier all-NumPy timbres so the same score can be A/B tested without changing its musical
decisions.

The `sfz` palette is the preferred listening path. It serializes the complete piano performance
(note timing, velocity, and sustain pedal) into one Standard MIDI file, then runs it through
`sfizz_render` (declared via `tactus.tool` at point of use) against the SFZ piano at `sfz_piano`.
It replaces the synthetic lead, guitar, strings, and bass with piano-register orchestration, while
retaining the pinned Rytho one-shot drums. This example accepts `sfz_piano`
as an explicit, unpinned path parameter — install `sfizz_render` separately and keep the chosen
SFZ library outside this repository; the receipt records the exact local path used for a render.

Set `"drums": "none"` to render the exact same piano performance without any percussion.
`"drums": "loop"` uses the pinned 120 BPM stereo lo-fi loop instead of one-shots. This makes
one-shot and loop choices audible as arrangement decisions rather than hidden mix changes.

This study uses a 120 BPM pulse with a half-time ballad feel. It moves from a sparse piano and
pluck-led verse to a higher, sustained lead melody and wider string/drum arrangement in the
choruses. The harmony is in D major/B minor; it does not transcribe the reference progression.

## Analysis notes

Phonon estimated the reference at 120 BPM and F major, with a long intro, several restrained
verse spans, and later recurring choruses. These are model estimates, not ground truth. The
production choices here preserve the medium pulse and gradual widening but use different chord
cycles and a new lead melody. No palette uses the reference recording.

The rendered mix was also checked with Phonon: it returned a 120 BPM beat grid and found the
main chord changes. Its global-key detector returned A major even though the declared harmony
is D major/B minor. The source score and timed chord sequence are authoritative for this study;
one global key label is a useful diagnostic, not a replacement for them.
