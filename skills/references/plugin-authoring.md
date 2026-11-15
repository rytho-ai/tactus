# Native audio plugin authoring and hosting

Use [plugin](../plugin/SKILL.md) to make the tool; use a separate
music work to choose how it is played or applied. A JUCE project produces standard
native plugins. Tactus does not need their C++ classes or a plugin-specific adapter.

For a human-facing editor, read [Plugin design](plugin-design.md) to decide the
visual/interaction direction and [JUCE editors](plugin-ui.md) for implementation,
optional worked controls and actual-host verification. Keep these decisions with the
plugin project so later revisions can preserve or deliberately change its language.

## Find the authoritative API

Start with the project's chosen JUCE checkout/version, not a remembered tutorial:

```sh
git -C /path/to/JUCE rev-parse HEAD
rg -n 'class AudioProcessor|processBlock' /path/to/JUCE/modules/juce_audio_processors*
rg -n 'ParameterID|versionHint' /path/to/JUCE/modules/juce_audio_processors*
```

Search narrowly, then read the matching declaration/implementation. Module paths can
change across JUCE releases. The checkout's `docs/CMake API.md` and `examples/CMake/`
own its build interfaces; `examples/Plugins/` contains editable native examples.
When downloading/searching docs, use a bounded local copy of the relevant official
page or the exact Git revision, and record the source/version. Do not paste an entire
API manual into the work. The online master docs may be newer than the selected code.

Official entry points:

