# Reusable offline DSP example

From the repository root:

```sh
uv run tactus run examples/dsp-effects/song.py --out runs/dsp-effects
```

The four-second, deterministic synthesized source requires no sample downloads.
The run exports dry, ducked, wet-only echo, filtered, driven and mixed audio.
The echo and mix include a 0.75-second tail; the other outputs retain source length.
These are independent comparisons, with an explicitly authored mix at the end.

`duck` returns a gain curve reusable on another same-length signal. `delay` moves
its fractional read position continuously, so changing its time intentionally
changes pitch. `lowpass` follows a per-frame cutoff sweep. `saturate` applies tanh
with default 8x oversampling and a per-frame dry/wet mix; it does not normalize gain.
Each function processes a complete clip and resets on every call. Existing
`dsp.biquad` remains the API for explicit fixed-parameter filter block state.

Change the declared `drive_db` and `delay_seconds` render parameters to produce
candidates. Full function contracts are in the root README's **Owned DSP** section
and the functions' Python docstrings.
