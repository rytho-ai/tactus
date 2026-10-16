# DAWG-derived piano model

These Python implementations adapt DAWG, Copyright (c) 2026 Hraness, under the
MIT license reproduced in LICENSE.dawg. Preserve both files when copying them.
Upstream: https://github.com/hraness/dawg at
13263790ade044979b6268059ec91567d793e04f.

- piano.py: src/audio/keys/piano.ts, acoustic PianoVoice, tuning and grand/felt defaults.
- piano_dsp.py: src/audio/keys/dsp.ts and src/audio/random.ts, modal recurrence,
  seeded mechanics, hammer pulse, RBJ filters and deterministic RNG.
- performance.py: keys/engine.ts control/tail conventions and core/expression.ts
  sustain/half-pedal/restrike behavior, adapted to sample-frame/seconds inputs.

The port uses NumPy/SciPy/Numba, with no JavaScript runtime, samples or weights.
Original session, score and preset APIs are not part of Tactus. Prepared piano,
shared sympathetic resonance, ensembles, voice stealing and DAWG calibration trims
are excluded. A voice's state is local to a call; only compiled code is cached.
