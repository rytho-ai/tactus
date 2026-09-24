# Sampling affordance: fresh-Agent A/B/C probe

> 2026-09-24 · Evidence for the pending Tactus musical-affordance decision. The initial 12-attempt technical probe still lacks a blind judgment; a separate replicated real-loop blind probe is complete below.

## Question and decision rule

Does exposing musical practice knowledge or an optional sampling API help an Agent create or revise a musical piece beyond ordinary Python? Condition A received Python/audio libraries; B received the same environment plus optional sampling operation cards; C received B's cards plus an optional `chop`/`play_slices` module. The source, task, model, export contract, and runtime were otherwise held fixed. B needs a musically useful change over A, not just more named techniques. C needs an additional benefit over B, not merely a shorter source file or more API calls.

## Method

Twelve fresh, independent `gpt-5.5` executor-strong attempts used `fork_turns=none`: three conditions × two briefs × two replicates. The briefs were a four-bar source-only sketch and a revision of an existing four-bar source, with the first two bars required to remain sample-identical. Every attempt used the same local-only 40-second, 48 kHz prepared source, 90 BPM, and a 512,000-frame stereo PCM24 export. Agents owned separate scratch directories and were told not to inspect other attempts. The optional API was disposable probe code, not Tactus product code.

The source's provenance/license was not established, so neither source nor rendered audio was committed or published. A local-only, anonymous listening page contains four matched triplets. Listening copies use only a fixed gain for RMS matching; revision clips contain only the changed second half.

## Technical observations

All 12 attempts produced valid, finite, non-silent WAVs with the specified format, duration, and peak bound. All six revisions preserved the first half exactly and changed the second half. None of the four C-condition source files referenced the optional API module. Thus this run tests the effect of making an API passively available, but does not compare outcomes of API use against non-use. Agents in A also authored slicing, reversal, and timing transformations without the operation cards; the existence of those techniques alone is not evidence that B or C improved the music.

## Pending verdict

Musical usefulness, preference, and whether B's operation cards broadened relevant exploration await Paul's blind listening. Do not promote the optional module to Tactus core, or claim it harms creativity, from technical validity alone. After ratings, decode the private mapping and report matched comparisons. The sample is small, uses one source and one model, and does not establish cross-project Agent behavior.

## Separate real-loop fixture pilot

After the first listening interface proved hard to judge musically, a separate, smaller pilot replaced the demo-song fixture with two real Rytho Library loops: `SO_JC_90_melodic_loop_almond_Bb` (eight-bar melodic source) and `KAELIN_ELLIS_90_drum_loop_chestpuncher` (four-bar shared drum context). The library originals were not modified. Three fresh `gpt-5.5` agents received identical converted melodic-source bytes and the same four-bar output contract. The drum loop was added only after their renders, at the same fixed gain for all three; dry and drum-backed versions were both available for blind listening. All three renders passed format, length, finite-value, non-silence, and peak checks.

The pre-registered *fixture* rule required a blind listener to identify a concrete musical difference and a meaningful preference, rather than only a loudness difference. Paul preferred anonymous version 3, describing better groove, more variation, and more variation in the ending. The private mapping identifies version 3 as condition A (ordinary Python/audio libraries). This passes the limited fixture-adequacy rule: the real-loop outputs were musically distinguishable to this listener. It does **not** establish that A outperforms B or C: this was one listener and one trial, the Python environment was not perfectly matched across agents, and the C-condition agent did not use the optional API. The controlled replicated follow-up is recorded below; its strict B-over-A and C-over-B verdicts were inconclusive.

This evidence feeds back into the pending Tactus affordance decision; it does not itself select a sampling API. The derived audio and mapping remain local-only in the disposable probe directory because the sample-pack distribution rights were not established.

## Replicated real-loop blind probe: six fresh `gpt-6-luna/max` agents

The follow-up held the real-loop source bytes, four-bar task, `uv run --project tactus --no-sync python` environment, output contract, shared drum context, and listening-level treatment constant. Two independent fresh agents were assigned to each condition: A received only ordinary Python/audio libraries, B also received optional sampling-operation cards, and C received B's cards plus the optional `chop`/`play_slices` module. All six rendered 512,000-frame, 48 kHz stereo PCM24 WAVs that passed finite-value, non-silence, and peak checks. Both C agents actually called `chop` and `play_slices`; this run can therefore test use of the helper, unlike the earlier technical probe and fixture pilot.

The verdict rule was registered before any trial: B would provide directional evidence over A only by beating A for musical reasons in *both* replicates; C would provide directional evidence over B only by beating B in *both* replicates while using the helper both times. Split outcomes, ties, or loudness-only reasons would be inconclusive. The one-source, two-replicate, one-listener design cannot establish general behavior.

Paul's blind rankings and reasons were:

| Replicate | Blind ranking | Decoded ranking | Musical reason |
| --- | --- | --- | --- |
| 1 | version 1 > versions 2 = 3 | C > A = B | Version 1 had a more fragmented, sampled feel. |
| 2 | version 1 > version 3 > version 2 | B > C > A | Version 1 had a fragmented sampling groove; version 3's small late repetition gave it more development than version 2's smooth continuation. |

The strict verdict is **inconclusive for both incremental claims**. B did not beat A in both replicates (one tie, one win); C did not beat B in both (one win, one loss). A weaker observation is that the top-ranked version in each replicate had been given sampling-operation guidance (C once, B once), and the listener consistently valued fragmented groove. This is a useful direction for further tests, not evidence that the helper itself improved the music or that ordinary Python cannot produce the same effect. In particular, the second replicate's winner was B, which had no helper. The next decision should separate the value of practice vocabulary from the value of an implementation API; do not promote `chop`/`play_slices` to Tactus core from this run.

The six outputs, listening page, and private condition mapping are local-only disposable artifacts under `/tmp/tactus-loop-affordance-replicated-MnIgS5`. Library originals and Tactus product code were unchanged; derived audio was not committed or published because sample-pack redistribution rights were not established.

## Design interpretation: affordance is creative vocabulary, not a required API

Paul's takeaway is to make sampling visible as a creative mode, while treating an exported helper API as only one way to carry it out. An Agent may already know how to slice an array; the product opportunity is to make practices such as chopping, retriggering, rearranging slices, and varying a phrase ending salient when they are relevant to the material. The two preferred versions in the replicated probe suggest that this vocabulary is worth exploring. They do not prove that the guidance is necessary or that a helper caused the preference: an earlier ordinary-Python pilot was also preferred, and the two replicated winners came from different guided conditions.

Keep three responsibilities separate:

- **Creative affordance:** show possible musical moves, the situations in which they are useful, and small examples. These are invitations, not a prescribed arrangement or style.
- **Implementation choice:** let the Agent use ordinary Python/NumPy or an optional helper such as `chop`/`play_slices`. A helper earns its place by removing real friction or errors, not merely by naming a practice.
- **Production contract:** Tactus still handles the non-creative invariants around time, assets, rendering, validation, and replay regardless of how the music was authored.

This is a product direction rather than a settled API decision: expose musical possibilities without making one representation mandatory. The next evaluation should test whether practice-oriented guidance reliably changes musically useful exploration, separately from whether a particular helper improves execution.
