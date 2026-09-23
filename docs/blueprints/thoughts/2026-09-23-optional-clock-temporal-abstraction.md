# Temporal abstraction without a mandatory global clock

> 2026-09-23 · Working conclusion agreed with Paul. This records the distinction between time tools and a work-wide clock; it does not approve a new public API or claim that the current renderer implements the model.

## Conclusion

Keep temporal abstraction available, but do not require every work to declare a global BPM or a work-wide clock. Production Python remains the creative source of truth: the author may define a global tempo map, independent local clocks, absolute-time events, or any mixture of them. Tactus should accept honestly resolved placement and duration without fictitious BPM/bar metadata, then resolve output positions consistently to samples.

This separates two questions:

- **Temporal abstraction:** How source code expresses, transforms, repeats, and resolves temporal relationships. It may be task-local Python or optional shared helpers such as `bar`, `beats`, `place`, `repeat`, `scale_time`, and `section_envelope`.
- **Global clock:** An optional shared mapping from a work's global beat position to absolute time. It is authored musical intent, not a prerequisite for rendering or for using temporal helpers.

A work can have a global clock without using a framework-owned clock object. It can also have no global clock while using absolute seconds, a seconds-anchored local clock, and temporal helpers. “No BPM” means no mandatory global beat grid, not no timeline or no rhythmic passage anywhere.

## Clock semantics to preserve

A global tempo change changes positions that follow global beats. An independent local BPM changes only events using that local clock. A local clock anchored to a global beat follows that anchor if the global tempo changes; one anchored to absolute seconds does not. Absolute-time events remain fixed when either BPM changes. These are distinct dependencies and must not be collapsed into one ambiguous `local_bpm` operation.

All forms ultimately produce output-time positions, but the authoring relationships need not become a mandatory arrangement schema. The compiled graph is derived from source, not a second editable source of truth.

## Evidence and current gap

The [beat/free-time probe](2026-09-23-beat-and-free-time-boundary-probe.md) found that current Tactus rejects a free-time work without `TRANSPORT`; two fake BPM encodings of the same audio made semantic diff report changes. The [mixed-clocks probe](2026-09-23-mixed-clocks-vs-python-probe.md) showed ordinary Python and NumPy correctly handled global tempo changes, independent local BPM, and no-global output. This establishes sufficiency for that short work, not long-term Agent maintainability or a need for framework-owned clock classes.

Earlier [Python/Pattern authoring probes](2026-09-22-python-pattern-authoring-boundary.md) support small optional temporal primitives for recurring placement and transformation math. They do not establish that Tactus must own every tempo map or local clock. The current `Project` still requires `bpm` and `bars`, and `Track.place` accepts only `at_beats`; the working conclusion is not yet implemented.

## Still undecided

1. **Placement interface:** The smallest honest way to pass seconds/sample positions and total duration into Tactus, while preserving existing beat-based source compatibility. `seconds(...)`, `at_seconds=...`, and a typed position are candidates, not decisions.
2. **Helper ownership:** Whether repeated tempo-map/local-clock calculations should remain task-local Python, live in an optional Tactus library, or become part of the core interface. Compare actual Agent revisions on the same work before promoting them.
3. **Compiled provenance:** Whether graph diff, cache invalidation, and audition need to retain “this event follows global beat 8” versus only its resolved output position. Source plus Git retains the relationship, but a compiled consumer may need more evidence.
4. **Harder time cases:** Gradual tempo curves, rubato, nested/relative clocks, event duration across tempo changes, rounding to samples, and stateful range rendering have not been established by these probes.

The immediate product gap is the false-BPM requirement. The wider clock model should grow only when a real revision or compiled consumer demonstrates what the minimal interface cannot express or maintain reliably.
