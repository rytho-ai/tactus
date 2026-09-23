# Mido-native versus Python-event MIDI authoring

> 2026-09-23 · This evidence feeds the pending Tactus MIDI authoring decision back to Paul.
> Both conditions used Mido 1.3.3 for file output; only the editable performance model
> differed. This is a bounded same-agent comparison, not a public API commitment.

## Question and pre-registered rule

Would keeping the whole performance as Mido `MidiTrack`/`Message` objects make Agent edits
simpler than using ordinary task-local Python records and calling Mido only at export?
Both had to create the same baseline and apply the same revision without losing any
unrelated event. The preregistered ergonomic signal favored Python records for this task
if the Mido-native revision function took at least 1.5 times as many nonblank,
noncomment lines while both were correct. A shorter or equal Mido-native revision would
keep it a reasonable primary editing candidate. Neither outcome alone would establish
cross-agent reliability or require a Tactus schema.

## Controlled method

The baseline had two tracks, 480 ticks/quarter, a 4/4 signature, a tempo change at tick
1920 from 120 to 90 BPM, eight overlapping notes of 720 ticks with distinct velocities,
CC64 sustain, and pitch bend. The revision moved the latter four notes and their
note-offs by 240 ticks, added 10 to their velocities, moved one pedal-off from tick
3720 to 3480, and changed the second tempo to 100 BPM.

- **Mido-native:** the editable value was a delta-timed `MidiFile` with `MidiTrack`
  messages. The revision converted messages to absolute ticks, matched note-on/off pairs,
  applied changes, sorted events, and rebuilt delta times.
- **Python events:** the editable value used task-local immutable `Note(start, duration,
  pitch, velocity)`, `Control`, and `Score` records. The revision changed records;
  `export()` then converted them to Mido messages and delta times.

Both used NumPy to establish the same pitch/velocity sequence and Mido for final `.mid`
output. A separate semantic checker parsed each file with Mido, compared every event to
the fixed musical brief, checked note pairing/duration and nonnegative deltas, then
compared file bytes. Whole-module and `revise()` lines were counted separately.

## Results

| Check | Mido-native | Python events |
| --- | ---: | ---: |
| Baseline | Pass first run | Pass first run |
| Revision, first run | Fail strict event order | Pass |
| Revision, after one correction | Pass | Pass |
| Whole implementation lines | 72 | 80 |
| `revise()` lines | 27 | 16 |

The first Mido-native revision moved a note-on to tick 2160, where an unchanged note-off
already existed. Its stable sort emitted the note-on first; the expected deterministic
order was note-off first. The two notes had different pitches, so this was a strict
event-order failure, **not demonstrated audible damage**. Adding an explicit same-tick
note-off-before-note-on rule fixed the fixture without changing the task or verdict
threshold. After that correction, both baseline outputs were byte-identical (163 bytes)
and both revised outputs were byte-identical (161 bytes).

Mido-native kept the total local implementation eight lines shorter, largely because
the Python-event route declared three task-local record types and an export adapter.
For the requested edit, Mido-native used `27 / 16 = 1.69` times the lines: it had to
recover absolute positions, pair note messages, and serialize the new order.

## Verdict and limits

**Both authoring forms are viable in this bounded task.** The pre-registered revision
threshold favors ordinary Python note/control records when the Agent is making musical
edits. Mido-native remains a reasonable compact choice for small or message-oriented
tasks; the total source-size result does not support banning it. The result supports
Mido as an I/O boundary, while leaving task-local Python representation open to the
production. It does **not** justify a mandatory Tactus `Note`/`Track` authoring schema.

The comparison has one author, one fixture, one revision, and no independent Agent
sessions. Code-line count is a mechanical proxy, not measured comprehension or long-term
maintenance. The checker uses Mido; no external DAW import, instrument render, audible
quality, varying time signatures, channels, direct `.mid` source editing, or arbitrary
third-party MIDI files were tested. The next deciding experiment, if the authoring form
remains contested, should give fresh Agents the same creative revision task with either
surface and measure first-pass correctness and edit locality.

Disposable preregistration, first-run/final results, scripts, and MIDI files are under
`/tmp/tactus-midi-authoring-probe.jc1Fzy/`; they are not durable repo fixtures. Product
code was unchanged, and there were no paid model calls.
