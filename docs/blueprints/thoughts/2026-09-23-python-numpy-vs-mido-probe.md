# Python + NumPy versus Mido for performed MIDI I/O

> 2026-09-23 · This evidence feeds the pending Tactus MIDI boundary decision back to Paul.
> Python + NumPy remained the shared creative language; only MIDI-file read/write mechanics
> varied. The result does not decide the full MIDI authoring model.

## Question and pre-registered rule

Does Mido add a capability required to create and maintain a bounded MIDI performance, or
does it mainly remove repeated file-format code? Both conditions had to preserve the same
events through write → read → targeted edit → write → read. If both passed, Mido was not
necessary for this capability. If Mido passed with at most half the MIDI I/O code lines,
it earned a strong recommendation as an **I/O helper**, not a mandatory authoring schema.
The rule and fixture were written before either condition ran.

## Controlled method

One shared Python + NumPy score supplied two tracks at 480 ticks per quarter note: a 4/4
signature, a 120 → 90 BPM tempo change, overlapping notes with varied velocities, CC64
sustain, and pitch bend. One shared edit transposed only notes beginning at or after the
tempo change by two semitones, including their corresponding note-offs; all other events
had to remain unchanged.

- **A — Python + NumPy only:** standard-library byte/`struct` code wrote and read the
  fixture's MIDI 1.0 subset, including variable-length delta times and track chunks.
- **B — Mido:** the same score and edit used Mido 1.3.3 for MIDI messages, tracks, and files.

Each condition read its own file back. A common semantic oracle read the resulting files
with Mido and checked exact event tuples, two tracks, resolution, and nonnegative deltas.
Byte comparison checked whether the two conditions serialized this fixture identically.
The I/O count excludes shared score/edit code and counts nonblank, noncomment lines in
each condition's implementation file.

## Results

| Check | Python + NumPy only | Python + NumPy + Mido |
| --- | ---: | ---: |
| Initial file matches all expected events | Pass | Pass |
| Edited file changes only selected notes | Pass | Pass |
| Two tracks, 480 ticks/beat, nonnegative deltas | Pass | Pass |
| MIDI I/O implementation lines | 111 | 48 |

Both conditions passed on the first run without a correction. Their initial files were
byte-identical, and their edited files were byte-identical. Each file was 163 bytes.
Mido reduced this fixture's MIDI I/O code by 63 lines, or about 57%; the shared creative
score and mutation logic did not change.

## Verdict and limits

**Mido is not necessary for Agent-authored MIDI creation in this bounded task.** Ordinary
Python + NumPy expressed the performance and edit, and a manual standard-library codec
produced the same file. **Mido is useful for recurring MIDI I/O mechanics:** it met the
pre-registered code-reduction threshold without taking over creative decisions. Tactus
can keep performance generation in normal Python and use Mido behind an optional file
import/export seam when that seam is needed.

This is one same-agent fixture, not independent Agent trials. The manual reader only
handles the message subset it wrote; it has not been tested on arbitrary external MIDI,
running status, unusual meta messages, multi-channel performances, or malformed files.
The common oracle also uses Mido, so this does not independently certify Mido's parser.
No instrument rendering, audio quality, tempo-change audition, or direct `.mid` editing as
authoritative source was tested. Those remain separate MIDI product questions.

Disposable preregistration, source, and generated MIDI files remain under
`/tmp/tactus-midi-mido-probe.1s1Ikc/`; they are not durable repo fixtures. Product code
was unchanged, and there were no paid model calls.
