# Sampled piano renderer probe

> 2026-09-16 · This evidence feeds the pending Tactus Code decision back to Paul. This is a renderer-only blind A/B, not a claim that sampled instruments alone make an arrangement good.

## Question and pre-registered rule

Does replacing the current General MIDI piano renderer with a continuous, multi-velocity sampled-instrument render materially improve the same code-authored MIDI performance? If the listener clearly prefers the sampled result and the renderer is deterministic, SFZ becomes the free sampled-instrument baseline. If the difference is not clear, the route is not worth pursuing and the next test should use a commercial VST3 piano.

## Method

A disposable eight-bar, 120 BPM D-major/B-minor piano performance was written once as a Standard MIDI file. It contains broken chords, a lead phrase, three velocity bands, slight timing offsets, and sustain-pedal messages. Every musical event was held fixed.

Condition A rendered that MIDI at 48 kHz through `sfizz_render` and VS Chamber Orchestra: Community Edition's `UprightPiano.sfz` with its 243 MB sample directory. Condition B rendered the same MIDI at 48 kHz through FluidSynth and the host-installed FluidR3 General MIDI SoundFont. The listener heard the two files as unlabeled A/B conditions before the mapping was disclosed.

## Observations

- The listener reported that A was "much better" and that it made the material "much more pleasant to hear."
- A was the SFZ sampled upright piano; B was the FluidR3 General MIDI piano.
- `sfizz_render` produced byte-identical WAV output on two independent renders of the same MIDI and SFZ input.
- The SFZ condition rendered successfully as one continuous performance. It did not reuse the earlier Tactus Code approach of independently bouncing fixed-velocity notes and assembling them afterward.
- This is evidence about piano timbre and performance continuity only. It does not validate the full pop-ballad arrangement, other instrument families, vocals, or mixing decisions.

## Verdict

The free SFZ route passes as the deterministic sampled-instrument baseline for code-first music work. General MIDI SoundFonts are acceptable as a functional fallback but are not a valid basis for judging whether Python-authored music can sound good. Future renderer work should preserve continuous MIDI performance data (velocity, controls, timing, and articulation) and route it to an instrument library; it should not reduce performance to isolated fixed-velocity note bounces. A commercial VST3 such as Pianoteq remains a later quality ceiling test, not the immediate dependency.
