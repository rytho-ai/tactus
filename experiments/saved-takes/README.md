# Saved takes: full-song transfer

This trial uses the official installed OB-Xf and sfizz binaries to generate two versions
of the private 46-bar production. It saves the first pads/bass performances through the
public take CLI, exports them and imports them into a separate pool. A second pad take
exercises explicit selection and rollback.

Four fresh containers have no networking, native instrument bundles, SFZ library, generation
run or stage cache mounted. They receive only the playback source, selected take blobs and
seven ordinary source samples. The existing clean-handoff image supplies Python and packages;
its editable Tactus source is overlaid with this implementation.

## Result

- Baseline playback: all six WAVs byte-identical to the original generation run.
- Bass gain -3 to -6 dB: the other four stems remain byte-identical.
- Alternative pad: matches the second generation's pad, differs from the first.
- Restoring the first ref: all six WAVs exactly restored.
- All playback receipts: `tools: []`, `reuse: false`, `stages: []`.
- No patched native binaries used; installed-original hashes are recorded in `evidence.json`.

The baseline and alternative takes are technical trial candidates, not listener-approved
replacements for the earlier accepted song. This verifies one Linux CPU/kernel and package
environment; it does not prove arbitrary downstream DSP behaves identically across platforms.
Unit/integration tests additionally delete the original source, run and pool before replaying
an exported/imported take, exercise malformed/missing/corrupt bundles and preserve float64
precision and over-full-scale values.

Repository gates: 416 pytest tests passed, 1 existing opt-in test skipped; Ruff passed.

## Reproduce locally

The source samples remain private and ignored. Requires the inputs and container image from
`experiments/clean-production-handoff`, Docker and original installed instruments:

```bash
uv run python experiments/saved-takes/probe.py \
  --source dogfood/2026-09-28-clean-production-handoff/transfer/work/song.py \
  --pool dogfood/2026-09-28-clean-production-handoff/transfer/pool \
  --plugin /home/worzpro/.vst3/OB-Xf.vst3 \
  --sfizz /home/worzpro/.local/bin/sfizz_render \
  --out dogfood/2026-09-29-saved-takes-verified
```

Choose a new `--out` path for another run. The script uses a real copied VST3 bundle;
`tool()` rejects a symlinked bundle root. A first harness attempt exposed that existing
constraint before generation; the completed trial uses a copy without changing the plugin.
JSON reports and logs remain in the ignored trial folder. Compact evidence is tracked here.
