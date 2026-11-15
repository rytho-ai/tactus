# Design an audio tool people can see, understand and play

Use this reference when making or revising a plugin's human-facing interface. Read
[JUCE editors](plugin-ui.md) when translating decisions into controls and host behavior.
Keep the design brief and evidence with the independent plugin project. These are
decision aids, not a mandatory aesthetic, parameter limit or production sequence.

## Start with an audible task

Describe who is using the tool, the sound they want to change, and the few actions
they will repeat. For example: shorten a drum's tail while preserving its attack;
place echoes between notes; explore unstable textures and retain a useful discovery.
An engineering control and a musical control may describe the same mechanism
differently. Pick names that communicate the actual behavior to the intended user.

Choose whether the tool favors precision, performance, exploration or a mixture.
Identify the primary action, related controls and settings that can appear on demand.
Group by audible relationship or signal flow, rather than C++ member order. A large
synth can legitimately expose many controls; a focused effect can expose a few.
Do not conceal an essential task behind an unexplained icon or shortcut.

Before drawing, decide how a user will find the primary control, hear its effect,
inspect the current value, compare an alternative and recover their earlier setting.
Optional A/B, undo, presets, randomization and macros earn their place through this
task. Do not add them to every plugin just because another product has them.

## Give this tool a visual identity

Select a coherent direction appropriate to its sound and audience: precise measurement,
physical equipment, playful exploration, restrained typography, or an original metaphor.
Look at reference interfaces for the problem each solves; retain the reasoning, not
another product's artwork or complete layout. A hardware metaphor can teach a familiar
workflow; a graph or novel interaction can make a different relationship tangible.

Use the [interface studies](plugin-interface-studies.md) for task-matched examples and
contrasting approaches. Inspect real interfaces as well as documented gestures before
settling the composition. Explain what transfers and what does not. Compare the result
at a similar displayed size: control priority, typography and useful graphical space
matter as much as palette. The optional gain editor demonstrates parameter wiring;
its repeated dial/value/reset layout is not the visual target for every plugin.

Keep the working brief concrete:

- Primary action and the visual element that leads to it.
- Control grouping and what can remain secondary without slowing that action.
- Typeface/weights, readable value/label hierarchy, spacing and density.
- Palette and contrast; meaningful emphasis, selection, focus and disabled states.
- The distinctive visual idea and why it belongs to this sound tool.
- Minimum/normal/large editor sizes and the target host/display scale.

Own these values together in the plugin's local theme/layout code and reuse them.
Do not require every plugin to share Tactus branding, dark mode, knobs, panels or
round corners. Test long labels, large/small values and all interactive states.
Whitespace and contrast should communicate relationships, and the name/logo should
leave room for the work. Avoid turning numeric readouts into illegible decoration.

## Make controls predictable and expressive

- Match the control to the job: a toggle for a true binary choice, a menu/segmented
  control for named modes, a continuous control for a range, a graph/XY area when
  the relationship itself benefits from direct manipulation.
- Offer both broad exploration and precise adjustment. Continuous controls usually
  benefit from a documented fine modifier, direct numeric entry and a discoverable
  reset. Pick gestures consistently; double-click conventions differ across products.
- Define useful units, text parsing, step size and perceptual scaling on the parameter.
  A frequency control's middle need not be half its Hz range. Display time units,
  bipolar centers and sync/free modes truthfully. Audit the DSP's actual mapping.
- Reset to the parameter's factory default, not its value when the editor opened.
  Opening an editor must not reset the sound or fight existing automation.
- Make active, bypassed, selected and unavailable states distinct. Supplement color
  with labels, shape or position. Explain why a control is unavailable when relevant.
- Support keyboard focus, meaningful reading/navigation order and accessible names,
  units and values. Test text-entry commit/cancel and return of focus to the host;
  plugin controls should not unexpectedly consume transport shortcuts.
- Provide immediate control feedback. Choose smoothing for the sound separately from
  visual animation; do not delay the actual parameter to make a knob animation pretty.

## Draw what helps the ear

