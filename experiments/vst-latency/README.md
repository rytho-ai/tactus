# Real VST3 latency verification

## Finding and correction

The previous automation loop used `reset=True` on its first block. Pedalboard treats
that as a complete call and flushes buffered output at the end of that block. Later
`reset=False` blocks therefore did not form an uninterrupted stream. Tactus also
read latency before initialization and shifted output manually. LSP's latency
report changes during initial setup: a cold test's impulses appeared 482 samples
late; a partially warmed test was 222 samples late. See [before.json](before.json).

`fx.process_automated` now:

1. Applies `update(0)` and negotiates external-plugin latency with silent preparation
   calls, requiring a stable report and limiting preparation to five calls.
2. Explicitly resets the chain once, then passes every production block with
   `reset=False`. Pedalboard owns startup-delay compensation.
3. Flushes missing output with silence after the requested audio/tail, without
   calling automation beyond the requested timeline or shifting compensated output.
4. Rejects reported latency changes during automation instead of returning silently
   misaligned audio. Keep lookahead and oversampling fixed during a call.

Native effects without a latency property skip preparation. Parameters survive reset;
no plugin binary was modified. This is an offline helper, not a real-time engine.

## Real plugin evidence

Unmodified **LSP Plugins 1.2.35**, Limiter Mono/Stereo, loaded through Pedalboard 0.9.25.
The limiter's gain boost and automatic regulation are disabled; low-level seeded
noise and impulses at the first and final samples should pass unchanged.

[report.json](report.json) verifies exact array equality and repeat calls for:

- 44.1 kHz mono and stereo; 48 kHz stereo.
- Single plugin and two plugins in series.
- 20 ms, 10 ms and 3 ms automation blocks, including blocks shorter than latency.
- Zero tail and an explicit 30 ms tail.

All four cases preserve every sample, output length and input array. Reported
latencies are recorded as observations; do not infer them solely from lookahead
milliseconds. No claim is made for every plugin, dynamic latency, or unreported delay.

Ordinary regressions in `tests/test_fx_latency.py` model host-compensated buffering
independently, including one-sample inputs, mono/stereo, latency longer than the
input, explicit tail, reuse, delayed initialization and unstable latency.

Verification: 137 focused FX, functional-run and export tests passed; Ruff passes.

## Reproduce

```bash
uv run pytest tests/test_fx.py tests/test_fx_latency.py
uv run experiments/vst-latency/probe.py /path/to/lsp-plugins.vst3 --out dogfood/vst-latency.json
```

The plugin is a test asset, not a Tactus dependency. Download from the
[official release](https://github.com/lsp-plugins/lsp-plugins/releases/tag/1.2.35),
extract its VST3 bundle and pass that path. Archive:
`lsp-plugins-1.2.35-Linux-x86_64.7z`, SHA256
`4ef3b2f63b29a522fdaf3a18f879c1c85c82f0bdd1e0b3c849a5f3c4b08d2550`.
The extracted binary hash is recorded in the report.

Upstream contracts and implementation:
[Pedalboard latency API](https://spotify.github.io/pedalboard/reference/pedalboard.html#pedalboard.VST3Plugin.reported_latency_samples),
[Pedalboard processing](https://github.com/spotify/pedalboard/blob/v0.9.25/pedalboard/process.h),
[LSP limiter manual](https://lsp-plug.in/?page=manuals&section=limiter_mono).