- [CMake API](https://github.com/juce-framework/JUCE/blob/master/docs/CMake%20API.md):
  `juce_add_plugin`, format flags, manifest/copy steps and build examples.
- [AudioProcessor](https://docs.juce.com/master/classjuce_1_1AudioProcessor.html):
  buses, variable/zero-length blocks, MIDI timestamps, latency, tails and editor lifetime.
- [APVTS](https://docs.juce.com/master/classjuce_1_1AudioProcessorValueTreeState.html):
  parameter layouts, raw atomic values, attachments and state copy/replace.
- [Parameter attributes](https://docs.juce.com/master/classjuce_1_1AudioParameterFloatAttributes.html)
  and [parameter identity/version hints](https://docs.juce.com/master/classjuce_1_1AudioProcessorParameter.html).
- [SmoothedValue](https://docs.juce.com/master/classjuce_1_1SmoothedValue.html),
  [DSP introduction](https://juce.com/tutorials/tutorial_dsp_introduction/) and the
  [official course](https://juce.com/learn/course/): optional mechanisms and examples.

These are references, not a list of allowed APIs. Use native C++/JUCE freely.

## Independent build

The minimal [CMake](../plugin/assets/CMakeLists.txt) and
[processor](../plugin/assets/Processor.cpp) are copied together into the
new plugin project. The effect passes mono/stereo through unchanged and has no editor,
musical parameters or dependency on Tactus. Replace its product/company/bundle codes
before installing or sharing. Choose four-character manufacturer/plugin codes and
retain the released identity. Keep source and dependency revision in that project's Git;
ignore build products and preserve chosen releases separately.

Example from the new project, with an already pinned JUCE checkout:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DJUCE_SOURCE_DIR=/path/to/JUCE
cmake --build build --config Release --target AudioPlugin_VST3 --parallel 4
```

For macOS select the host architecture explicitly at configuration; compiler defaults
can target a different architecture. For example, use
`-DCMAKE_OSX_ARCHITECTURES=arm64`. A universal build uses the quoted argument
`"-DCMAKE_OSX_ARCHITECTURES=arm64;x86_64"`. Host process, native plugin and Python host
must have compatible architectures. Inspect `file`/`lipo -archs` on binaries and
`platform.machine()` / `sys.executable` in the actual Python environment.

For the music work, `uv run --python /path/to/compatible/python ...` selects a known
interpreter; record/pin that environment for a fresh checkout. `uv.lock` alone does
not choose Python's architecture. Check `tactus --project WORK doctor` and the installed
package metadata before assuming a dependency works on another interpreter/platform.

The starter builds VST3/Standalone, installs neither, and adds a final macOS ad-hoc
signature/strict verification after JUCE's manifest generation. Complete resources
before final signing; use explicit install/copy only after unloading owned instances.
Inspect the output bundle, not just an executable within it. Other formats and signing
requirements follow the selected platform's official tools. Adding a format requires
testing it; development signing does not establish distribution/notarization readiness.

For a MIDI instrument, set `IS_SYNTH TRUE`, `NEEDS_MIDI_INPUT TRUE`, declare appropriate
output buses and implement MIDI/audio behavior. CMake flags and processor methods must
agree. A Standalone build is a convenient test route but cannot establish all DAW
transport, automation or routing behavior. Custom editors remain optional authored code.

## Parameters, state and processing

Parameter identity, host presentation and sound are separate decisions:

- Preserve IDs and existing index order; append new parameters. For AU, set new
  `ParameterID` version hints above all earlier hints, following the AU-specific rules
  in the selected JUCE version. A version hint is not a universal VST3 migration fix.
- Set units and meaningful text/parser conversions on the parameter itself, for
  example `AudioParameterFloatAttributes().withLabel("ms")` and the corresponding
  value/string functions. GUI-only labels do not teach a host how to present values.
  Inspect what each host actually exposes before setting physical or normalized values.
- APVTS `ParameterLayout` and Slider/Button/ComboBox attachments can connect standard
  controls to host automation. A custom interaction should notify the host and bracket
  user gestures appropriately. The processor must work while its editor is closed.
- Save the complete chosen state. For a newer build reading old state, initialize
  missing new parameters deliberately, including when loading into an already modified
  instance; do not accidentally retain a stale current value. Validate the state schema.
- Allocate buffers in `prepareToPlay`, read current parameters efficiently, handle
  supported bus layouts and MIDI's sample offsets. Avoid allocation/file I/O/locks/GUI
  work in `processBlock`. APVTS `copyState`/`replaceState` are not realtime-safe.
- Choose smoothing and interpolation to match the intended sound. Frequency/volume can
  use appropriate `SmoothedValue` modes; multiplicative smoothing cannot reach zero.
  Report processing latency to the host and align dry/wet paths when required. Report
  the intended tail; silence, reset and continuing a block stream are different cases.

DSP algorithms, voice allocation, oversampling, modulation, presets and editor design
belong to the plugin. Existing JUCE DSP or work-local implementations are optional
building blocks. Do not insert a default sound chain into the music host.

## Verify in the actual host

Use revealing inputs: impulse/tones for an effect, note timing/velocity/note-off and
polyphony for an instrument. Exercise silence, reset, representative sample rates,
changing block sizes and relevant parameter extremes. Test the sonic intent separately
from format compliance. For supported buses see the [official bus-layout guide](https://juce.com/tutorials/tutorial_audio_bus_layouts/).

When matching a reference effect, save the exact plugin build, host, input and
parameter readback with each comparison. Some Python hosts allow assigning an
unknown attribute without changing a plugin parameter; an output comparison can
then silently measure bypass. Check the inspected host parameter key and its
normalized or physical readback after every setting. Sweep center frequencies as
well as gain, width and sample rate: a filter that matches at 1 kHz can diverge
near Nyquist. Compare phase/waveform and a representative music input alongside
magnitude; broad spectral bands can hide a narrower response mismatch. Treat a
published DSP formula as a candidate model, not evidence of the reference's internals.

For polyphonic instruments, hold a note while repeatedly playing short notes: free
voices must behave according to the intended allocation policy, and an allocator must
not accidentally steal a held note just because its circular index wraps. Test the
documented capacity and deliberate stealing behavior separately. Distinguish MIDI
All Sound Off (immediate stop) from All Notes Off (normal release), including channels.
For a clean harmonic oscillator, also test high notes/sample rates where a generated
partial crosses Nyquist; a correct fundamental does not establish alias-free synthesis.
Deliberate aliasing and unconventional voice behavior remain valid sound choices when
they are intentional, communicated and tested.
JUCE's [Synthesiser](https://docs.juce.com/master/classjuce_1_1Synthesiser.html) and
[SynthesiserVoice](https://docs.juce.com/master/classjuce_1_1SynthesiserVoice.html)
provide conventional voice/MIDI mechanisms to adapt when useful; a custom engine is
also valid. Read the pinned implementation's allocation and MIDI policy before reuse.

Run the VST3 SDK validator when targeting VST3. [Pluginval](https://github.com/Tracktion/pluginval)
adds parameter/state/editor/host tests and supports CLI use:

```sh
/path/to/pluginval --strictness-level 5 /path/to/Plugin.vst3
```

Use the installed tool's help for headless/GUI options; do not report skipped editor
checks as GUI coverage. AU can be checked with Apple's `auval`; JUCE's AudioPluginHost
is another development host. Record versions, commands, pass/fail logs and actual scope.

Use [daw](../daw/SKILL.md) for native DAW testing. Work in an owned test project/config,
identify the loaded path/build, inspect the current editor, change a parameter and
read back after host settling. Save/reopen, verify the chosen values and envelope points,
then repeat with the newer build and old project when claiming migration. Automation at
the current cursor may override a saved temporary knob value. Never replace a mapped
library in place: unload/close owned hosts, install an immutable completed build and
reopen. If a host caches the old identity, report it rather than call it a tested upgrade.
An unscanned VST3 may need an owned search folder and rescan before native loading.
Check the actual loaded identity: a DAW catalog can resolve a requested path to another
scanned copy with the same plugin ID. Declare/verify that actual bundle against the
chosen release. Scope MIDI-instrument parameter reads: virtual CC controls can greatly
outnumber the authored sound controls.

## Fixed releases and music works

Freeze the named native bundle inside a release directory alongside the source/build
identity (source commit/hash, JUCE revision, platform/architecture and build commands).
Include necessary sample data or an explicit way to obtain it. Preserve the `.vst3`
child name when importing a release tree; the materialized tree root itself is a hash
directory, not a filename with the plugin's extension. Keep the pool available separately
from Git: a ref is an identity, not a backup of its bytes.

Import the selected release with `tactus material add /path/to/release`. In the music
work, save that returned ref as source, then resolve and declare the bundle:

```python
from pedalboard import load_plugin
from tactus.inputs import material, tool

# RELEASE_REF and BUNDLE_NAME are the work's chosen literal ref and relative filename.
release = material(RELEASE_REF)
plugin = load_plugin(str(tool(str(release / BUNDLE_NAME))))
```

`tool()` takes a string, records the actual bundle hash and returns its path; it does
not lock a mutable development path. `material()` verifies the fixed tree. Preserve
settings as explicit source values or a pinned native state/preset appropriate to the
host; plugin state can refer to additional external assets. Never silently choose a
different release when the specified one is absent.

Read [packages](packages.md#pedalboard-and-instrument-hosts) and inspect the loaded
plugin with `fx.describe` before configuring it. `fx.set_param` uses host-exposed units
and values; verify actual readback. Use its inspected Python key (a `Level` parameter
with dB units can appear as `level_db`), not a name guessed from the GUI. Copy host
wrapper values to plain scalars when saving JSON observations. If an owned plugin exposes normalized values only,
record the explicit mapping in the work or improve its metadata, without pretending the
host exposes physical units. Delayed host display strings may require a separate read.

- Effects: `fx.process(plugin, audio, rate, tail_seconds=...)` resets independent clips
  and preserves Tactus layout; `fx.process_automated` supports authored block controls.
- MIDI instruments: `fx.render_instrument(plugin, messages, duration=..., sample_rate=...)`
  takes absolute-second MIDI events and returns frames-first audio. Choose warm-up and
  buffer size for the actual instrument; declared warm-up does not replace note-tail tests.
- DAW use: load the same chosen native build through that DAW and retain its project/
  state using the host reference. A Python-host render does not prove DAW equivalence.

Use [compose](../compose/SKILL.md) for `tactus init`, versioned music source, `run` and
receipt delivery. Keep release refs/settings in that work. Upgrade deliberately; rebuild
old pinned works with matching runtime/environment and compare actual outputs before
claiming preservation. Some plugins are nondeterministic: preserve the accepted audio.
