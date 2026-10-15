---
name: resources
description: Find and download external audio for Tactus works, including samples, loops, recordings and sound effects. Use when sourcing material, checking free download and reuse conditions, or maintaining resource lists. Delivers actual audio files with provenance; plugin installers and streaming previews do not satisfy an audio request.
---

# Resources

Turn a musical need into usable local audio with its source and use conditions preserved.
The current catalog covers audio files; VST instruments and effects can be added later as
a separate catalog, with their own platform, installation and compatibility evidence.

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

## Maintain the catalogs

Add sources to the audio reference with the exact tested item, official source and license
links, checked date, download path and validation scope. Keep price, access, rights and
file validity separate. Move stale or blocked entries out of verified recommendations;
do not expand a single success into a site-wide claim. Future VST entries should live in
their own reference and include OS/architecture, format, price/license, account/installer
requirements and actual host-test status; an empty VST list is not needed today.
