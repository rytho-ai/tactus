# Accelerating DSP and synthesis code

Speed work is an experiment: measure the real workload, change one thing, prove the output
is unchanged, and keep the change only if the measurement improves.

## Steps

1. **Profile the real work first.** Run the actual render under `cProfile` before timing any
   function in isolation. Time often sits outside the suspected hot loop: import and startup,
   many short per-note calls, or one library call repeated hundreds of times.
2. **Time the three shapes separately.** Long-clip throughput (one 60 s call), per-call cost
   (hundreds of 0.1 s notes, the usual composition pattern) and first-call cost (Numba compile
   or cache load, paid once per process). A change can win one shape and lose another.
3. **Save reference outputs** of the current implementation for a fixed set of cases
   (mono/stereo, scalar/per-frame controls, edge lengths) before editing.
4. **Name the cost** the profile shows, then pick the matching remedy from the table below.
5. **Verify equality**: sample-identical where the arithmetic order is unchanged; otherwise
   state a tolerance (around 1e-12 for float64) and say why the order changed.
6. **Keep or revert.** Done when every case matches and the timing improves on the workload
   that mattered. Revert attempts that tie or lose, and note why in the work.

## Which remedy fits which cost

Gains are what Tactus's own blocks showed; treat them as orders of magnitude and measure your case.

| Cost the profile shows | Remedy | Typical gain |
|---|---|---|
| A sample-by-sample recurrence (filter state, delay line, string loop) | Small `@njit(cache=True)` kernel; validation stays in Python | about 200× over a pure-Python loop (Karplus-Strong) |
| A Python loop over many small items (grains, notes, events) | Move the whole loop into one kernel | about 2× from loop overhead alone |
| The same table rebuilt for each item (a window, a wavetable) | Compute it once per distinct shape and reuse it | 3–4× more when shapes repeat |
| Independent channels in a heavy kernel | `parallel=True` with `prange` over channels; each channel's order is unchanged | close to the channel count |
| Slow startup | Import heavy modules inside the function that needs them | `scipy.signal` alone costs about 0.4 s |

## Costs Numba does not reduce

Leave these on NumPy/SciPy; moving them into a loop ties or loses:

- **Optimized library C code**: SciPy `upfirdn`/`resample_poly`, `lfilter`, FFT.
  Hand-written FIR loops tend to win on long clips and lose on short notes; loop orders that
  sweep the output repeatedly thrash the cache.
- **Transcendental functions on whole arrays**: NumPy's `tanh`, `sin` and `exp` use SIMD;
  inside a Numba loop each call is a scalar libm call.
- **Reductions without fastmath**: a dot-product loop cannot be reordered into SIMD and stays
  latency-bound. Several independent accumulators help a little; a vectorized library call
  usually helps more. Tactus's builtin kernels keep fastmath off so their arithmetic order is
  reproducible; your work may enable it if it accepts changed rounding.
- **Per-frame element-wise math between Python callbacks**: when each frame's cost is array
  math (`angle`, `mod`, `exp`), batching the surrounding calls does not help.

## Correctness while optimizing

- Keep the clear Python or NumPy version as the reference and test the kernel against it,
  including state at block edges and empty or one-sample input.
- Measure cold first call (compile or cache load) apart from warm calls; a kernel that
  wins warm can still slow a one-shot audition.
- `parallel=True` is safe only where iterations are independent; recurrences stay serial
  inside each channel.
