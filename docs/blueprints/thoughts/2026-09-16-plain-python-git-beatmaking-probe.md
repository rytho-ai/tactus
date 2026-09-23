# Plain Python + Git beatmaking probe

> 2026-09-16 · This evidence feeds the pending Tactus Code decision back to Paul. This is one Python-only behavior probe, not a framework A/B.

## Question and pre-registered rule

Can ordinary Python + Git complete a real-source eight-bar beat, a targeted 808 revision, and a clean-clone rebuild? Completion with only setup/provenance work means engineering friction, not a demonstrated musical-expression limit. A blocked musical operation would count as creative friction; missing inputs would remain inconclusive.

## Method

A disposable Git repo used Music Agent OS's local `CErZvbcaOeE_inst.wav` and beat-grid `.npy`, NumPy-written drums and 808, Pedalboard warp/effects, and a Python build script. It rendered a 90 BPM, eight-bar mix plus sample/drums/bass stems. The original Splice drum loops were unavailable, so this is not a sonic reproduction of `chop_flip.py`.

## Observations

- The project used 211 lines of Python; 71 were in the build/manifest/receipt entry point. Git tracked source, `pyproject.toml`, `uv.lock`, and asset hashes, but not licensed audio or generated WAVs.
- `uv sync` initially selected Python 3.13; importing Pedalboard exited with code 132. Pinning Python 3.12 made the same dependency import and the song build work.
- Changing `BASS_DRIVE` from 2.4 to 3.2 was a one-line Git diff. Only bass and mix WAV hashes changed; sample and drums remained byte-identical.
- A clean clone failed with a precise missing-asset error. After manually supplying the two hash-checked assets, all four WAVs matched the source repo byte for byte.
- Both versions render 21.333-second audio. Musical quality has not been judged by a human listener.

## Verdict

For this bounded task, Python + Git was sufficient; no tested musical operation required a special runtime. The observed friction was environment compatibility, external asset handoff, and a 71-line project entry point that combines musical orchestration with build/provenance work. This does not establish how a more complex session scales, or whether Tactus Code removes enough repeated glue to justify itself.
