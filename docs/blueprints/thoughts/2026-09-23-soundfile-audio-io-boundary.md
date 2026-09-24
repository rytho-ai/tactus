# Audio file boundary: use SoundFile, verify the integration

> 2026-09-23 · Working decision for Tactus. Adopt SoundFile as the default audio-file I/O tool; no separate library-selection probe is required now. Integration checks below are proposed acceptance criteria, not completed experiment results.

## Decision

Use SoundFile to read supported audio files into NumPy arrays and write arrays back to audio files. Ordinary Python/NumPy owns creative processing; SoundFile owns file encoding and decoding through libsndfile. Tactus should not implement its own general audio-file decoder or introduce a new authoring model for this boundary.

This is a practical adoption decision based on a direct fit with SoundFile's documented purpose, not a claim that experiments proved it superior to every alternative. Its API supports NumPy arrays, sample-rate reporting, explicit output subtypes, and partial or block-based reads. See the [official documentation](https://python-soundfile.readthedocs.io/en/latest/).

## Responsibility boundary

- SoundFile handles supported audio-file reads and writes.
- Python/NumPy/SciPy handles creative transformations and signal processing.
- Pedalboard plus helpers remains the current effect-processing and VST-hosting direction.
- Tactus adds only the validation and data-layout adaptation that these boundaries need.

Reading and writing do not perform sample-rate conversion. Changing the sample-rate value passed to a writer does not resample the audio; a production must explicitly resolve differing rates.

SoundFile's two-dimensional array layout is `(samples, channels)`. Tactus must make its internal layout and conversions at other tool boundaries explicit. This decision does not select a new canonical internal layout or authorize a layout migration. Likewise, float dtype and output encoding must be deliberate rather than accidental defaults.

## Verification proportional to the risk

Do not open another broad selection probe just to establish that SoundFile can read audio files. Add small integration tests when implementing or extending this boundary:

1. **Mono and stereo:** verify sample count, channel count, array layout, and the chosen dtype, including consistent handling of mono data.
2. **Sample rate:** preserve the input rate and explicitly handle a mismatch with the production rate; never silently relabel samples.
3. **Tool handoff:** exercise file read → NumPy processing → Pedalboard → file write. Check channel identity, expected length, and sample values using an identity or otherwise predictable effect configuration.
4. **Output encoding:** verify floating-point and PCM output with encoding-appropriate tolerances. Include out-of-range values so clipping, rejection, or another explicitly selected policy is visible rather than accidental.

These tests establish that Tactus uses the library correctly. They are not a new DSP benchmark, an audition-quality assessment, or evidence that all file formats and metadata are preserved.

## Revisit trigger

Revisit the boundary when a real workflow requires an unsupported format, metadata preservation, large-file behavior, or performance that the current integration cannot provide. Test that concrete requirement before adding another decoder or a broader abstraction. Those cases do not need speculative probes now.

The current conclusion is: adopt SoundFile for audio-file I/O and verify the handoffs, without turning a routine dependency choice into another research project.
