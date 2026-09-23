# Symusic batch-indexing probe

> 2026-09-23 · This evidence feeds the pending Tactus MIDI dependency decision back to Paul; it is not API approval.

## Question and preregistered rule

A plausible Symusic-specific workload is indexing a large MIDI library: parse each file into note onset, duration, pitch, and velocity, then compute a pitch histogram and total sounding duration. This uses Symusic's native note-level representation and fast parser rather than testing small hand-authored edits again.

Before running, the rule was: both implementations must produce identical note rows and index results; for a 500-file batch, Symusic must be at least 5× faster and save more than 2 seconds to count as a material batch-workflow benefit. A one-file measurement would prevent confusing throughput gain with an everyday single-production need. No paid Agents were used; product code was read-only.

## Controlled long-song workload

The input was one verified 76-bar phonon-ballad MIDI with 884 notes, repeated in memory to simulate 500 files of that complexity. Both implementations performed decoding, note extraction, and the same NumPy indexing work. Note rows and index results matched exactly, including 884 notes and 505,840 total note-duration ticks.

Across alternating timed runs, the one-file medians were 3.81 ms for Mido and 0.057 ms for Symusic: roughly 67× faster, but only 3.75 ms saved. The 500-file medians were 1.908 s and 0.0219 s: roughly 87× faster and 1.886 s saved. The preregistered 2-second absolute-saving threshold was not met. Repeating one file measures CPU parsing/indexing throughput, not disk I/O or diverse-file behavior.

## Real-library check

`rytho-library` contained 544 paths ending in `.mid`/`.midi`; two were HTML files mislabeled as MIDI, which both parsers rejected. The remaining 542 valid files contained 17,454 notes and 186,967 logical bytes. Mido and Symusic produced identical note rows and index results for all 542.

For those valid files, median full-corpus indexing time was 78.6 ms with Mido and 9.10 ms with Symusic: 8.64× faster, but only 69.5 ms saved. This is an effective speedup but not a meaningful wait reduction for the library as it exists today. Excluding the two mislabeled files is a fixture-quality adjustment; the full 544-path corpus was not a clean all-MIDI input.

## Verdict

Symusic's speed advantage is real for note-level batch indexing, but this probe did not identify a current Tactus workload that requires it. The pre-registered 500-long-song case narrowly missed the absolute-time threshold, while the actual 542-file library saved less than a tenth of a second. Continue with Python/NumPy plus Mido for present creative and MIDI-preservation work. Reconsider Symusic as an optional batch-indexing backend if the workload grows substantially or if repeated catalog queries make parse time observable.

This probe did not test Agent coding success, MIDI rewrite fidelity, disk-bound indexing, diverse long compositions, or memory use. The benchmark harness and outputs are disposable under `/tmp/tactus-symusic-batch-probe/`.