A display should answer a question: where is the echo, how long is the envelope,
which signal modulates which target, how much gain reduction is occurring?
Distinguish an analytic model/preview from measured audio and from the parameter's
base value versus its modulation. Label axes/units and relevant unavailable/no-signal
states. A static illustration must not masquerade as a running spectrum or meter.
Position axis labels using the same coordinate mapping as the plotted values, and
identify reference input/dry marks separately from processed events when relevant.

Add direct manipulation only with discoverable targets, appropriate hit areas,
precise alternatives and an accessible route to the same important parameters.
Let expensive graphics slow down or stop when hidden; measure CPU/repaint behavior.
Some instruments benefit from expressive artwork or motion. The design should still
remain legible, responsive and useful while someone listens and adjusts repeatedly.

## Iterate through tasks in the real editor

Start with a working interface, inspect the loaded build and perform representative
tasks. Screenshots establish appearance; actual input and parameter/audio readback
establish interaction. An HTML mockup or a passing headless validator proves neither
the native editor's final rendering nor its host behavior.

Useful tasks to adapt:

1. Find the primary control and make an audible intended change without reading code.
2. Enter an exact physical value, fine-adjust it, cancel an edit and reset it.
3. Change the parameter from host automation/MIDI and verify the editor follows.
4. Reopen the editor/project and verify sound, control values and necessary UI state.
5. Use keyboard navigation and the target platform's accessibility inspector/reader.
6. Repeat the main task at normal, compact and large/scaled sizes in the actual host.
7. Compare the result with matched settings/levels where that serves the sound judgement.

Record confusion, missed clicks, accidental jumps, unreadable text, unnecessary steps
and audible interruptions. Fix the cause and repeat the affected task. Keep original
captures/failed trials as evidence; do not replace them with a favorable mockup.
Judge visual coherence and musical usefulness explicitly, identifying who listened
or tested. Self-review and numerical checks have different limits from user testing.
Never report a subjective quality percentage as a measured agent success rate.

Listening services are optional aids, not a required paid acceptance step. Deliver
receipted audio and identify whether a person or an audio-capable model actually
listened; playing a file locally or measuring it does not establish that the agent
heard it. If listening evidence is unavailable or unreliable, keep that judgement open
while reporting the independently verified engineering and interaction results.

Treat model listening descriptions as fallible observations. Bind them to the exact
audio, inspect execution evidence, and check claimed processing causes against the
actual routing. A model missing a parameter contrast does not prove the control is
broken; a spectral difference does not prove that contrast is perceptually useful.
Do not retune a sound solely because a model invents compression, modulation or other
processing absent from the source. Preserve disagreement and use a revealing audition
or human feedback when the quality decision depends on it.

## Reference approaches

These sources describe different successful design intentions, not one universal skin:

- [FabFilter Pro-Q display/workflow](https://www.fabfilter.com/help/pro-q/using/eqdisplay):
  manipulate the frequency relationship directly, with numeric alternatives.
- [Valhalla's minimalism](https://valhalladsp.com/2017/05/25/minimalism-in-plugin-guis/):
  focused controls and a distinctive two-dimensional graphic language.
- [Goodhertz interaction manual](https://goodhertz.com/midside/manual/): precise entry,
  primary/advanced controls, keyboard focus and selective visualization.
- [EchoBoy manual](https://www.soundtoys.com/wp-content/uploads/EchoBoy-Manual.pdf):
  familiar equipment controls and expandable mode-specific editing.
- [Hive](https://u-he.com/products/hive/): modular grouping, modulation relationships,
  drag assignment and multiple performance controls.
- [Synplant](https://soniccharge.com/synplant): a visual metaphor that changes how sounds
  are explored, with deeper parameter editing available.
- [ADC inclusive-design workshop](https://midi.org/wp-content/uploads/2025/03/ADC24-inclusive-design-workshop.pdf):
  legibility, meaningful scales/labels, alternate input and actual musician involvement.
- [Knobs and Nodes research](https://mro.massey.ac.nz/items/f630372b-5871-4864-b4ab-aefc49e4e1fc):
  an eight-participant exploratory study; useful for iteration methods, not a universal
  claim that nodes outperform knobs or flat design outperforms physical metaphors.
