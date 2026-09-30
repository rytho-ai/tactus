---
name: compose
description: Write, run, audition or revise music as a Tactus Python work. Use for arranging clips, sampling, synthesis, MIDI, routing, automation, combining analysis with effects, pinning inputs, comparing candidates or preserving chosen performances. Connect to dsp for processing design and measure for using or writing analyses.
---

# Compose with Tactus

A work is ordinary Python and NumPy defining `render(*, ...)`. You choose its materials,
notes, timing, processing order, routing and form. Tactus runs it, saves audio and records
what produced it. Builtin DSP, Pedalboard, other libraries and your own functions are
equally valid building blocks; builtin source can also be studied and adapted.
When choosing a package or connecting its audio/MIDI to the work, read
[Packages and integration notes](../references/packages.md) for available tools,
installation scope, layouts, time units and state/reproducibility caveats.

## Develop the work

1. **Start from the intended sound or revision.** Locate the existing source and inputs.
   For a new work, `tactus init DIR` creates its uv project; it does not compose a song.
   Check `tactus doctor` and read [Creating a work](../references/runtime.md#creating-a-work)
   when installing or selecting an environment.
   Follow [version](../version/SKILL.md) to verify the work is tracked and
   commit its starting source before the first render.
2. **Pin inputs.** Use `tactus material add FILE_OR_DIR` and keep the returned ref in source;
   resolve it with `material(REF)`. Declare external binaries and plugin bundles with
   `tool()`. See [Inputs](../references/runtime.md#inputs) for folder materials and loading.
   When chopping loops or mixing from saved stems, read
   [Source regions and audio delivery](../references/production.md) to declare the musical
   body, tails and processing boundaries.
3. **Express the idea in functional code.** Extract coherent musical and processing logic
   into functions and modules that make the next edit easy. Choose the arrangement
   representation that suits the work. Read the
   [render contract](../references/runtime.md#the-render-contract) before returning audio.
   Expose choices you want to compare as keyword-only parameters with JSON-valued defaults.
4. **Render a candidate:** `tactus run song.py --out runs/a --params '{"gain": 0.2}'`.
   Choose a new directory each time; keep generated runs outside Git and available while
   listeners use them. Read the returned paths and [run results](../references/runtime.md#run-results).
5. **Listen, compare and revise.** Numerical checks establish technical facts; use listening
   and the user's intent to judge musical results. If listening tools are unavailable, say
   what was measured and what remains unheard. For an excerpt, use `tactus excerpt` on the
   saved full run so tails, phase and preceding state match the actual candidate.
   Use [version](../version/SKILL.md#revise-and-adopt) for the Git base,
   candidate attribution and adoption commit.
6. **Preserve the selected result.** Adopt parameter values or material refs in source.
   Use [Saved takes](../references/runtime.md#saved-takes) for performances that vary on
   each render. Follow [Keeping a candidate](../references/runtime.md#keeping-a-candidate)
   to archive approved audio and record the revision. If source changed, render and compare
   the new candidate before claiming it is the approved one. Preserve unrelated user edits.

## Connect capabilities when the idea calls for them

- Read [dsp](../dsp/SKILL.md) when designing a processor, adapting an algorithm, deciding
  state/tail behavior, or turning a curve into an audio effect.
- Read [measure](../measure/SKILL.md) when choosing observations, writing an analysis,
  comparing candidates objectively, or extracting controls from source audio.
- Read [Creative connections](../references/connections.md) when an idea crosses these
  boundaries: source energy could change phrase lengths, then move a filter after stretching;
  onset candidates could guide chopping; a custom descriptor could control another voice.
  Decide the musical mapping yourself. These are starting points to alter or discard.

The [runnable examples](../examples/README.md) combine local DSP, Tactus, Pedalboard and
analysis-driven time warping. They are optional vocabulary, not a required production sequence.

## Maintain music as code

**Write functional code.** Pass data through arguments and return values. Keep input arrays
unchanged; allocate buffers you own for in-place mixing. Make processor state and random
seeds explicit, and keep module-level values constant. Separate file/tool access at clear
boundaries from transformations where practical. Bind shared intermediates once and reuse
them, so parallel branches have visible dependencies.

**Modularize coherent responsibilities.** When a phrase, instrument, arrangement rule,
processor or measurement can be understood and changed independently, give it a named
function or module with clear inputs and outputs. Reuse shared logic rather than copying
it across sections. Keep one owner for each musical choice; let callers express how parts
connect. Name modules by their role in the work. Choose the grouping yourself: a mandatory
Track/Bus model or fixed material/effect/arrangement directory tree is unnecessary.

**Design deep modules.** A module can be a function or a file: its depth comes from how
much useful behavior a caller gets through a small, clear interface. The interface includes
units, shapes, state lifetime, ordering and failure behavior, not just its signature.
Keep implementation details local while exposing the musical choices callers need to control.
For example, a phrase processor can own buffer allocation, interpolation and tail handling
behind audio, rate and meaningful controls. A change to its algorithm should usually stay
inside that module. If callers must coordinate all its internal steps, deepen the module;
if deleting a wrapper removes complexity rather than spreading it to callers, simplify it.
Test meaningful behavior through the same interface the work uses.

**Use progressive disclosure to write and navigate code.** The entry point should reveal
the work's overall form and signal flow through meaningful calls. Module/function summaries
describe purpose, inputs, outputs and relevant state/time conventions; open implementation
details when the current question needs them. To revise a work, start at `render`, follow
the relevant calls, read the owning module's contract, then inspect its algorithm. Keep the
other parts understandable through those boundaries instead of reading every file up front.

**Make revisions reviewable.** Change the owner of the musical decision, inspect the diff,
and check its intended impact. Render/listen to the affected context; when a part should
stay identical, compare its saved output or intermediate array. Add focused tests for
reusable algorithms and bug fixes where they protect a meaningful behavior. Git records
source, refs and locks; generated runs provide evidence for the musical revision.

Freeze accepted analysis decisions as source constants or pinned data, with source identity
and units. Reanalysis then becomes an explicit revision. Signal-following processors such as
envelope followers may run inside `render` as part of the sound. When timing changes, choose
whether controls follow source time or output time; see the connections reference.

Consult [Musical time](../references/runtime.md#musical-time-optional) for optional timing
helpers, [stage reuse](../references/runtime.md#reusing-unchanged-stages) for unchanged
computations, and [project commands](../references/project-commands.md) for delivery from
saved renders. Installed signatures and `--help` describe the work's pinned runtime version.
