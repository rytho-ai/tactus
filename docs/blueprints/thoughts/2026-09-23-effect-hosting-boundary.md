# Effect hosting: settle the backend choice, keep the workflow question open

> 2026-09-23 · Working decision for Agent-first, offline Tactus Code. This closes the
> current host-selection investigation, not the implementation or compatibility work.

## Decision

Use **Pedalboard + small Tactus helpers** as the first effect-processing and VST3-hosting
path. Keep **DawDreamer as a reference** and defer a custom JUCE binding or direct-SDK host
until a required workflow demonstrates a gap that a targeted extension cannot reasonably
close. Python + NumPy/SciPy remain valid for Agent-authored DSP; the Agent chooses the
effects, order, parameters, automation shape, and routing intent. Tactus owns repeatable
execution mechanics, not creative policy.

This is a backend direction, **not** a claim that Tactus already has an integrated effect
chain, universal VST compatibility, or external sidechain support.

## Why this is enough to stop host selection for now

- The [host capability probes](2026-09-22-plugin-host-capability-probes.md) exercised
  parameter inspection and setting, cross-process state restore, and missing sampler
  assets. Pedalboard handled the tested parameter and restore paths; explicit material
  inventory is still needed because a plugin can silently output nothing when an asset
  disappears. Metadata repair and dependency checks fit small helpers.
- The [segmented automation probe](2026-09-23-pedalboard-segmented-automation-probe.md)
  changed a parameter at an exact input-sample boundary by processing adjacent chunks
  through the same plugin with `reset=False`. A real delay preserved its echo across
  chunks. Control-rate curves were practical in this small test. This does not provide
  VST3 sample-offset event queues inside one processing call.
- A [direct VST3 SDK probe](2026-09-23-direct-vst3-host-probe.md) and an
  [Agent-authored JUCE probe](2026-09-23-agent-native-juce-probe.md) showed bounded native
  hosting is possible. Neither demonstrated that maintaining a general host is cheaper
  or more reliable than extending the Pedalboard path.

The clear exception is **external sidechain**: Pedalboard's tested public path cannot
feed a separate control bus into a VST3 effect. A thin native binding did so in the
controlled probe. Keep this as a known capability gap, not a reason to silently claim
all effect chains work and not yet a reason to replace the whole host.

## Responsibilities and revisit trigger

The first helper candidates are parameter inspection/validation, explicit asset checks,
channel-layout checks, and segmented parameter scheduling. They should be introduced
where the real production needs them; this thought does not commit to a public chain
schema or a universal `process(...)` API.

Revisit the backend choice when a concrete production needs external sidechain or
another unsupported operation. Compare a narrow Pedalboard native extension against a
separate host using the **same target plugin and production task**, including audio
correctness, Agent-facing friction, and maintenance cost. Do not infer general host
quality from one fixture.

## What remains unverified beyond host selection

The next product-level gate is still the [code-first production vertical slice](../plans/2026-09-16-code-first-production-slice.md): adapt a real musical source and workflow,
compare it with the existing production path, and get Paul's listening judgment. The
[plan board](../plan.md) owns priority and status; this section records the distinct
questions rather than creating another roadmap.

1. **End-to-end musical workflow:** Can Python-authored materials, real samples, MIDI,
   effects, and revision be produced and maintained without task-specific framework
   contortions? Pitch-preserving warp and source-rate conversion remain separate fidelity
   questions.
2. **Actual audition loop:** Can the formal Tactus runtime provide correct stateful
   `range`/`stem` auditions, temporary parameter trials, metrics, and useful latency?
   Existing [audition evidence](2026-09-21-stateful-audition-first.md) comes largely from
   disposable runtimes and numeric goals; Agent-led subjective musical improvement is
   still untested.
3. **Derived graph payoff:** The [graph probe](2026-09-21-production-graph-first-probe.md)
   established inspection, semantic diff, and source-free replay, but not safe selective
   recomputation or faster audition. A production-scale consumer must justify any new
   graph fields; code remains the creative source of truth.
4. **Authoring abstractions in context:** Functional Python + NumPy and optional local
   [Pattern functions](2026-09-22-python-pattern-authoring-boundary.md) have bounded
   support. Their value for real arrangements, temporal controls, targeted rendering,
   and longer-lived Agent maintenance remains to be tested in the product workflow.
5. **Effect compatibility at the point of need:** A real stateful compressor with external
   sidechain, multi-effect latency/tail handling, commercial plugin quirks, fast
   modulation, crash recovery, and cross-platform behavior are open. These are
   compatibility gates, not prerequisites for restarting host selection immediately.

The first four questions determine whether Tactus helps an Agent make and revise music.
The fifth should be pulled forward only by a production that needs the capability.
