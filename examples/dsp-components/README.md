# LR4 crossover and crossfade delay example

Run from the repository root:

```sh
uv run tactus run examples/dsp-components/song.py --out runs/dsp-components
```

The deterministic eight-second source needs no external assets. Outputs compare:

- `dry`: the source;
- `recombined`: LR4 low/high branches summed without further processing;
- `high_drive`: saturation only on the high branch before recombination;
- `full_drive`: the same saturation settings on the recombined signal;
- `crossfade_echo`: a dual-head crossfade when delay time changes;
- `gliding_echo`: an ordinary fractional delay whose readhead moves over the transition.

Echo targets change at 2, 4 and 6 seconds. Both comparisons use zero feedback,
65% dry / 35% wet, and include a 0.5-second tail. The default transition is 50 ms.
The crossfade keeps fixed head positions during each transition; interference can
change amplitude. It does not promise transparent switching. LR4 recombination
preserves magnitude response, not sample identity or phase.

Declared render parameters are `cutoff_hz`, `crossfade_seconds` and `drive_db`.
The public contracts are in the [DSP reference](../../skills/references/dsp.md). Each call starts
from silence; these examples do not expose streaming state or a new processor graph.
