---
name: resources
description: Find and acquire external audio and VST instruments or effects for Tactus works. Use when sourcing samples, loops or recordings, choosing well-reviewed free plugins, checking download and use conditions, or maintaining resource catalogs. Verify audio files and plugin host operation separately, preserving provenance.
---

# Resources

Turn a musical need into usable local audio or an available plugin, with its source and
use conditions preserved. Use the audio workflow for files and the
[plugin workflow](#find-and-verify-vst-plugins) for instruments/effects.

## Find and acquire audio

1. **Choose for the request.** Infer the needed sound, file type and intended use from the
   work. For free requests, require a zero-price acquisition without a paid trial; note
   account, credit or email requirements separately. When the user asks for individual
   creators, prioritize those authors. Read [audio sources](references/audio-sources.md)
   for tested starting points, then search current primary pages for a closer match.
   A catalog entry is a lead, not a permanent guarantee.
2. **Check the selected item.** Follow its official page to the actual download and its
   license. Record whether attribution, commercial use, modification or redistribution
   is restricted; distinguish a recording's rights from its composition's rights.
   “Royalty-free,” free software and a free preview do not establish free reusable audio.
   Unclear use conditions remain unclear even if the bytes are obtainable.
3. **Download the offered audio.** Fetch the full file through the normal download flow
   into a new local destination. A browser is useful for dynamic download buttons. Use
   available authorized credentials when needed; if none are available, record the gate
   and continue with another suitable source. Never count an HTML login page, API response,
   installer, demo mix or converted streaming preview as the requested original asset.
   A full MP3 can be the publisher's actual deliverable; converting it to WAV does not
   make it lossless source audio. Keep downloads outside `render`.
4. **Verify what arrived.** Record bytes and SHA-256, inspect the actual container/header
   for login pages or server-error text mixed into the payload, and fully decode
   selected audio with an available decoder such as FFmpeg or SoundFile. Require a successful
   decode with no reported decoding errors; an exit code of zero alone can miss a malformed
   final PCM packet or skip an HTML error prefix. If another decoder reports a problem,
   retain that finding instead of declaring the file clean. Check positive duration,
   sample rate and channel count. For archives, check integrity and paths before
   extraction. A fully verified pack requires full decoding of every audio member;
   if only selected members were checked, label the pack partially verified and name that
   scope. Keep relative paths for SFZ/sample folders.
   HTTP 200, an extension, metadata inspection or a successful HEAD request alone is not
   audio validation. Separate technical validity from listening and musical suitability.
5. **Deliver files and evidence.** Link the actual local audio, not just the source website
   or ZIP. Keep the archive too when useful. Preserve a small adjacent JSON or Markdown
   record: title/creator, source page, download URL, date, cost/access conditions, license
   URL and attribution, file path/hash/bytes, audio metadata and checks performed. Redact
   credentials and expiring signed-query secrets. Clearly separate verified files from
   gated, failed or unchecked candidates. A test of one item proves only that item.

## Use the selected material

For an existing Tactus work, pin the selected file or sample folder with
`tactus material add FILE_OR_DIR` and preserve its provenance alongside the work's source.
Read [Inputs](../references/runtime.md#inputs) for pool scope, file/tree refs and loading;
the material hash proves content identity, not permission to use it. Acquisition alone
does not need a new work or a render receipt.

When the task continues into making music, follow [compose](../compose/SKILL.md), use the
returned material refs, and deliver the resulting audio from a Tactus run. Native plugin
binaries belong to the separate `tool()` workflow described in Inputs; downloading one
does not deliver samples or demonstrate that it runs on the user's platform.

## Find and verify VST plugins

1. **Choose for a job and host.** Read [VST sources](references/vst-sources.md) for a small
   reviewed shortlist. Establish OS, CPU architecture, supported plugin format and desired
   role. Explain the sonic/workflow reason for a recommendation and cite independent
   hands-on reviews with their dates; distinguish historical reputation from tests of the
   current build. For free requests, select the full free edition, recording account or
   activation requirements and separating paid upgrades, trials and promotions.
2. **Acquire the exact build.** Follow official stable downloads, retain version, URL,
   bytes/hash, license and required factory data. Inspect archive integrity and paths;
   extract to an isolated location when possible and preserve existing installations.
   Confirm the binary's format/architecture, not just the download page's platform list.
   Keep permission to make music separate from rights to redistribute binaries or presets.
3. **Verify at the available depth.** Record download, extraction, host loading, audio
   processing and GUI/preset checks separately. A plugin that enumerates parameters may
   still fail to sound. Use the work's locked host, declare bundles and external data with
   `tool("/absolute/path")`, and follow [compose](../compose/SKILL.md) for a receipted
   `tactus run` test. For instruments compare MIDI note output with a no-note control;
   for effects compare processed audio with dry input and check the intended response or
   tail. Inspect finite/nonempty output, warnings and the actual parameter values; read
   [plugin helpers](../references/runtime.md#helpers-from-tactus-import-fx) for units,
   warm-up and layouts. Isolate native-plugin tests in separate processes. Retain errors
   and label partial results; a Linux VST3 pass does not certify AU, other OS builds,
   sibling plugins, every preset or musical quality.
4. **Hand off what was verified.** Give the local bundle/package and its provenance,
   supported host conditions and any receipted test audio. Describe installation or data
   placement still needed. Keep unverified candidates out of the tested shortlist;
   plugin acquisition is a separate deliverable from the audio-file catalog.

## Maintain the catalogs

Maintain [audio sources](references/audio-sources.md) and [VST sources](references/vst-sources.md)
separately. Each entry names its tested item/build, official source and license, checked
date, acquisition path and verification scope. Plugin entries also retain platform,
format, factory-data requirements and the evidence behind their recommendation. Keep
price, access, rights and validity separate. Move stale or blocked entries out of verified
recommendations; do not expand a single success into a site-wide compatibility claim.
