# Deterministic instrument regeneration

> Product decision, 2026-09-29: use original instruments and [saved takes](../saved-takes/README.md).
> Native patches below remain research evidence, not an installation requirement.

**Both local native patches passed full-song regeneration.** Three fresh offline containers
regenerated the 46-bar song, without stage reuse or saved performance arrays. All six WAVs
matched byte-for-byte. The installed plugin and sfizz executable remain unchanged.

This follows the [clean handoff](../clean-production-handoff/README.md). That experiment first
preserved audio as materials; this experiment fixes repeatability at native synthesis instead.

## Evidence and limits

| Test | Outcome |
| --- | --- |
| Installed OB-Xf, three fresh processes | Three different outputs |
| Zero all four slop controls | Still different |
| Seed C RNG, with/without zero slop | Still different |
| Rebuilt unpatched OB-Xf, three fresh processes | Three different outputs |
| Same build with repeatable initialization, five fresh processes | All float32 arrays identical |
| sfizz with delayed background dispatch, one note | All three runs differ from the healthy reference |
| Same dispatch delay plus loading-barrier fix | Three single-note and three full-bass renders exactly match healthy references |
| sfizz production patch, no injected delay | Ten full-bass renders on one CPU exactly match the healthy reference |
| Both patched instruments, full Tactus production | Three fresh containers; all six WAVs identical; bass/drums/keys/textures match prior host outputs |

Raw sfizz repeatability failures are intermittent without perturbation. The unmodified normal
10-run controls happened to match in this trial; their success does not erase the previous
observed failure. Delaying dispatch supplies a stable red-capable reference comparison.
See [evidence.json](evidence.json) and the [findings](../../docs/blueprints/thoughts/2026-09-28-deterministic-instruments.md).

These results apply to the pinned native revisions, this MIDI/patch and this Linux machine.
They do not establish cross-platform identity or deterministic behavior for every SFZ opcode.
The OB-Xf patch uses fixed internal seeds and is not a host-exposed seed parameter or saved
plugin-state feature. It selects a new performance; it does not reconstruct the old accepted take.

## Native patches

- [`obxf-repeatable-initialization.patch`](obxf-repeatable-initialization.patch), against
  [OB-Xf `1223e6f`](https://github.com/surge-synthesizer/OB-Xf/tree/1223e6f7b209b9affa91331c26f39d4095a4088e):
  replaces system/process-global randomness with local fixed seeds for voice slop, oscillator
  phase/tuning/noise and LFO state. Voice seeds differ by index; slop parameter amounts and DSP
  remain active. Root seeds are fixed at 42/43 for this experiment. Upstream-friendly seed/state
  controls and live-host reset semantics need separate design before product integration.
- [`sfizz-loading-barrier.patch`](sfizz-loading-barrier.patch), against
  [sfizz `f5c6e29`](https://github.com/sfztools/sfizz/tree/f5c6e29f23b8057867c08e88f5f6ac6738baa30b):
  `waitForBackgroundLoading()` drains pending requests into the worker pool under the existing
  dispatcher mutex, then waits for all jobs. Previously it waited only for jobs already
  dispatched; the render thread could outrun the dispatcher and sample loading.
- [`sfizz-dispatch-delay.patch`](sfizz-dispatch-delay.patch) is **test-only**. It adds 20 ms before
  dispatch obtains the mutex, making that scheduling gap reproducible. The final tool does
  not contain this delay. Apply it equally to unpatched and fixed variants for the regression.

## Build locally

Work in an ignored directory. Fetch both exact revisions and their pinned recursive submodules.
Keep unpatched tools before applying patches so compiler/environment differences cannot be
mistaken for fixes. All paths below are absolute; run Docker commands from the Tactus repo.

For sfizz (host CMake/compiler):

```bash
cmake -S "$SFIZZ_SOURCE" -B "$SFIZZ_BUILD" -DCMAKE_BUILD_TYPE=Release \
  -DSFIZZ_JACK=OFF -DSFIZZ_SHARED=OFF -DSFIZZ_RENDER=ON
cmake --build "$SFIZZ_BUILD" --target sfizz_render -j 8
# Preserve library/bin/sfizz_render, apply the patch, then build again.
git -C "$SFIZZ_SOURCE" apply "$REPO/experiments/deterministic-instruments/sfizz-loading-barrier.patch"
cmake --build "$SFIZZ_BUILD" --target sfizz_render -j 8
```

For OB-Xf, build the dependency image from the included Dockerfile, then use the same source,
compiler and build directory before/after the patch. Keep the VST3 bundle basename `OB-Xf.vst3`;
put variants in different parent directories. Pass an absolute bundle path to Pedalboard.

```bash
docker build -t tactus-instrument-builder:20260928 experiments/deterministic-instruments
docker run --rm --network none \
  --mount "type=bind,src=$OBXF_SOURCE,dst=/src" \
  --mount "type=bind,src=$OBXF_BUILD,dst=/build" \
  -w /src -e GIT_DIR=/src/.git -e CMAKE_BUILD_PARALLEL_LEVEL=8 \
  tactus-instrument-builder:20260928 sh -c \
  'git config --global --add safe.directory /src && cmake -S /src -B /build -DCMAKE_BUILD_TYPE=Release -DCOPY_PLUGIN_AFTER_BUILD=OFF && cmake --build /build --target OB-Xf_VST3 -j 8'
```

Copy `OB-Xf_artefacts/Release/VST3/OB-Xf.vst3` to an unpatched location. Apply the OB-Xf patch to
`$OBXF_SOURCE`, repeat the build command, and copy the patched bundle to a second location.
No install step is needed. Actual outputs for this trial are in ignored
`dogfood/2026-09-28-deterministic-instruments/tools/` (`fixed/OB-Xf.vst3`, `sfizz-fixed`).

## Run the probes

Use the repository's `uv` environment. All probes invoke real synthesis.

```bash
uv run python experiments/deterministic-instruments/probe_obxf.py \
  --plugin "$PLUGIN" --out "$OUTPUT.npy"
# Repeat in fresh processes; compare arrays/hashes. Optional arms: --zero-slop, --c-seed 42.

uv run python experiments/deterministic-instruments/probe_sfizz.py \
  --tool "$SFIZZ" --sfz "$PROGRAM" --midi "$MIDI" --out "$RESULTS" \
  --cpu 0 --runs 10 --reference "$HEALTHY_WAV" --require-identical
```

Choose an allowed CPU on your machine. The SFZ probe can compare to a healthy reference,
not merely to its own first run: consistently truncated output must still fail the test.
For the recorded fixture use the prior handoff's Karoryfer `07-darkblack_ghost.sfz` and generated
MIDI. Material/tool files remain private and are not included in Git.

The full-song probe uses the previous handoff's source/environment image and a fresh pool,
copies the patched native tools, and executes three new network-disabled containers. It calls
`tactus run` without `--reuse`, verifies each WAV against its manifest, and checks receipts.

```bash
uv run python experiments/deterministic-instruments/probe_full_song.py \
  --pool "$SOURCE_POOL" --plugin "$FIXED_PLUGIN" --sfizz "$FIXED_SFIZZ" \
  --out "$NEW_TRIAL_DIRECTORY" --reference "$PRIOR_HOST_BASELINE"
```

Its default image is `tactus-clean-handoff:20260928`, built by the preceding experiment.
The pool-copy optimization uses hardlinks and requires the same filesystem. Original input
blobs are immutable in this probe; no negative corruption test is performed on those links.

No new Tactus API, installed-tool replacement or upstream publication is part of this trial.
