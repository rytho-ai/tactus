---
name: plugin
description: Create, modify and validate native audio effects or MIDI instruments with JUCE/C++, producing VST3, Audio Unit or Standalone builds. Use for authoring an audio plugin, its parameters, editor, state or build, and adopting a chosen build in a Tactus work. For using an existing plugin or operating its DAW instance, use compose or daw.
---

# Author an audio plugin

Build the sound tool the user wants as an independent JUCE project. Its DSP, MIDI
behavior, controls and editor are authored C++; no Tactus processor registration or
fixed sound architecture is required. Music works choose a built release and settings.

For designing or adapting a sound algorithm, use [dsp](../dsp/SKILL.md) for signal
contracts, synthesis/processing mechanisms and revealing numerical checks. Implement
the chosen algorithm as realtime-safe C++ in the JUCE project; its Python examples
are optional references, and a Python prototype is optional. Check native behavior
against the intended signal/state contract and hear it in the music work.

Read [Authoring and hosting](../references/plugin-authoring.md) for the relevant build,
parameter/state, host or release step. It links official JUCE APIs and explains how to
read the exact selected source rather than copying a stale tutorial.

When the plugin has a human-facing editor, read [Plugin design](../references/plugin-design.md)
to shape its visual identity and interaction around the musical task, then
[JUCE editors](../references/plugin-ui.md) for implementation and actual-host checks.
The optional [parameter control](assets/editor-example/ParameterControl.h) and
[gain editor example](assets/editor-example/Processor.cpp) demonstrate mechanisms to
adapt, not a required style or processor architecture. A generic editor is useful for
debugging; evaluate a delivered custom editor through real tasks, screenshots and sound.

## Develop independently

- Start with the intended audible behavior and target host/format/platform. Keep the
  plugin's source, dependencies, tests and Git history in its own project. A repo per
  plugin is optional; coupling it to one song's files or Tactus imports is unnecessary.
- Reuse an existing JUCE project, the official examples, or copy the minimal
  [CMakeLists.txt](assets/CMakeLists.txt) and [Processor.cpp](assets/Processor.cpp).
  The starter is an audio-transparent effect, with no musical parameters or editor.
  Change its identity before sharing/installing; choose instrument flags, buses, DSP,
  GUI and dependencies for the actual request. The starter does not constrain them.
- Fix the JUCE revision and record compiler/platform/architecture. Select Python and
  native host architectures explicitly when testing; a Python lock alone does not
  select a compatible interpreter. Build into a development directory and freeze
  completed releases separately. Never rebuild a bundle still loaded by a host.

## Make the host contract deliberate

- Give parameters stable IDs, units, ranges, text parsing and useful defaults. Preserve
  old IDs/order; append new parameters and provide explicit old-state migration. AU
  version hints have their own ordering rules. Validate old automation, not just presets.
- Keep audio/MIDI processing independent of editor lifetime. Allocate processing memory
  in preparation, handle changing/empty blocks and supported buses, and keep file I/O,
  locks and GUI work outside the audio callback. Choose smoothing, latency and tails
  to match the sound. APVTS state copy/replace uses locks even though it is thread-safe.
- Use JUCE attachments for standard controls when useful; custom editors and original
  DSP remain ordinary options. Host parameter readback can settle after the setter call.

## Build, verify and revise

Use the selected JUCE revision's CMake tools. On macOS verify the finished bundle's
signature after resources/manifest generation, before installation. A development
signature is not distribution/notarization verification.

Check meaningful signals and MIDI against the intended behavior, then load the actual
binary in the target host. Use SDK validation and pluginval where available; keep logs
and report which checks ran. Inspect the actual current editor, exercise parameter
changes, save/reopen and test old-project migration when revising a released plugin.
Use owned test projects; preserve existing unsaved work. [Daw](../daw/SKILL.md) routes
native REAPER/Live operations and isolation guidance. A passing validator alone does
not prove sound quality, realtime performance or compatibility with every DAW.

## Adopt a build in music

Keep an immutable release containing the named plugin bundle and its build/source
identity. Pin the release with a tree material ref; resolve the bundle and declare it
with `tool()` before loading through the existing host. `tool()` records bytes but
does not by itself pin a mutable path. Preserve required external sample/preset data
and explicit settings. Missing builds must not silently select another sound.

Use [compose](../compose/SKILL.md) for a separate music work, `tactus init` / `run` and
receipted auditions. Existing Pedalboard plus `fx.process` or `fx.render_instrument`
is a hosting route, not a required DSP choice. A native DAW can host the same release.
Upgrade a music work explicitly, and compare old pinned outputs before claiming they
are preserved. Deliver native builds/source separately from the work's audio/receipt.
