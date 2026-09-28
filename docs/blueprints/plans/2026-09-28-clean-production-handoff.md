# Clean-environment production handoff — plan

> Generated: 2026-09-28 · Source: Paul approved the proposed rebuild, revision and delivery
> acceptance trial · Grounding: Tactus `6f6ae20`, dogfood 3 approved work `aa39c0f` / run `c7`.

## Context

The earlier A7 trial rebuilt in another directory while sharing this machine's material pool
and native tools. The new trial must establish which dependencies actually need transport.
Use the complete 46-bar, 74 BPM ambient work Paul approved: samples, SFZ bass through
`sfizz_render`, OB-Xf VST3 pads, and pytimestretch textures. Keep the original work untouched.

The work loads OB-Xf from the user's home without `tool()`. Its accepted performance is also
stochastic. These require explicit treatment: declare the plugin in a portable work copy;
compare stochastic rebuilds separately, then preserve the clean baseline's exact performance
through stage reuse while changing only bass gain.

## Approach

1. Prepare a versioned experiment under `experiments/clean-production-handoff`, with a
   reproducible work source, its own uv project/lock, dependency inventory and container recipe.
   Store audio, copied native binaries, pool blobs, wheels and delivery bundles outside Git.
2. Freeze a baseline using the current pinned Tactus environment, and record source/lock hashes,
   all material refs, native tool identities and dynamic library requirements. Resolve tree
   manifests recursively so SFZ samples are included, not just the manifest blob.
3. Build an Ubuntu/Python 3.12 container with a fresh environment and no developer-home mount.
   Transport only declared work source, required pool blobs, plugin bundle and sfizz binary;
   install their documented system libraries in the image. Record the image identity and package
   versions. Rendering runs with `--network none` and a fresh destination pool/cache.
4. Exercise missing-material/tool checks before restoration, restore the transfer bundle, and
   render a clean baseline. Deterministic stems must match the host baseline exactly; report
   stochastic pad differences with the prior per-section 1 dB tolerance, without bit-identity claims.
5. Produce a candidate changing bass gain from -3 to -6 dB. Reuse the clean baseline stages so
   pads, keys, drums and textures remain byte-identical; only bass and mix may change. Confirm
   the bass change numerically and preserve both candidates as unaccepted review artifacts.
6. Deliver named mix/stems with aligned frame counts, tempo/section metadata, source/lock,
   receipts and checksums. Verify the bundle from a new directory and provide a local listening
   and download page. No assets or native binaries are publicly published.
7. Record measured gaps and outcome in the existing thoughts/board structure. Make runtime
   fixes only if a demonstrated defect blocks this workflow. Run pytest, Ruff and actual CLI checks.

## Critical files

| File | Responsibility |
|---|---|
| `experiments/clean-production-handoff/` | Preparation, dependency inventory, container recipe and acceptance evaluator |
| `dogfood/2026-09-28-clean-production-handoff/` (ignored) | Transfer assets, isolated destination, render and delivery artifacts |
| `docs/blueprints/thoughts/2026-09-28-clean-production-handoff.md` | Findings, evidence and limits |
| `docs/blueprints/plan.md`, `docs/design.md` | Current verified portability boundary |

## Verification

- No host venv, home, original work directory or original pool is mounted into the container.
- Rendering has no network; all file/tree material hashes and native tool hashes verify.
- Missing input/tool checks identify what must be restored; corrupt blobs are rejected.
- Fresh-baseline deterministic stem hashes match. OB-Xf variation is reported independently.
- Bass-only candidate changes bass/mix; four other stems match exactly, with reuse receipts.
- Delivery stems share rate/start/length; checksums survive unpacking to a new directory.
- Full pytest, Ruff, real container render/CLI, and listening-page/download checks pass.

## Out of scope

Cross-OS bit identity, universal plugin compatibility, public distribution of third-party
materials, a new generic packaging CLI without evidence, or choosing the quieter bass for Paul.

## Evidence-driven extension

The first fresh rebuild failed the original reproduction gates: SFZ bass differed on four
notes; OB-Xf outro RMS differed by 1.075 dB. Preserve that failure. Subsequent minimal SFZ
and pipeline probes matched, so the bass cause remains unconfirmed; no native-engine fix is
claimed. Add a second, explicitly different trial: pin the host baseline's pre-gain pads and
bass stage arrays as materials, retain their generation source/receipt, and transfer them to
another fresh pool. Require all six outputs to match the host baseline exactly. This proves
saved-performance portability, separately from regenerating instruments. Deliver this stable
baseline and its bass-only candidate, with the failed synthesis evidence alongside.

## Outcome

Completed with two distinct verdicts: fresh instrument regeneration failed; saved-performance
handoff, bass-only revision and delivery passed. All six saved-performance WAVs matched the
host, four untouched stems survived the edit exactly, 14 negative checks passed, and the
ZIP/rebuild inputs were unpacked and verified. Full pytest: 400 passed, 1 opt-in skipped;
Ruff and browser/CLI checks passed. No runtime API or native-engine fix was introduced.
See the [findings](../thoughts/2026-09-28-clean-production-handoff.md).
