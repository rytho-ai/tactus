# Implement and verify a JUCE editor

Read [Plugin design](plugin-design.md) for the human task and visual decisions, and
[authoring](plugin-authoring.md) for build/state/release requirements. Inspect the
selected JUCE revision's headers and examples before adapting an API shown here.

## Choose the rendering route for this project

Native `Component`, `Graphics`, `Slider`, `Button` and `LookAndFeel` support original
interfaces; JUCE's default appearance is not a visual limit. Keep the plugin's theme
and reusable controls local to its project. A polished editor need not be photorealistic
or animated. A generic processor editor is a useful parameter/debug comparison.

JUCE also supports embedded web interfaces through `WebBrowserComponent` and native
parameter/event bridges. HTML/CSS/JS can shorten visual iteration and reuse web tooling;
test platform-specific engines, packaged/offline assets, focus, lifecycle, parameter
mapping and resource usage. A desktop-browser preview is only a preview. Keep audio
processing in its realtime-safe native processor; do not route audio-rate work through
JavaScript messages. Choose native, WebView or another justified renderer explicitly.

- [Official WebView overview](https://juce.com/blog/juce-8-feature-overview-webview-uis/)
- [LookAndFeel](https://docs.juce.com/master/classjuce_1_1LookAndFeel.html)
- [Component](https://docs.juce.com/master/classjuce_1_1Component.html)

## Keep one parameter contract

Own IDs, physical ranges, default values, units, text and parser conversions in the
processor parameter. Editors and host automation must operate on the same contract.
Use an appropriate `NormalisableRange` for continuous parameters and choices/bools
for discrete values. Test round-trip conversion and meaningful midpoint/extreme values.

Use APVTS `SliderAttachment` / `ButtonAttachment` / `ComboBoxAttachment`, or the
underlying `ParameterAttachment` for custom interactions. In the pinned JUCE 9 example,
`SliderParameterAttachment` supplies range, text/parser, factory double-click default
and host gesture notifications. Inspect the selected implementation before overriding
these: an editor-side formatter can otherwise disagree with the DAW. Set any deliberate
display customization after creating the attachment and retain parameter semantics.

The optional [ParameterControl](../plugin/assets/editor-example/ParameterControl.h)
shows a label, numeric/rotary control and explicit reset wired to a real parameter.
The [gain example](../plugin/assets/editor-example/Processor.cpp) demonstrates its
lifetime and an editor layout; adapt both rather than adopt their colors or DSP by default.

To try this optional example, copy the parent asset's `CMakeLists.txt` and the two
files in `editor-example/` into a separate project directory, placing all three
side-by-side. Configure/build using the existing authoring commands and change product
identity before installing it outside that isolated test. Its Level parameter changes
gain with smoothing; it is a control/editor example, not the transparent starter.

Declare controls before attachments so attachments are destroyed first. Keep the
parameter/processor alive throughout. Give each editor its own controls/attachments;
opening a second editor must not invalidate the first. Do not load presets, initialize
current values or push factory defaults from an editor constructor. Query current state.

For a custom gesture, begin once on user interaction, send values with host notification,
and end once on completion/cancellation. Host playback updates the control without
creating another user gesture. Preserve IDs/order and the old-project migration rules.
UI undo and host undo are different mechanisms; test the behavior you promise.
In a REAPER fixture built entirely through scripts, establish its initial undo state
before testing real UI gestures. An empty history without that baseline is inconclusive;
do not wrap the target UI action in a scripted undo block to manufacture coverage.

- [Slider attachment](https://docs.juce.com/master/classjuce_1_1AudioProcessorValueTreeState_1_1SliderAttachment.html)
- [ParameterAttachment](https://docs.juce.com/master/classjuce_1_1ParameterAttachment.html)
- [Slider](https://docs.juce.com/master/classjuce_1_1Slider.html)

## Layout, text and accessibility

Use `resized()` with local bounds, FlexBox/Grid or a coherent proportional layout.
Choose a readable minimum size and resize limits. Test actual host resize/scale behavior;
an arbitrary narrow window cannot be fixed merely by shrinking every font and hit area.
Make primary labels/value fields real accessible components, not only painted text.
Keep suffixes, signs and long parameter names from clipping at tested sizes.

Provide titles/descriptions/help and a logical focus order. Standard controls preserve
many input behaviors while `LookAndFeel` changes rendering. Fully custom graph/knob
components owe keyboard/value access and an `AccessibilityHandler` as appropriate.
Test keyboard commit/cancel/reset, screen reader values, focus visibility and transport
shortcut behavior in the target host. A drawn focus ring alone is not keyboard support.
Host policy can also close a floating editor on Escape after cancelling text entry;
verify the cancelled value survives reopening and report the observed focus behavior.

Use `getDefaultValue()` with the parameter's conversion when resetting, not the current
value captured on open. Keep reset/input gestures discoverable. Provide fine adjustment
and an exact text alternative for drag-sensitive parameters. Explain modifiers locally.

- [JUCE accessibility guide](https://github.com/juce-framework/JUCE/blob/master/docs/Accessibility.md)
- [AudioProcessorEditor](https://docs.juce.com/master/classjuce_1_1AudioProcessorEditor.html)
- [Melatonin Inspector](https://github.com/sudara/melatonin_inspector): optional native
  component/property/accessibility inspection; runtime tweaks still need source changes.

## Graphics and lifetime

Read parameter atomics for inexpensive previews; label them as a response/trajectory
preview when they do not measure actual audio. Transfer measured peaks, envelopes or
spectra from the processor with bounded lock-free/atomic storage appropriate to the
data. Do not call GUI methods, allocate drawing data, take locks or repaint from the
audio callback. APVTS state copies are not realtime-safe.

Choose a useful UI update rate and repaint only affected regions. Cache stable artwork
when measurements justify it. Avoid recomputing expensive graphics in every `paint()`.
Stop timers/work when appropriate while hidden. Repeated open/close must clean up
timers, listeners and pending callbacks; avoid capturing a dead editor in async lambdas.
Detach a component's custom `LookAndFeel` before destroying the look object.

## Exercise the actual editor

Build and sign the completed bundle. Identify the loaded path/build before evaluating;
a DAW may resolve the same plugin ID to an older scanned copy. Follow [daw](../daw/SKILL.md)
for owned test projects and native readback. Preserve unrelated unsaved user work.

Use real mouse/keyboard/accessibility input for promised gestures, then check the
native parameter/state and, when relevant, resulting audio. Calling a host setter
tests host-to-editor synchronization; it does not prove that dragging/typing works.
A component unit test can catch mapping/layout bugs but does not replace a native pass.

Capture the actual normal/compact/large editor. Inspect label/value clipping, focus,
active/bypass/disabled states, primary task, contrast and useful feedback. Repeat edits,
automation, editor close/reopen and project save/reopen. Check idle and moving UI load
with active audio. Preserve a failure and its corrected result when iterating.

Run the applicable validator with editor checks enabled where the environment supports
them. State skipped GUI checks explicitly. Do not report a mockup, a headless pass or a
saved PNG from another build as coverage for the current editor. Record known limits
such as untested platforms, display scales, accessibility clients and musical listening.
