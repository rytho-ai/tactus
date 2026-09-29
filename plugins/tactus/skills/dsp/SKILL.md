---
name: dsp
description: Use, write or adapt audio-processing functions for Tactus works. Use for custom effects, control curves, filters, delays, modulation, nonlinear processing, processor state, DSP correctness or measured acceleration. Builtin Tactus DSP, Pedalboard and work-local Python can be combined or used as implementation references.
---

# Build and combine DSP

Start with the audible behavior you want to create. Use an existing processor, adapt its
implementation, write a local function, or combine these approaches. A custom effect is
ordinary Python called from a work; it needs no Tactus registration or processor base class.
Read [Packages and integration notes](../../references/packages.md) when selecting a
library or crossing array, MIDI, plugin-state or time-stretch interfaces.

## Shape the function around the sound

1. **Choose a signal boundary.** State input/output shape and rate, dry/wet meaning, length,
   latency, tail, parameter units and state lifetime. Whole-clip reset and continuous block
   processing are different contracts; choose the one the work needs.
2. **Find useful mechanisms.** Read [Builtin DSP](../../references/dsp.md) for available
   operations, then inspect the installed function's signature, docstring and source when
   adapting it. Use `inspect.getsource(tactus.dsp.delay)` or the module's `__file__` in the
   work's Python environment. Private kernels are implementation references; own copied or
   adapted code locally and respect its license. Read a dependency's own API for its details.
3. **Implement an explicit transformation.** Pass audio, controls and any state as arguments;
   return audio and state when needed. Preserve caller arrays. Choose interpolation and
   smoothing for time-varying parameters, and process the intended tail. Keep deliberate
   distortion distinct from accidental clipping at the delivery boundary.
4. **Check the mechanism with a revealing signal.** For a delay, locate an impulse and its
   repeats; for a filter, measure a known tone or response; for modulation, inspect a
   transition; for nonlinear processing, compare aliasing across rates/oversampling.
   Exercise silence, short input, stereo and relevant parameter boundaries. Compare blocks
   with whole-clip output only when continuous state is part of the contract.
5. **Hear it in the work.** Return dry/wet or alternative outputs when that helps comparison.
   Use [compose](../compose/SKILL.md) for candidate execution and preservation, and
   [measure](../measure/SKILL.md) for a numerical question. Passing checks does not establish
   musical usefulness; keep the implementation that serves the intended sound.

## Controls can come from analysis

Read [measure](../measure/SKILL.md) to use or write a descriptor. Define its musical mapping:
range, polarity, interpolation, edges and silent/missing values. A feature sampled every
20 ms is not yet per-sample automation. If the audio is stretched, explicitly map between
source and output coordinates; [Creative connections](../../references/connections.md)
explains the choices and links an executable example. Audio-rate followers can remain
inside the processor; adopted slice/warp decisions can be frozen outside the render.

## Accelerate measured bottlenecks

Begin with NumPy/SciPy for array operations and native filters. Benchmark the actual workload
before changing it. Numba is useful for sequential sample loops: keep validation in Python
and compile a small numerical kernel, typically with `@njit(cache=True)`. Compare against
the clear reference implementation, including state and edges. Measure compilation/cache
load separately from warm execution; a warm speedup can still slow a one-shot audition.
Choose precision and tolerances deliberately. Add parallelism only where iterations are
independent and measurements justify the overhead.

The [colored taps and mixed processing examples](../../examples/README.md) illustrate
local DSP beside builtin and Pedalboard effects. Their structure and sound are yours to change.
