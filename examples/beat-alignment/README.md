# Beat alignment: a real-performance comparison

This work turns a variable-tempo recording into two 27-second, 160 BPM candidates:
fixed-ratio stretch and beat-marker warp, with identical authored percussion. It uses the
existing `pytimestretch.time_warp` through ordinary Python; no new Tactus runtime API is needed.

**Status:** rendered and measured; Paul reports a modest improvement in the A/B comparison.
Final grid/candidate acceptance remains open. See the
[listening feedback](../../docs/blueprints/thoughts/2026-09-28-beat-alignment-production.md#listening-feedback-and-remaining-decision).
The frozen beat map is provisional, not ground truth or a downbeat grid.

## Source and frozen decisions

- Brahms, Hungarian Dance No. 5, performed by US Army Strings; librosa's HQ `brahms` recording.
  The supplied metadata declares CC-PDM-1.0. See [provenance.json](provenance.json) for source
  URLs, the compressed-source hash, decoded-WAV ref and analysis ref.
- Decode to stereo PCM24 at 44.1 kHz without changing timing. Run `tactus analyze rhythm beats`
  once and freeze the report as material. Render never invokes a tracker.
- Select detected beat indices 11 through 83: 4.13315–31.63719 seconds in the recording,
  72 intervals / 27.50404 seconds. This excludes the unstable opening estimates and includes
  both acceleration and slowing. No markers were hand-shifted or inserted.
- Map these to 160 BPM (27 seconds). Both modes use Rubber Band high quality, unchanged pitch,
  music gain -6 dB, percussion gain -13 dB and 15 ms edge fades. The half-time groove is an
  authored overlay; its grouping does not assert the recording's bar positions.
- `song.py` pins the source and analysis refs as constants. `prepare.py` explicitly creates a
  new analysis artifact; rerunning it is a proposed revision, not a render dependency.

## Reproduce

Run inside this directory; its uv project resolves Tactus from the relative checkout `../..`.
The lock pins third-party sources; the Tactus source revision is recorded in the render receipt.
The baseline Tactus revision for this trial is `ccb3cc8`.

```bash
uv sync --locked
uv run python prepare.py
uv run tactus run song.py --out runs/final/source --params '{"mode":"source"}'
uv run tactus run song.py --out runs/final/fixed --params '{"mode":"fixed"}'
uv run tactus run song.py --out runs/final/warp --params '{"mode":"warp"}'
uv run python evaluate.py
python3 -m http.server 4186 --bind 127.0.0.1
```

`prepare.py` prints the pinned identities. They must match `SOURCE` and `BEAT_REPORT` in
`song.py`; different bytes require an explicit decision and source edit. Existing run
folders are protected by Tactus: keep them and use fresh output directories for a revision.
Recordings, renders and the venv are ignored; source, lock, provenance and measurements are
versioned. The material pool also preserves the exact decoded source and frozen analysis.

Open `http://localhost:4186/` through SSH/IDE forwarding. The Traditional Chinese page offers
source-with-clicks review and A/B switching at the same timeline position, plus clean music,
click and percussion-mix views. It links the actual Tactus WAV outputs, not re-encoded audio.
`index.html` is the page source; it reads manifests and evaluator plot data at runtime.

## Measured outcome

| Check | Fixed ratio | Beat-marker warp |
|---|---:|---:|
| Mean absolute audio-correspondence error relative to grid | 600.49 ms | 7.79 ms |
| 95th percentile error | 1569.73 ms | 17.66 ms |
| Maximum error | 1609.56 ms | 20.96 ms |
| Output frames | 1,190,700 | 1,190,700 |
| Music RMS | -27.81 dBFS | -27.70 dBFS |
| Reported clipped samples (all outputs) | 0 | 0 |
| Isolated marker-boundary sample-step flags | 0 | 0 |

The percussion WAV hashes match exactly. Source interval estimates range from 117.45 to
206.72 BPM. Complete definitions and numbers are in [measurements.json](measurements.json).

### Measurement limits

Temporal correspondence is measured from the actual saved source/music WAVs using 48-band
log-mel features plus positive spectral difference and DTW, with 10 ms analysis hops. The
algorithm receives audio features, **not** the intended marker coordinates. The source beat
positions are queried only after the full path is found. First/last two anchors are excluded.
The identity calibration is exact; the fixed-ratio output agrees with its known affine map
to 2.55 ms mean absolute error (8.89 ms maximum). This supports a large improvement in alignment
of the chosen source positions, not a claim that the estimated beats are musically correct.

Both modes process the whole phrase continuously; there are no per-beat cuts to crossfade.
Boundary statistics look for isolated sample differences near markers relative to nearby
signal derivatives. A zero flag count cannot certify no audible artifacts. There was no
available subjective listening instrument in this session: the page supports the required
human audition of beat interpretation, transient softness, flutter and phrase feel.

## What this demonstrates

For this production, existing Tactus + pyqmdsp + pytimestretch cover the workflow. The missing
step was composing a frozen marker map with the existing engine, not adding another warp
implementation. Human acceptance remains open, as does whether repeated works justify a
shared authoring helper. No candidate has been chosen or presented as a finished musical verdict.
