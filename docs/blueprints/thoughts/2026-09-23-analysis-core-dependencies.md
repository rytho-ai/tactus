# Core analysis dependencies

> 2026-09-23 · Product decision by Paul. This supersedes the package-selection recommendations in the [necessity probe](2026-09-23-analysis-dependency-necessity-probe.md) and [advanced librosa probe](2026-09-23-librosa-advanced-analysis-probe.md), while retaining their measured results and limits.

## Decision

Include `pyloudnorm` and `librosa` in Tactus's default dependencies alongside NumPy, SciPy, and SoundFile. Agent-authored production code may use all five directly. Analysis remains an observation supplied to the author; the presence of an analysis library does not make an estimated tempo, onset, pitch, or chord authoritative musical intent.

This is a product choice about a ready-to-use Python music-production environment. The probes did not establish that either library is mathematically necessary: FFmpeg also measured LUFS in the tested cases, and a task-specific SciPy implementation handled the tested synthetic timing and harmonic examples. Their conclusions should not be rewritten as empirical proof of unique library necessity.

`pyloudnorm` provides integrated loudness measurement directly on in-memory arrays. `librosa` provides established higher-level analysis operations such as onset candidates, CQT chroma, and pYIN. Keep creative decisions in production source and use library outputs as evidence. Short audio may not yield integrated LUFS; free-time audio may still receive an estimated BPM; timing candidates may be offset from the authored event.

## Implementation boundary

Declare these packages explicitly in the base distribution and lock them with the rest of the runtime. Do not add a mandatory analysis schema or a new analysis API merely because the packages are installed. When a real production repeatedly needs a shared report or helper, design that interface from the observed workflow.
