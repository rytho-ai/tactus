# Downloadable audio sources

Use this when selecting audio to acquire. The two tables contain **13 sources** with
specific zero-payment downloads checked on **2026-10-15**, without accounts, email
submission or paid trials. Every audio file in the listed downloaded packs, and each
listed individual file, passed full decoding; the scope is **887 audio files**. Recheck
the selected item's current page and license. This is technical verification, not a
listening evaluation or a guarantee about other files on the same service. Sources that
failed or did not deliver original audio are separated below.

## Creator libraries and sample packs

| Source / creator | What to retrieve | Rights and access | Verified scope |
|---|---|---|---|
| [VCSL — Sam Gossner and contributors](https://github.com/sgossner/VCSL) | Original WAVs in instrument folders; open file → Raw/download | [CC0 at the tested revision](https://github.com/sgossner/VCSL/blob/c1ea7bcc3c7309650ab0da9d15c9cd1fbc4a4c7e/LICENSE) | Kalimba `MBira3_pluck_Main_B4_k23_50_100_rr2.wav`, 318,232 bytes; full decode, 48 kHz stereo, 1.105 s |
| [VSCO 2 CE — Versilian / Sam Gossner](https://github.com/sgossner/VSCO-2-CE) | Individual orchestral WAVs; preserve folder layout for a whole instrument | [CC0](https://github.com/sgossner/VSCO-2-CE/blob/440300901dfe9275fd84e0b7763af1f8443ae62e/LICENSE); also preserve [Readme.txt](https://github.com/sgossner/VSCO-2-CE/blob/440300901dfe9275fd84e0b7763af1f8443ae62e/Readme.txt), which requests credit and no direct resale of unchanged samples (author requests, not CC0 conditions) | `VlnEns_Pizz_D5_v1_rr2.wav`, 77,634 bytes, 0.440 s; independent skill trial also fetched `LLVln_ArcoVib_A4_f.wav`, 2,488,526 bytes, 14.107 s. Both fully decoded, 44.1 kHz stereo |
| [Salamander — Alexander Holm](https://github.com/sfzinstruments/SalamanderGrandPiano) | `Samples/` FLACs, or whole SFZ instrument | [CC BY 3.0 at the tested revision](https://github.com/sfzinstruments/SalamanderGrandPiano/blob/3382bf9496bba2486f5ab0de55a264d1dfc38404/LICENSE); retain attribution | `A4v1.flac`, 1,302,933 bytes; full decode, 48 kHz stereo, 13.205 s; not a full-instrument playback test |
| [FreePats Upright Piano KW small](https://freepats.zenvoid.org/Piano/acoustic-grand-piano.html) | Select KW **SFZ + FLAC** small package on page | CC0 stated for this instrument on source page | 3,092,715-byte 7z; integrity and all **26 FLACs** pass full decode; all SFZ sample references resolve. WAV edition uses a compression combination some extractors cannot handle |
| [AVL Drumkits — Glen MacArthur](https://www.bandshed.net/avldrumkits/) | Blonde Bop **SFZ** ZIP containing WAVs, rather than a plugin binary | Page states CC BY-SA 3.0 with an author exception for music-use attribution; preserve the actual terms for redistribution | 18,894,875-byte ZIP, all CRCs and **135 WAVs** pass full decode; all SFZ sample references resolve. Instrument host playback not tested |
| [SampleRadar 808 weight](https://www.musicradar.com/music-tech/samples/sampleradar-105-free-808-weight-samples) | Pack pages link to downloadable ZIPs; [808 weight ZIP](https://cdn.mos.musicradar.com/audio/samples/musicradar-808-weight-samples.zip) | Pack page permits music use without credit; no redistribution as samples | 60,144,839-byte ZIP, all CRCs and **105 audio files** pass full decode; AppleDouble metadata excluded from the audio count |

For a small, reproducible original-audio download, this [VSCO violin WAV](https://raw.githubusercontent.com/sgossner/VSCO-2-CE/440300901dfe9275fd84e0b7763af1f8443ae62e/Strings/Violin%20Section/Pizz/VlnEns_Pizz_D5_v1_rr2.wav)
is pinned to a repository revision. SHA-256:
`e9ac949d9d0e90cd98e00b6ace9e66ea42352920b6de744ae8ae1816cd0e20ee`.
Its [license at that revision](https://github.com/sgossner/VSCO-2-CE/blob/440300901dfe9275fd84e0b7763af1f8443ae62e/LICENSE)
travels with the provenance. Prefer a sample suited to the music over repeatedly choosing
this small test file.

## Recordings and sound effects

| Source / item | Acquisition and conditions | Verified scope |
|---|---|---|
| [Incompetech — Kevin MacLeod, The Britons](https://incompetech.com/music/royalty-free/index.html?isrc=USUAN2600004) | Use the track's MP3 download; CC BY 4.0 attribution option is free; paid license is a separate option | Complete MP3, 12,271,315 bytes, 306.730 s; full decode and finite-sample check pass |
| [Kenney Interface Sounds](https://kenney.nl/assets/interface-sounds) | Download → Continue without donating → ZIP; CC0 | 834,536-byte ZIP; all CRCs and **100 OGG files** pass full decode |
| [OpenGameArt Retro 512](https://opengameart.org/content/512-sound-effects-8-bit-style) | Download the attached collection; this item's license is CC0, not a site-wide license | 20,582,855-byte ZIP; all CRCs and **512 audio files** pass full decode |
| [SoundBible Service Bell — Daniel Simion](https://soundbible.com/2218-Service-Bell-Help.html) | Page's WAV download; Attribution 3.0, preserve creator credit | 277,060-byte WAV fully decoded, 44.1 kHz stereo, 1.570 s |
| [Mixkit rain sound effects](https://mixkit.co/free-sound-effects/rain/) | Actual download button gives WAV; [SFX license](https://mixkit.co/license/modal/sfxFree/) allows audio end products, including commercial work; no raw/stock redistribution or rights-management registration. This is not the music license | Item `2393.wav`, 2,646,730 bytes, full decode, 44.1 kHz stereo, 15 s |
| [NPS rain](https://www.nps.gov/subjects/sound/sounds-rain.htm) | Download Original MP3; this [sound gallery](https://www.nps.gov/subjects/sound/gallery.htm) states public domain and requests credit | RainDEPO.mp3, 81,986 bytes, full decode, 44.1 kHz mono; ffprobe reports 4.971 s |
| [Citizen DJ Edison collection](https://citizen-dj.labs.loc.gov/loc-edison/use/) | Collection offers samples for new music; preserve the selected recording metadata and collection use statement | “Till the boys come home” official 6.711 s WAV sample, 1,288,556 bytes; full decode and finite-sample check pass. Complete sample, not complete song |

## Known damaged pack: excluded from recommendations

[Legowelt Drumnibus](https://legowelt.org/samples/) was obtained free through the official
WeTransfer button (34,294,264-byte ZIP). All archive CRCs pass, but only **228 of 229 WAVs**
pass strict full decoding. `FX/FX_Timpio.wav` ends with an incomplete PCM packet: FFmpeg
reports one byte where at least three are needed. The pack SHA-256 is
`459e22076c5f1665e0b12287b8a5ff99feeabbc637960fcfa36d9a7b29ca9d05`.
The author permits free download and use in productions; this does not fix the file defect
or grant CC0. Do not present this version of the whole pack as fully verified. Retain the
original and report the failure; any selected usable files need their own evidence.

## Personal Splice-like projects: separate from verified audio

- [Sonura](https://app.sonurastudio.com/samples): community library exists, with Free Sounds,
  search and download buttons. Tested download requires sign-in; no original audio acquired.
  Its [terms §4.2](https://sonurastudio.com/terms/) dedicate publicly shared samples to CC0.
  Recheck account conditions; generation credits do not establish community download limits.
- [Bangerly](https://bangerly.com/): community samples and packs; [help](https://bangerly.com/help)
  describes five weekly free credits. The free Lo-fi pack routes to sign-in; the tested
  single-sample download routes to `/signin` and a 404. No original audio acquired.
- [Splicedd](https://github.com/ascpixi/splicedd) and [Splicerr](https://github.com/Robert-K/splicerr):
  third-party Splice frontends. Their preview-to-WAV path does not establish original,
  licensed sample acquisition; [Splice terms](https://splice.com/terms) restrict previews to
  auditioning in the service. Do not recommend them as verified free audio sources.
- [OpenLoop](https://github.com/moddroid94/openloop): self-hosted management of the user's
  existing samples, not a supplied public audio library.

Account-gated sites may still offer free audio, but remain unverified until an authorized
download succeeds. Keep those results separate instead of filling the deliverable with
landing-page links.
