# Frozen loudness reference answers

`loudness-reference.json` captures **33 independent pyloudnorm 0.2.0 calls** before
removing that package from Tactus. These values are consumed by 29 ordinary tests;
no reference package is required and these tests no longer skip in the default env.
Expected values were generated directly with pyloudnorm, never with Tactus.

The JSON records the source package/version, NumPy/SciPy versions, SHA256 of the
installed reference source files, meter parameters, input shape/sample rate and
little-endian float64 input hashes. Hashes document the original capture; tests
use numerical tolerances rather than require bitwise libm identity across platforms.
The input recipes remain in the corresponding tests:

| Case keys | Input recipe / test | Stored result |
| --- | --- | --- |
| `stereo-tone` | `test_analysis.test_loudness_matches_frozen_reference`: 3 s, 1 kHz, amplitude .2, R=.95*L | Integrated LUFS, default K-weighting |
| `integrated-{rate}-{channels}` | `test_owned_analysis.test_integrated_lufs_matches_legacy_gate_and_partial_tail`: NumPy seed 84, 2.357 s, stepped levels | Integrated LUFS, gates and partial tail |
| `silence-{rate}-{seconds}` | `test_owned_analysis.test_integrated_short_threshold_and_silence`: zeros, 0.399–1.05 s | Null for nonfinite integrated LUFS; `ValueError` also recorded below .4 s |
| `curve-{rate}-{window}` | `test_level_curves.test_loudness_matches_independent_meter_block_powers`: seed 3, 6 s stereo noise | Integrated and blockwise LUFS, DeMan, overlap .5, windows .4/3 s |

Tolerances stay at their previous values in the tests (integrated 1e-9/1e-8 absolute,
curves `assert_allclose` with atol 2e-8 and its existing rtol). Input shape/rate are
checked at lookup. Test answers must not be regenerated from the implementation
under test. Deliberately refreshing an oracle requires an independent source in an
isolated environment and review of changes to these values; normal development and
CI never install or invoke pyloudnorm.

These snapshots complement analytical channel/gain/window tests, the published
48 kHz K-weighting coefficients and an independent EBU corpus check retained in the
local experiments workspace. They are regression evidence, not a claim to
cover every possible audio input or the entire pyloudnorm API.
