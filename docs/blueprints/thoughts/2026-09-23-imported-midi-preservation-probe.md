# Imported MIDI preservation probe

> 2026-09-23 · This evidence feeds the pending Tactus MIDI authoring decision back to Paul; it is not API approval.

## Question and preregistered rule

For a code-authored transformation of an existing full-performance MIDI file, does Symusic help an Agent preserve untouched events more reliably than Mido? Two fresh `gpt-6-luna` (max) Agents received the same two-step task. A reliability advantage required better first-submission correctness or fewer repairs without a preservation regression. Equal correctness and repair burden means no demonstrated reliability advantage; source length is secondary.

## Method

The immutable input was the previous probe's verified 76-bar phonon-ballad piano MIDI: one track, 480 PPQ, 884 notes, 152 sustain controls, tempo 120, and note-off velocity 0. Both Agents wrote Python source that imports this MIDI and produces an edited file. Only the MIDI manipulation path differed: Mido versus Symusic, with task-local preservation code allowed but recorded.

Stage 1 added eight channel-0 CC11 events at the starts of bridge bars 52–59, with values 72 through 100 in steps of four. Stage 2 kept those controls and moved only the eight outro last-arpeggio note-offs 120 ticks earlier. The independent checker compared every decoded event field, track count, PPQ, and original relative event order after accounting for the specified changes. First submissions were saved before validation. Both Stage 2 files were rendered with the same VSCO Upright Piano SFZ.

## Results

| Arm | Stage 1 first submission | Stage 2 first submission | Musical-source repairs | Stage 2 audio |
| --- | --- | --- | --- | --- |
| Mido | Pass | Pass | 0 | Rendered |
| Symusic plus task-local raw-SMF preservation writer | Pass | Pass | 0 | Rendered |

All four final outputs also passed: no missing or extra decoded events, no unintended field changes, and unchanged original-event order. The two Stage 2 WAV files were byte-identical. The MIDI files themselves were not byte-identical because their encodings differed.

The Symusic Agent used `Score` to inspect/edit notes and controls, but did not use its exported MIDI as the final file. To retain original release velocity and other raw events, it wrote a task-local Standard MIDI File parser/serializer and carried only the intended edits into the original event stream. Its Stage 1 and Stage 2 source files totaled 407 lines, compared with 115 lines for the Mido arm. This is observed Agent effort, not a controlled library LOC benchmark; the Symusic Stage 2 file also imports the Stage 1 helper code. One Symusic validator bug was repaired, but neither musical source nor submitted MIDI needed repair.

## Verdict

The preregistered reliability comparison is a tie: both Agents passed both steps on their first submission. This is stronger evidence that Mido is sufficient for this existing-MIDI maintenance workload, not proof that Symusic is unreliable. The practical friction is that the Symusic Agent had to bypass its normal MIDI export to meet exact event preservation; in this run, its score API did not replace a lower-level MIDI event layer. Keep Mido as the default preservation/export path for now, while treating Symusic as optional for higher-level symbolic transformations if a later task demonstrates value.

This is one Agent per arm, one imported MIDI file, and two edits. It does not test arbitrary multi-track files, unusual meta/SysEx events, different plugins, or subjective musical quality. The SFZ instrument remains in disposable `/tmp`.
