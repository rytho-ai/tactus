# Learn from existing audio-plugin interfaces

Use these studies to choose an interaction and visual direction for a particular
instrument or effect. They complement [Plugin design](plugin-design.md) and
[JUCE editors](plugin-ui.md); they are not templates, an approved-product list or a
requirement to implement every feature below.

Sources reviewed 2026-10-19: official product pages, manuals and published interface
images. These are documented/visible behaviors, not hands-on usability tests. Product
versions and imagery differ; a historical manual is evidence for its pictured version.
The trade-offs and applications below are design interpretations, not measured rankings.

## Study a task, a gesture and a visual relationship

Find references close to the intended task and a contrasting approach. Inspect actual
images as well as manuals: text can explain a gesture without showing proportion,
hierarchy or material character. Record what the player does, how the interface makes
the result visible, what remains secondary, and what does not transfer to this tool.

Avoid a palette-only reference pass. A warm background and three identical knobs do
not by themselves make a playable instrument. Conversely, detailed hardware controls,
illustration, a large expressive display or many simultaneous parameters can be right
when they serve the chosen task. Uniform minimalism is not the acceptance criterion.

## Directly shape a sound relationship

### FabFilter Timeless 3 — edit the echoes where they are drawn

The [delay display](https://www.fabfilter.com/help/timeless/using/delaydisplay)
shows input and left/right repeats. Dragging a bar horizontally changes delay time;
vertical movement changes feedback. Numeric controls remain available.

Transfer: give a delay's spacing and decay a useful visual scale, and consider making
that relationship editable. Cost: graph gestures need clear targets and precise,
keyboard-accessible alternatives. Do not imply independent taps if the DSP only has
one delay time and feedback amount.

### Goodhertz Midside — let geometry explain the signal

The [manual and interface](https://goodhertz.com/midside/manual/) place Mid and Side in
paired regions, use sliders/readouts with embedded level information, and separate
advanced controls. A stereo display reports the channel relationship.

Transfer: paired controls and meaningful direction can explain more than repeated
rotary knobs. Choose a fader for level or a centered slider for a relationship when
appropriate. Cost: compact symbols still need labels, units and readable focus states.

### oeksound Soothe3 — distinguish amount from the frequency target

The [official interface](https://oeksound.com/plugins/soothe3/) gives Depth a prominent
control next to a much larger frequency graph; smaller controls sit below it. The
graph separates a target curve from the displayed reduction shape.

Transfer: allocate space to the actual decision, not equally to every parameter.
Cost: a model preview, editable target and measured response are different things;
their visual distinction must survive animation and bypass. Do not claim a live
analyzer from a static drawing. The former Soothe2 product URL now redirects here.

## Establish a recognizable instrument or piece of equipment

### Soundtoys Decapitator — make the main act unmistakable

The [version-5 manual](https://www.soundtoys.com/wp-content/uploads/Decapitator-Manual.pdf)
shows a large Drive control, an attitude meter, smaller tone/output/mix controls and
five style switches. Material, labeling and control proportions share a hardware idiom.

Transfer: give the sound's defining action visual weight. A coherent physical surface
can reinforce that identity. Cost: do not inherit tiny legends or ambiguous switches
just to reproduce hardware; distinct saturation algorithms do not justify adding fake
style switches to a simpler processor.

### Valhalla VintageVerb — a restrained surface with meaningful character

The [official product documentation](https://valhalladsp.com/shop/reverb/valhalla-vintage-verb/)
describes algorithm Mode and era Color choices; the interface palette changes with the
selected era. These are sound choices as well as visual identity.

Transfer: strong typography, grouping and purposeful color can carry a focused effect
without elaborate rendering. Cost: color should reinforce a labeled state, not be its
only identifier. Do not add an era selector solely to obtain alternate themes.

### Aberrant DSP SketchCassette II — illustration belongs to the sound world

The [manual](https://aberrantdsp.com/wp-content/uploads/2020/11/SketchCassette-II-User-Manual.pdf)
shows a hand-drawn cassette panel, an Age slider and grouped Wow/Flutter, Dropouts and
noise controls. The drawing, lettering and worn-tape vocabulary form one visual world.

Transfer: a plugin may be playful, imperfect or illustrative while its controls remain
legible and organized. Cost: texture must not obscure active states or precise input;
the cassette metaphor fits degradation, not every instrument.

### u-he Diva — density can serve an expert task

The [version-1.4.8 guide](https://u-he.com/downloads/manuals/plugins/diva/Diva-user-guide.pdf)
shows oscillator, mixer, filter and envelope regions, plus lower-panel tabs for other
tasks. The hardware-inspired modules expose many related parameters together.

Transfer: preserve useful signal-flow grouping and simultaneous access when comparison
matters. Cost: blindly hiding controls to achieve minimalism can slow patch design;
blindly reproducing a large synthesizer overwhelms a small three-parameter instrument.

## Support exploration, performance and a deeper editing layer

### Sonic Charge Synplant 2 — the metaphor changes the creative action

The [official overview](https://soniccharge.com/synplant) presents growing branches as
sound exploration and a separate DNA editor for detailed synthesis settings. The plant
is central to how variants are created, not just a logo above conventional controls.

Transfer: original interfaces can expose a meaningful creative space without showing
every implementation parameter first. Cost: unfamiliar metaphors need orientation,
recoverability and a way to preserve a discovered sound. Do not invent exploration
dimensions unsupported by the engine.

### Arturia Pigments — performing and constructing need different emphasis

The [official overview and gallery](https://www.arturia.com/products/software-instruments/pigments/overview)
show a reactive Play view, macro controls, and deeper synthesis/modulation views with
color-coded relationships. A modulation source's color continues into its assignments.

Transfer: performance can emphasize a few expressive controls while editing exposes
the underlying structure. Cost: another view must save real navigation effort; a small
instrument may need only one well-composed page. Moving graphics need informative
behavior, an appropriate refresh cost and a quiet/disabled mode when appropriate.

### Minimal Audio Rift — choose the depth of control deliberately

The [official product page](https://www.minimal.audio/products/rift/) documents Play and
Advanced views and drag-and-drop modulation. This study uses the documented workflow;
it does not claim native interaction or visual inspection of both views.

Transfer: progressive disclosure can separate immediate sound exploration from detailed
routing/modulation. Cost: primary changes must not require repeated trips between views;
one level of controls may be sufficient for a focused effect.

### Baby Audio Transit 2 — turn a musical movement into a performable control

The [official manual](https://babyaud.io/docs/transit-2-manual) describes a Macro that
moves linked effect parameters through visible start/end ranges, alongside editable
effect modules. The photographed interface gives this Macro a clearly dominant role.

Transfer: many parameter changes can become one expressive gesture when that mapping
is actually part of the sound design. Cost: users need to inspect direction and range;
a macro is a creative mapping, not a generic UI shortcut to add automatically.

### XLN Audio XO — organize discovery around similarity and recovery

The [official interface guide](https://support.xlnaudio.com/hc/en-us/articles/16920363887645-Interface-Overview)
describes a similarity-organized sample space, history, neighboring samples and hot-swap
audition inside the playing beat, with OK/Cancel for the trial.

Transfer: exploration needs orientation, immediate context and a return path, not only
a randomize button. Cost: a meaningful similarity space requires actual sample data;
decorative dots do not provide that behavior.

## Turn a reference into an original editor

Write a compact design brief in the independent plugin project:

- The musical action that leads, and why it deserves the largest control or display.
- The relationship that determines grouping: signal flow, coupled parameters, time,
  frequency, performance or a deliberate exploration space.
- The control form for each job, its value display and precise/reset/keyboard route.
- The visual world: typography, material or flat treatment, spacing, contrast, states
  and one recognizable idea tied to the sound.
- What is borrowed as a principle and what is intentionally different from references.
- The actual host size and tasks used to check whether the design works.

Review the result beside the relevant references at comparable displayed sizes. Check
which element leads, whether values remain readable, whether graphical space earns its
cost, and whether an unfamiliar musician could make and reverse the intended change.
Then build and inspect the native editor. Neither reference screenshots nor an HTML
direction study establish that the delivered JUCE interface behaves correctly.

Keep third-party artwork and screenshots out of the reusable starter and native
distribution. Link primary sources; any local comparison captures remain research
evidence. Author the plugin's own graphics and control behavior.
