# Phonon-ballad MIDI maintenance probe

> 2026-09-23 · This evidence feeds the pending Tactus MIDI authoring decision back to Paul; it does not approve an API.

## Question and preregistered rule

Does Symusic make an Agent more reliable than Python-owned production logic plus Mido when maintaining MIDI in a real, multi-section piece? Two independent `gpt-6-luna` (max) Agents received the same source and two sequential edits. A positive signal required fewer correctness errors or repairs without preservation regressions. Equal first-pass musical correctness and repair burden means no demonstrated reliability benefit; code length alone is not a win.

## Method

Both arms copied the current `examples/phonon-ballad/song.py` into separate disposable scratch areas. The only assigned representation difference was MIDI export: Mido versus Symusic. Stage 1 changed sustain-pedal release/repress timing only at the seven interior boundaries of `chorus_1`. Stage 2 transposed only the 19 `chorus_2` melody notes up 12 semitones while preserving Stage 1. Both exported with `--drums none` to lock the shared random-number stream.

An independent checker regenerated the source's 76-bar, 884-note piano performance and compared 480-PPQ MIDI note events, tempo, program, and 152 sustain controls. Both Stage 2 outputs were rendered through the same VSCO `UprightPiano.sfz` with `sfizz_render`. Product source was not changed.

## Data

| Arm | Stage 1 | Stage 2 | Repairs to musical logic | Real SFZ render |
| --- | --- | --- | --- | --- |
| Python + Mido | Pass: 0 missing/extra events | Pass: 0 missing/extra events | 0 | Pass |
| Symusic | Pass: 0 missing/extra events | Pass: 0 missing/extra events | 0 | Pass |

Both Stage 2 WAVs were non-silent, 153.408 seconds at 32 kHz stereo, and differed by at most one 16-bit PCM step. This is a render smoke test, not a listening-quality judgment. Scratch-path import adjustments and a switch from the source's default one-shot drums to `--drums none` were test-harness/configuration corrections, not musical-logic repairs.

A stricter raw-MIDI audit found one difference the preregistered musical-event checker normalized away: the original/Mido path wrote all 884 note-off velocities as 0; the Symusic `Note` export wrote each note-off velocity equal to its note-on velocity. The Symusic file also placed program change before CC64 at tick 0, versus the opposite order in the raw writer. The latter is equivalent for this piece; the former could matter for instruments that respond to release velocity. We did not establish whether Symusic offers another export path that preserves it.

## Verdict

The preregistered reliability rule did not select a winner: both Agents completed both edits without musical-logic repair. This strengthens the case that Python-owned production logic plus Mido is sufficient for this workload; it does not prove equivalence across all MIDI work. Symusic was usable, but this trial did not show an Agent reliability gain. Exact raw-event fidelity is a separate compatibility question because the tested Symusic `Note` path changed release velocity.

This is one Agent per arm and one two-step production task, not a statistical reliability estimate. It did not test imported MIDI, arbitrary channels, microtiming, expressive release velocity, or subjective listening quality. The Upright Piano SFZ currently resides in disposable `/tmp`, not in `rytho-library`.
