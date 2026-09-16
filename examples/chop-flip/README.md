# Chop-flip vertical slice

This is a redistributable, synthetic-source adaptation of Music Agent OS's
`lab/chop_flip.py::make_beat`. It preserves the workflow shape—four-bar source, mostly long-phrase
chops, a short turnaround, drums, a custom 808, and separate mix/stems—but not the private crate
audio, RubberBand warp, production effect chains, or human-approved sound. It is an engineering
fixture, not a claim of musical parity.

```bash
uv run tactus-code build examples/chop-flip/song.py
uv run tactus-code inspect examples/chop-flip/.tactus-code/build/arrangement.json
uv run tactus-code render examples/chop-flip/.tactus-code/build/arrangement.json \
  --out examples/chop-flip/.tactus-code/render
```

Edit `parts/bass.py` to change the bass sound while leaving `parts/chops.py` and `parts/drums.py`
untouched. Build into two separate output directories and compare them with `tactus-code diff`.
Generated files remain outside the source of truth.
