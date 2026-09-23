# The Space Between Replies

An original instrumental pop-ballad study. The reference is Fish Leong's "Acceptance"
(`https://www.youtube.com/watch?v=NV3M1LHSr_s`), used only to study tempo, form, and emotional
arc. No audio, melody, lyrics, or sampled material from the reference enters the render.

The arrangement is ordinary Python: harmony, melody, performance, timbre selection, section timing,
mixing, and export are defined by `song.py`. The fixed seed makes regeneration deterministic. The
rendered WAVs and receipt live in `dist/phonon-ballad/` and are intentionally not committed.

From the `tactus-code` repository root:

```sh
uv run python examples/phonon-ballad/song.py --palette sampled
uv run python examples/phonon-ballad/song.py --palette synthetic --out dist/phonon-ballad/synthetic
uv run python examples/phonon-ballad/song.py --palette sfz \
  --sfz-piano /path/to/UprightPiano.sfz --out dist/phonon-ballad/sfz
uv run python examples/phonon-ballad/song.py --palette sfz \
  --sfz-piano /path/to/UprightPiano.sfz --drums none --out dist/phonon-ballad/sfz-no-drums
uv run python examples/phonon-ballad/song.py --palette sfz \
  --sfz-piano /path/to/UprightPiano.sfz --drums loop --out dist/phonon-ballad/sfz-loop
```

The `sampled` palette uses the host-installed FluidR3 General MIDI soundfont (MIT) through the
small `soundfont.py` bridge, plus four one-shot drum samples already in the local Rytho Library.
Those sample paths and SHA-256 hashes are pinned in `song.py`; the sources are never edited and
their bytes are not committed here. Set `RYTHO_LIBRARY_ROOT` and `FLUID_SOUNDFONT` if those
dependencies live elsewhere. The `synthetic` palette recreates the earlier all-NumPy timbres so
the same score can be A/B tested without changing its musical decisions.

The `sfz` palette is the preferred listening path. It serializes the complete piano performance
(note timing, velocity, and sustain pedal) into one Standard MIDI file, then runs the supplied
multi-sampled SFZ piano through `sfizz_render`. It replaces the synthetic lead, guitar, strings,
and bass with piano-register orchestration, while retaining the pinned Rytho one-shot drums.
Install `sfizz_render` separately and keep the chosen SFZ library outside this repository; the
receipt records the exact local paths used for a render.

Set `--drums none` to render the exact same piano performance without any percussion. `--drums loop`
uses a pinned 120 BPM stereo lo-fi loop; its source path and SHA-256 are recorded in the receipt.
This makes one-shot and loop choices audible as arrangement decisions rather than hidden mix changes.

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
