# Chop-flip vertical slice

This is a redistributable, synthetic-source adaptation of Music Agent OS's
`lab/chop_flip.py::make_beat`. It preserves the workflow shape—four-bar source, mostly long-phrase
chops, a short turnaround, drums, a custom 808, and separate mix/stems—but not the private crate
audio, RubberBand warp, production effect chains, or human-approved sound. It is an engineering
fixture, not a claim of musical parity.

```bash
uv run tactus build examples/chop-flip/song.py
uv run tactus inspect examples/chop-flip/.tactus/build/arrangement.json
uv run tactus render examples/chop-flip/.tactus/build/arrangement.json \
  --out examples/chop-flip/.tactus/render
```

Edit `parts/bass.py` to change the bass sound while leaving `parts/chops.py` and `parts/drums.py`
untouched. Build into two separate output directories and compare them with `tactus diff`.
Generated files remain outside the source of truth.
