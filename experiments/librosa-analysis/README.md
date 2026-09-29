# Librosa analysis integration

Historical initial-integration findings. Current runtime uses owned implementations;
re-running the comparison below requires the optional `librosa` extra.

The five optional analyses are available through Python and `tactus analyze`:
`rhythm.onset_strength`, `rhythm.onsets`, `spectral.mel`, `spectral.chroma`, and
`spectral.mfcc`. No dependency was added. This checkout uses librosa 1.0.0.

## Verification

- `uv run pytest -q`: **530 passed, 1 skipped** (the existing opt-in installation test).
- `uv run ruff check`: passed.
- All five real `uv run tactus analyze` commands succeeded on a recorded drum loop or piano
  loop; the three matrix attachments loaded as finite NumPy arrays. Local receipts live in
  `dogfood/2026-09-29-librosa-analysis/cli/` (ignored).
- Numerical tests compare explicit direct-librosa calculations at 22050, 44100 and 48000 Hz,
  including nondefault parameters. Independent tone, impulse and DCT checks cover axes and
  timing. Silence, short signals, cancellation, malformed inputs, CLI help, array hashes,
  provenance, saved-run inputs and existing custom commands are covered by pytest.

## Onset comparison

[`report.json`](report.json) contains timestamps, per-file precision/recall/F1, matched timing
errors, input hashes, implementation hashes and versions. Defaults were fixed before this
comparison; the nine loops were not used to tune the new detector.

Macro F1 across nine difficult loops made from recorded one-shots:

| Method | ±2 ms | ±10 ms | ±25 ms | ±50 ms |
| --- | ---: | ---: | ---: | ---: |
| Librosa default, backtracked | 0.144 | 0.533 | 0.700 | 0.790 |
| Previously tuned librosa, backtracked | 0.267 | 0.757 | 0.840 | 0.854 |
| Tactus Mel SuperFlux defaults | 0.086 | 0.525 | 0.818 | 0.818 |
| Tactus defaults with backtracking | 0.293 | 0.685 | 0.808 | 0.818 |

**This is not a general accuracy improvement over the previously tuned configuration.**
The new API supplies candidate events and an editable frontend, not precise cut boundaries.
The older 2 ms validation failure remains valid. Backtracking selects a preceding strength
minimum and changes the meaning of the returned marker; it does not recover ground truth.

The new frontend follows the [librosa SuperFlux example](https://librosa.org/doc/0.11.0/auto_examples/plot_superflux.html):
1024-sample FFT, approximately 5 ms hop, 138 Mel bands, lag 2, maximum filter width 3,
27.5 Hz to min(16 kHz, Nyquist). It explicitly supplies the FFT size for timing compensation.
This Mel implementation is not claimed numerically identical to original log-frequency
SuperFlux. Peak picking uses delta 0.07 and a 30 ms minimum interval. All are documented in
help, with frontend and detection parameters exposed.

### What these labels mean

The corpus marks each sample's first crossing of 1% of its own peak **before mixing and
effects**. Near-simultaneous notes remain separate references. These are mechanical labels,
not perceptual onset annotations. The previous tuned baseline used loop 04 during tuning;
it is not an untouched baseline. Matching here is one-to-one maximum-cardinality ordered
matching, rerun for every method; the old report used nearest greedy matching, so headline
numbers should not be compared without rerunning. Timing errors concern matched events only.

Two additional synthesized five-note cases (3 ms and 80 ms attacks) detected all five events
5 ms after their authored envelope starts, with no extra detections. Both score 1.0 at
10/25/50 ms and 0 at 2 ms. The fixtures taper their tails to avoid unlabelled truncation
clicks. These simple signals do not establish soft-attack accuracy on real instruments.

Recorded piano and pad loops produced finite Mel/chroma/MFCC arrays. They have no onset
labels, so they are smoke tests only. The pad produces many candidate events; users must not
interpret every spectral change as a new note. Very early notes, quiet ghost notes and close
flams can also be missed or merged. Neither this comparison nor the synthetic fixtures
establish performance on a general music benchmark.

## Reproduce

Use the repository's locked environment:

```sh
uv run --extra librosa python experiments/librosa-analysis/check.py \
  --corpus dogfood/2026-09-29-librosa-analysis/corpus \
  --out experiments/librosa-analysis/report.json
```

Add `--audio FILE...` before `--out` for unannotated smoke tests. The checked-in report includes
the piano and pad files named in its `unannotated_smoke` section. The local corpus preserves
the previous nine loops and `truth_manifest.json`; audio is not committed.

[`build_corpus.py`](build_corpus.py) preserves the original recipe. To reconstruct using the
same recorded one-shots (not distributed here):

```sh
TACTUS_ONSET_DRUMS=/path/to/crate/drums \
TACTUS_ONSET_CORPUS=/path/to/rebuilt-corpus \
  uv run python experiments/librosa-analysis/build_corpus.py
```

The script names every required asset. Exact regeneration depends on those asset bytes and
the processing library versions; compare regenerated hashes with the report before treating
it as the same corpus. This integration was evaluated against the saved original WAVs.

## Feature contracts

Python matrix results remain NumPy arrays. CLI callers pass `--out DIR` to receive JSON field
descriptors plus hashed `arrays.npz` attachments; no flattened matrix JSON was introduced.
Spectral features sum channels, matching the existing spectral category. Rhythm averages
channels. Opposite-polarity channels can cancel in either case.

New features use centered, zero-padded Hann frames. Mel is linear power with Slaney weighting,
not dBFS. Chroma has C-first rows and per-frame maximum normalization. MFCC uses DCT-II of
log-Mel power; silence has a nonzero zeroth coefficient. The function docstrings and generated
CLI help specify these definitions, shapes, timestamps and parameters.
