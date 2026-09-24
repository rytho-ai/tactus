# Real-source chop-flip study

An eight-bar, 90 BPM production exercising the functional `render()` entry:
four real source bars → pitch-preserving warp → long-phrase rearrangement →
authored drums/bass → filtering/delay/mix → a bass-level candidate.
The source is the existing local Music Agent OS `CErZvbcaOeE` case near 54.1 seconds.
This is a bounded adaptation of its musical approach, not a claim of sonic parity.

## Local inputs and dependencies

Source and beat-grid SHA256 identities are pinned in `materials.py`. The default
paths use the existing ignored `dogfood/2026-09-16-real-chop-flip/project/assets/`.
To use another location for those exact bytes, set `TACTUS_CHOP_SOURCE` and
`TACTUS_CHOP_GRID`. A different source requires an intentional identity/source edit.
No source recording, sidecar or rendered audio is committed with this example.

The Tactus environment supplies NumPy, SciPy and SoundFile. This production also
uses `pyrubberband` 0.4.0 and the system `rubberband` executable (tested with 3.3.0),
already present in the local probe environment. They are project requirements,
not newly declared Tactus core dependencies. Use `uv run --inexact` to preserve
the locally installed experimental package. On a new machine, provision these
dependencies and the pinned inputs before running this example.

## Produce and audition

```bash
uv run --locked --inexact tactus run examples/real-chop-flip/song.py \
  --out /tmp/chop-flip-base
uv run --locked --inexact tactus run examples/real-chop-flip/song.py \
  --out /tmp/chop-flip-less-bass --params '{"bass_gain_db": -9.0}'
```

The base uses `bass_gain_db=-5.0`. The candidate reduces only bass by 4 dB;
sample/drum outputs should remain byte-identical. No output is automatically
accepted. Listen before changing the source default; after an accepted change,
render without overrides and compare with the selected candidate.

`chops.py` owns selection order, final-bar fragments, filters and stereo delay.
`rhythm.py` owns seeded synthetic drums, kick positions and bass notes; note choices
were informed by an existing source transcription and still need listening judgment.
`song.py` owns gains, mix and tail. These are ordinary production functions, not
Tactus recipes or imposed mix/stem roles. The one-second output tail is authored.

## Evidence boundary

This example tests real production and revision through the CLI. A valid WAV,
matching hashes or LUFS measurements do not establish musical quality. The local
listening session and its captures live under
`dogfood/2026-09-24-functional-production/`. Source identities are explicit here;
the runtime does not automatically trace the external files or Rubber Band version.
