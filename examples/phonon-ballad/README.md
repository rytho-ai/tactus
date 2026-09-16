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
```

The `sampled` palette uses the host-installed FluidR3 General MIDI soundfont (MIT) through the
small `soundfont.py` bridge, plus four one-shot drum samples already in the local Rytho Library.
Those sample paths and SHA-256 hashes are pinned in `song.py`; the sources are never edited and
their bytes are not committed here. Set `RYTHO_LIBRARY_ROOT` and `FLUID_SOUNDFONT` if those
dependencies live elsewhere. The `synthetic` palette recreates the earlier all-NumPy timbres so
the same score can be A/B tested without changing its musical decisions.

This study uses a 120 BPM pulse with a half-time ballad feel. It moves from a sparse piano and
pluck-led verse to a higher, sustained lead melody and wider string/drum arrangement in the
choruses. The harmony is in D major/B minor; it does not transcribe the reference progression.

## Analysis notes

Phonon estimated the reference at 120 BPM and F major, with a long intro, several restrained
verse spans, and later recurring choruses. These are model estimates, not ground truth. The
production choices here preserve the medium pulse and gradual widening but use different chord
cycles and a new lead melody. Neither palette uses the reference recording.

The rendered mix was also checked with Phonon: it returned a 120 BPM beat grid and found the
main chord changes. Its global-key detector returned A major even though the declared harmony
is D major/B minor. The source score and timed chord sequence are authoritative for this study;
one global key label is a useful diagnostic, not a replacement for them.
