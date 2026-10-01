# Ways of making music with material

Synthesis is one way to make a sound; recorded material and your own renders open others.
Each technique below is an invitation with the situation it suits. Combine them with
synthesis in any proportion.

| Technique | What you do | Reach for it when | Uses |
|---|---|---|---|
| Sample as instrument | Play one recorded note or sound at many pitches, with your own envelope and a sustain loop | A synthesized voice sounds plain; you want the timbre of a real piano, voice, bell or found sound carrying a melody or chords | [`devices.sampler`](devices.md) |
| One-shot kit | Build drums and accents from single recorded hits, tuned, shaped and layered | Percussion needs weight and realism | [`devices.pads`](devices.md), `devices.steps` |
| Chop and rearrange | Slice a loop or phrase and trigger the slices in a new order and rhythm: repeat one, skip some, change the ending | A source has character you want to keep while making the phrase your own | `pads.slices`, `pads.play` with `choke` |
| Loop as a bed, then vary | Run a loop at its tempo and edit it across the form: filter, drop out, retrigger its first beat, let its tail ring | You need texture or harmony that evolves with the sections | `pads.play`, [`dsp`](dsp.md) |
| Resample your own output | Render a part, then treat the render as new material: pitch it, reverse it, slice it, granulate it | Transitions, fills and textures should belong to this piece | Any device on your own arrays |
| Texture from anything | Stretch, granulate or freeze a short recording into pads, risers and atmospheres | A section needs air or motion without a new melodic idea | [`synth.grains`](synth.md), `dsp.spectral` |
| Layer recorded with synthesized | Put a sample's attack on a synthesized body, or a synthesized sub under a recorded bass | Each source lacks what the other has | `sampler`, `synth`, `dsp` |
| Step-sequenced pattern | Write rhythm as a grid with accents and swing | A part is a repeating figure best seen as steps | `devices.steps`, `timing.euclid` |

## Working with material you cannot hear

Measure a sample before trusting its name: its real pitch (see root in
[Devices](devices.md)), whether the pitch drifts, where the steady part starts, its tempo
and length in beats. Unpitched material suits pads and textures; steady pitched material
suits the sampler.

Tempo and key: fit material to the piece by repitching (length and pitch change together),
by time-stretching with `pytimestretch` (pitch kept), or by choosing the piece's tempo and
key to fit the material. Each is a creative choice.
