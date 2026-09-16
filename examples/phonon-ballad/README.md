# The Space Between Replies

An original instrumental pop-ballad study. The reference is Fish Leong's "Acceptance"
(`https://www.youtube.com/watch?v=NV3M1LHSr_s`), used only to study tempo, form, and emotional
arc. No audio, melody, lyrics, or sampled material from the reference enters the render.

The arrangement is ordinary Python: harmony, melody, performance, synthesis, section timing,
mixing, and export are all in `song.py`. The fixed seed makes regeneration deterministic. The
rendered WAVs and receipt live in `dist/phonon-ballad/` and are intentionally not committed.

From the `tactus-code` repository root:

```sh
uv run python examples/phonon-ballad/song.py
```

This study uses a 120 BPM pulse with a half-time ballad feel. It moves from a sparse piano and
pluck-led verse to a higher, sustained lead melody and wider string/drum arrangement in the
choruses. The harmony is in D major/B minor; it does not transcribe the reference progression.

## Analysis notes

Phonon estimated the reference at 120 BPM and F major, with a long intro, several restrained
verse spans, and later recurring choruses. These are model estimates, not ground truth. The
production choices here preserve the medium pulse and gradual widening but use different chord
cycles, a new lead melody, and entirely generated instrument sounds.

The rendered mix was also checked with Phonon: it returned a 120 BPM beat grid and found the
main chord changes. Its global-key detector returned A major even though the declared harmony
is D major/B minor. The source score and timed chord sequence are authoritative for this study;
one global key label is a useful diagnostic, not a replacement for them.
