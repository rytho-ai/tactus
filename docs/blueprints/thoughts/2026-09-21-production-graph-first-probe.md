# Production Graph first behavior probe

> 2026-09-21 · This evidence feeds the pending Production Graph decision back to Paul. It compares a source-only direct render with the existing compiled-graph path on one controlled `chop-flip` revision; it does not establish a universal music schema.

## Question and pre-registered rule

Does persisting a Production Graph provide useful inspection, diff, replay, or computation reuse beyond ordinary Python source plus retained stems?

The Graph earns a second experiment if it provides at least two real capabilities that the source-only condition would need equivalent persistent structured state to match, without changing creative code or becoming a second source of truth. It remains optional if it improves inspection or packaging but does not reduce computation. It is not justified if it merely duplicates source and outputs without an active consumer.

## Method

Both conditions used copied versions of the same modular `examples/chop-flip` project. The only source revision changed `BASS_DRIVE` from `2.4` to `3.2`.

- **Condition A — source-only:** execute the Python authoring source and immediately render mix plus stems; retain no compiled graph or material store.
- **Condition B — compiled graph:** run the existing `build` path, retain `arrangement.json`, receipt and materials, then render in a separate step.

Both conditions used the same `Project`, computation functions and render math so that graph persistence was the controlled axis. A disposable harness recorded computation calls, output hashes, graph facts and source-free remix/replay behavior. Product code remained read-only.

The first run was invalid because Python reused `parts.bass` from the v1 fixture when loading v2 in the same process. That result was discarded. The valid rerun purged fixture-local modules between versions before collecting evidence.

## Results

### Output parity and revision isolation

Condition A and B produced byte-identical mix, sample, drums and bass WAVs for both versions. In both conditions, the revision changed only `mix` and `stem:bass`; `stem:sample` and `stem:drums` remained byte-identical.

The existing semantic diff reported that `bass-0` through `bass-7` changed and transport did not. The graph also contained the deeper cause: computations `808-0` through `808-7` changed `drive` from `2.4` to `3.2`, and each output material changed. The current `tactus-code diff` surface does not report that computation-level cause; a separate graph query was required.

### Source-free inspection

With only retained stems, the source-only condition exposed filenames, decoded duration, sample rate and audio samples. It did not retain BPM, bar count, event identities, computation parameters or declared-input provenance.

With source absent, the compiled package still exposed 90 BPM, eight bars, 48 kHz, three named tracks, 41 events, 12 computations, stable computation identities and every 808's pitch, duration, drive and output material.

### Source-free replay

For this simple additive fixture, retained stems were sufficient for the source-only condition to produce bass-only and bass-muted mixes. Its bass-only output was byte-identical to the compiled graph renderer's solo-bass mix. Source-free mute/solo therefore does not by itself establish that a graph is necessary.

The compiled graph additionally preserved the instructions and material references needed for the shared renderer, rather than relying on a project-specific assumption that retained stems may simply be summed. More complex routing, effects, automation and tails were not tested.

### Computation reuse

Neither condition reused computations. Both v1 and v2 executed all 12 calls:

```text
source-phrase
chops
kick-sound
hat-sound
808-0 ... 808-7
```

The current `solo` render path also renders every track before selecting which track enters the mix. The graph records facts that could support invalidation and selective execution, but the current build and render consumers do not use them that way.

### Derived-state check

A clean rebuild of v2 produced byte-identical arrangement JSON, receipt, mix and bass stem. Deleting generated state therefore did not lose a creative decision in this fixture; the graph remained a reproducible build artifact rather than a second source of truth.

The v2 compiled package contained a 19,830-byte graph, an 845-byte receipt and about 9.4 MB of content-addressed materials. The source-only retained delivery set contained about 24 MB of mix plus three stems. These are different artifact scopes, so the size difference is descriptive rather than a storage verdict.

## Verdict

**Graph has demonstrated value, but only as an optional compiled artifact so far.**

The graph has active consumers and makes source-free inspection, stable identity, parameter provenance, semantic track/event diff, integrity checking and portable compiled replay possible. Matching its inspection and cause-level diff in the source-only condition would require adding a persistent structured manifest, which is graph-like state under another name.

It has not yet demonstrated incremental build, selective recomputation, faster audition, a universal schema or easier musical authoring. Retained stems already cover source-free mute/solo for this fixture. The evidence supports one further experiment—using the recorded computation identities and dependencies to reuse unchanged materials—but does not support making the graph a required Tactus core.

## Next deciding experiment

Build a disposable incremental planner over the same bass-only revision. Reuse v1 materials when a computation's callable identity, source identity, explicit inputs and parameters remain unchanged; execute only invalidated computations; then compare the incremental graph and audio byte-for-byte with a full v2 rebuild.

The planner passes only if it executes the eight changed 808 computations, reuses the four unchanged sample/drum computations, produces the exact full-rebuild graph and audio, and rejects a corrupted cached material. Failure to identify dependencies safely means the current graph is a report, not yet a reliable build graph.

## Limits

- One small synthetic, additive fixture cannot establish cross-workflow schema fitness.
- Timings came from single local runs and are not used as performance evidence.
- Condition A used the same in-memory authoring model to control render behavior; this probe tested the persisted compiled artifact, not whether any shared music schema is necessary.
- No routing, plug-ins, external tools, automation, real media or hidden dependency was exercised.
- Scratch harness and raw evidence were retained only under `/tmp/tactus-production-graph-probe-retry.2tFS78/` for the active session.
