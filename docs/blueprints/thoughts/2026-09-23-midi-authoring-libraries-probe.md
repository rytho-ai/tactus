# MIDI authoring libraries: bounded revision probe

> 2026-09-23 · This evidence feeds the pending Tactus MIDI authoring decision back to Paul. It is not an API decision.

## Question and preregistered rule

Can a note-level library make a bounded MIDI edit without losing the surrounding performance? Before trials, the gate was: preserve all specified note, tempo, meter, CC64, and pitch-bend events before and after revision; only passing candidates could be compared for editing burden. A candidate would be promising as a *better* authoring surface only if it passed and reduced revision burden or removed a material class of editing errors. This same-agent exercise cannot establish cross-Agent reliability. The preregistration is in the disposable directory noted below.

## Method

The fixed 480-PPQ input had 4/4, a tempo change, eight overlapping 720-tick notes, four CC64 events, and two pitch bends. The requested edit shifted the last four notes by 240 ticks, raised their velocities by 10, moved one pedal-off, and changed the second tempo. A separate Mido reader compared normalized output events to the brief. MusPy, pretty_midi, and Symusic each loaded the same input and wrote MIDI; the [earlier task-local Python-events/Mido probe](2026-09-23-mido-native-vs-python-events-probe.md) is contextual baseline. Product code was not changed.

## Results

| Candidate | Baseline | Revision, first run | Revision, final | Edit function |
| --- | --- | --- | --- | ---: |
| MusPy 0.5.0 | Not run: `music21` install stalled | Not run | Not run | 15 lines drafted |
| pretty_midi 0.2.11.post0 | Pass | Fail: authored shift was 480 rather than 240 ticks | Pass after correction | 26 lines |
| Symusic 0.6.0 | Pass | Pass | Pass | 16 lines |

pretty_midi preserved all target events on round-trip. Its edit used seconds, then Mido patched the tempo event because the chosen public authoring path did not provide a tempo-change setter. The first shift error was in our code, not evidence of a pretty_midi bug. Symusic exposed the relevant notes, CCs, bends, pedals, and tick-based tempo directly and passed without correction. Its baseline and revised MIDI files were 152 and 151 bytes; pretty_midi's were 154 bytes each. The checker normalized note-on-with-zero-velocity as note-off and did not require byte identity.

MusPy has no runtime score here: `muspy` itself installed, but its `music21` dependency download did not complete after repeated attempts. Its [published Mido input code](https://muspy.readthedocs.io/en/latest/_modules/muspy/inputs/midi.html) stores CC as track annotations but does not map `pitchwheel`; its [Mido output code](https://muspy.readthedocs.io/en/latest/_modules/muspy/outputs/midi.html) emits program changes and notes without emitting those track annotations. This source-level evidence predicts that the specified CC/bend round-trip would fail, but is not a measured runtime failure. MusPy's [MIDI I/O documentation](https://muspy.readthedocs.io/en/latest/io/midi.html) confirms that Mido is the default backend.

## Verdict and limits

**Symusic is a credible candidate for a fresh-Agent comparison, not a demonstrated replacement for task-local Python events.** Its 16-line edit function is not directly comparable with the earlier 16-line `revise()`: the libraries loaded an existing MIDI file, whereas the earlier Python-events code constructed the baseline. pretty_midi remains viable for seconds-oriented editing but required more conversion work in this beat/tick-oriented task. MusPy remains unverified at runtime and has a source-backed fidelity risk for this task.

The checker covered only the specified musical events, not arbitrary MIDI metadata, channel/program identity, unsupported message types, or byte identity. One author wrote all variants, and there were no independent Agent sessions or paid LLM trials. The next deciding test should give fresh Agents the same source and revision brief in the passing representations, measuring first-pass correctness, edit locality, and whether NumPy-driven pattern changes remain natural.

Disposable preregistration, probe script, input and MIDI outputs are under `/tmp/tactus-midi-libraries.vIbaCI/`; they are not durable repository fixtures. No product code was changed.
