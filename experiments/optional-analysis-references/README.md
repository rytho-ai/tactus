# Optional external analysis references

**Current update:** librosa is an optional package extra, `tactus[librosa]`,
not a default dependency. Select `uv sync --extra librosa` in this checkout.
The earlier `reference` dependency group has been replaced by this extra.
Wheel metadata and an isolated wheel install confirm that the extra installs librosa;
default installs include neither librosa nor pyloudnorm. After this change, the focused
suite passed 185 tests (27 optional skips), and all 53 librosa reference tests passed.
Pyloudnorm is removed from the root and active example locks. Its 33 captured
answers support 29 ordinary tests; see [fixtures](../../tests/fixtures/README.md).
Numba is now a runtime DSP dependency. The historical measurements below describe
the earlier separation of both references, before these changes.

Originally, librosa and pyloudnorm were pinned in the optional `reference` dependency group.
Default development uses pytest/Ruff plus the existing seven runtime dependencies.
No analysis algorithm changed in this separation; upstream attribution remains.

## Verified environments

| Environment | Result |
| --- | --- |
| Exact default dev sync | librosa, pyloudnorm and numba absent |
| Default full pytest | 799 passed; 79 reference skips + 1 existing opt-in install skip |
| Independent reference environment | 79 reference tests passed; no skips; 800 deselected |
| Default real CLI | 9 positive checks and invalid-frontend rejection passed |
| Repository gates | Ruff, format and build passed |

[report.json](report.json) records the results. JUnit case identities confirm that
**every** missing-reference skip in the default run passed in the reference run.
Tests load optional packages through per-test fixtures, not module-level skips.
Twelve independent dense-log cases continue running without librosa; combined
checks were split so external peak-picking comparisons cannot hide independent math.
Known-signal, numerical edge, API and CLI tests remain active.

The nine CLI checks cover both SuperFlux functions/frontends, Mel/MFCC/chroma array
attachments, integrated LUFS and independent WAV export. Python and saved results
match; the exported preferred-C WAV retains its original hash. These operations
used the default checkout environment, not the separately installed references.
Wheel metadata lists only the seven runtime dependencies.

Local raw evidence is under ignored `dogfood/2026-09-29-optional-analysis-references/`:
`default-tests.xml`, `reference-tests.xml`, command captures, feature attachments,
export and dependency discovery. The historical onset comparison also reran in the
reference environment, reproducing earlier scores after correcting its source
inventory's retired `_librosa.py` filename.

## Commands

```bash
# Ordinary development: exact sync removes leftover optional packages.
uv sync --group dev
uv run pytest -q -rs

# External numerical comparisons only, or the complete suite with references.
uv run --extra librosa pytest -q -m reference
uv run --extra librosa pytest -q

# Return to a development environment without reference packages.
uv sync --group dev
```

`uv run` can leave extras installed, so an exact sync is necessary before claiming
that a package is absent. This trial used a separate `UV_PROJECT_ENVIRONMENT` for
reference tests; the main checkout remained reference-free and was synced again at
the end. No global tool installation changed.

Optional references still appear in uv.lock. Historical work locks and experiments
can contain librosa; the beat-alignment preparation/evaluation explicitly uses
`uv run --with librosa`. This does not port that example's DTW or delete its history.


## Pyloudnorm removal verification (2026-09-29)

At removal time, `reference` contained only `librosa==1.0.0`; it has since moved
to the `librosa` package extra with the same pin. Root and both active
example locks no longer resolve pyloudnorm. The archived clean-production handoff
still records its original vendored runtime; its historical lock is not a dependency
of current Tactus. Attribution and the adapted-code license remain in the wheel.

Before removal, 33 direct calls to pyloudnorm 0.2.0 were captured, with version,
source hashes, inputs and meter parameters. The existing 29 parametrized tests now
consume those fixed answers in the ordinary suite, with their previous tolerances.
Current `experiments/owned-analysis/check.py` uses only librosa for six feature/onset
comparisons; EBU and frozen test answers cover loudness.

[Removal report](removal-report.json):

- Focused analysis/loudness suite: **185 passed**, 27 optional librosa skips.
- Optional reference suite: **53 passed**, with librosa installed and pyloudnorm absent.
- Independent EBU integrated/M/S/LRA/peak corpus: **102/102 passed**.
- Three actual `uv run tactus analyze level ...` commands (integrated, momentary,
  short-term) match frozen values and saved JSON without either reference installed.
- Updated feature comparison script: **6/6 passed** with optional librosa alone.
- Ruff, Python formatting and wheel/sdist build pass. No algorithm/source changes
  to the loudness implementation, no new dependency, global reinstall or Git publication.

Reproduce the ordinary checks with `uv sync --group dev` and
`uv run pytest tests/test_analysis.py tests/test_owned_analysis.py tests/test_level_curves.py`.
Use `uv run --extra librosa pytest -m reference` for optional librosa comparisons.

## Clean installation and STFT/Mel verification (2026-09-29)

A separate local Git clone of `82d7486` plus the pending tracked changes contained no
blueprints, dogfood files or existing environment. `uv sync --frozen --offline --group dev`
installed a new environment from the lock, using a copied dependency download cache.
`uv build --offline` produced an sdist and wheel; both exclude blueprints. Replacing the
editable installation with that wheel verified imports from the new environment's
`site-packages`, not the development source. Default installs omit librosa and pyloudnorm.

- Analysis, image, CLI, export and custom-command tests: **129 passed**.
- A second new environment installed the built `tactus[librosa]` wheel, constrained by
  the lock: librosa 1.0.0 present, pyloudnorm absent; **53 reference tests passed**.
- The checked-in DSP effects example rendered six outputs. After deleting its generator,
  WAV export remained byte-identical to published WAVs; FLAC decoded arrays matched them.
- A 19 s fixture made from that render passed eight actual CLI analyses: loudness,
  onsets, beats, STFT, Mel, CQT, VQT and tempogram. The five matrix analyses emitted SVGs;
  artifact hashes matched and STFT/Mel NPZ arrays equaled direct Python results.

STFT revision 2 returns arrays directly and shares the numeric/image path with Mel.
See the [current usage and migration note](../../README.md#stft-mel-spectrogram-cqt-vqt-tempogram-and-images).
[clean-install-report.json](clean-install-report.json) records the source hashes, wheel
metadata and results. Raw CLI logs are local under
`dogfood/2026-09-29-stft-mel-clean-install/`.

This verifies a new environment on the same Linux/Python 3.12.11 host using cached
downloads. It does not establish cross-platform compatibility, a global tool update,
or remote publication. Source hashes identify the tested pending changes independently
of the base commit.
