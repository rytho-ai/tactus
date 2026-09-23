# MIDI boundary: Python owns the music, Mido owns file interchange

> 2026-09-23 · Working decision for Tactus Code. This closes the current MIDI-library selection, not the MIDI/groove integration in the production vertical slice.

## Decision

Keep Agent-authored musical logic in ordinary Python, using NumPy where it helps. A production may generate note and control events directly; it does not need a library-specific `Score` or a MIDI file as its creative source of truth. Use Mido by default when a workflow must read, preserve, or write a Standard MIDI File. Mido is a file-boundary tool, not a required composition model or universal runtime dependency.

Do not add Symusic, MusPy, or another note-level library as a default Tactus dependency now. Do not build a custom general MIDI parser to avoid Mido unless a concrete boundary requirement justifies that cost.

## Why this is enough to stop selection

- The [Python/NumPy versus Mido probe](2026-09-23-python-numpy-vs-mido-probe.md) and the existing `phonon-ballad` source show that Python can generate musical events and even write a bounded MIDI file without Mido. This establishes sufficiency of Python for creative logic, not that a custom MIDI implementation is the best interchange layer.
- [Independent Agent authoring](2026-09-23-independent-agent-midi-authoring-probes.md) and [real-piece maintenance](2026-09-23-phonon-ballad-midi-maintenance-probe.md) found no Agent reliability gain from Symusic over task-local Python plus Mido in the tested edits.
- The [imported-MIDI preservation probe](2026-09-23-imported-midi-preservation-probe.md) showed both arms could pass exact event checks, but the Symusic arm used a separate raw-MIDI preservation writer for its final output. Mido handled the same file-boundary job directly.
- The [batch-indexing probe](2026-09-23-symusic-batch-indexing-probe.md) confirmed Symusic's speed advantage, while showing that the absolute saving was small for the current `rytho-library` MIDI corpus.

The evidence supports Mido as a practical default at the file edge. It does not prove Mido is mathematically necessary, that Symusic cannot work, or that every future MIDI workload will have the same trade-off.

## Responsibilities and revisit trigger

Python production code chooses notes, timing, dynamics, controllers, and transformations. Tactus should standardize only the mechanics a real workflow repeatedly needs, such as musical-time conversion or validated file interchange; it should not predefine creative decisions through a large MIDI schema. A direct instrument/event path may skip MIDI files entirely.

Reopen library selection only when an actual production or catalog workflow shows a measurable gap: a required MIDI feature that Mido cannot preserve conveniently, a repeated note-level transformation that materially simplifies with Symusic, or batch parsing time that becomes visible in the Agent's workflow. Compare alternatives on that same workload, including correctness, Agent effort, and absolute latency.

The [production vertical slice](../plans/2026-09-16-code-first-production-slice.md) still needs real MIDI/groove integration and listening validation. Closing library selection does not mark that product work complete.
