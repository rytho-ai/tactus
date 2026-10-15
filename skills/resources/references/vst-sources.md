# Free VST instruments and effects

Use this when choosing a well-reviewed plugin for a Tactus work. This is a small
selection by musical purpose, not a popularity ranking. Checked **2026-10-15**:
all five products below were obtained from official downloads at zero cost without
accounts, activation or paid trials. Exact Linux x86_64 VST3 builds were loaded and
rendered through Tactus with Pedalboard **0.9.26**, Python **3.12.11**, glibc **2.39**,
at **44.1 and 48 kHz stereo**. Windows/macOS support below is vendor information,
not our host-test result. Recheck current releases and terms before acquisition.

## Choose by purpose

| Job | Choice | Why it is worth considering | Verified scope and limits |
|---|---|---|---|
| Broad synthesis: pads, leads, bass, modulation | [Surge XT 1.3.4](https://surge-synthesizer.github.io/) | MusicRadar's [hands-on synthesis tutorial](https://www.musicradar.com/how-to/fantastic-free-synths-surge-xt), 2022-12-01, favorably assesses its breadth and modulation. Strong first general-purpose synth; a substantial interface to learn | Instrument VST3 responds to four MIDI notes; no-note control is silent. Full package and factory data acquired; initial sound tested, not every preset. Separate Surge XT Effects bundle untested |
| FM electric pianos, bells, bass; DX7 workflows | [Dexed 1.0.1](https://asb2m10.github.io/dexed/) | MusicRadar's [DX7/FM programming tutorial](https://www.musicradar.com/news/fantastic-free-synths-dexed), updated 2023-02-02, gives a positive practical assessment. Complements Surge for six-operator FM; programming FM takes practice | Instrument VST3 responds to MIDI; no-note control is silent. Initial embedded sound tested; hardware SysEx transfer and arbitrary imported banks untested |
| Dynamic EQ and frequency-selective compression | [TDR Nova 2.2.3](https://www.tokyodawn.net/tdr-nova/) | MusicRadar's [dedicated hands-on article](https://www.musicradar.com/music-tech/plugins/fantastic-free-plugins-and-how-to-use-them-tdr-nova), 2025-06-01, recommends its accessible EQ/dynamics workflow. Standard edition has four dynamic bands; paid **Nova GE** is separate | Linux VST3 loaded; band-2 EQ changes the signal, and enabling its dynamics produces a different output from static EQ. External sidechain and all other modes untested |
| Tape saturation, wow/flutter and lo-fi color | [CHOW Tape Model 2.11.4](https://chowdsp.com/products.html) | [BPB's firsthand review](https://bedroomproducersblog.com/2020/07/14/chow-tape-model/), updated 2021-01-23, praises its tape coloration and degradation controls. Useful for coloration; high oversampling costs CPU | VST3 processes tonal transients with a nonzero dry/wet difference, finite output and no clipping. Tape drive/saturation checked, not every degradation mode. Keep input below unity as advised by the [manual](https://chowdsp.com/manuals/ChowTapeManual.pdf) |
| Conventional hall reverb on Linux | [Dragonfly Hall Reverb 3.2.10](https://michaelwillis.github.io/dragonfly-reverb/) | [LANDR's hands-on roundup](https://blog.landr.com/free-reverb-vst-plugins/), 2026-03-13, praises natural tails. It also reports Early Reflections instability on M2/macOS Sonoma; that is a different variant/host | **Hall only:** VST3 processing and tail checks pass, with DPF component/connection-point cleanup warnings. Do not call it warning-free. Room, Plate and Early Reflections were downloaded but not host-tested |

Reviews establish attributed opinions about usefulness, often on older versions; they
do not certify the exact builds above. Our ten short render checks establish MIDI/audio
operation, finite samples, correct lengths and zero clipped output samples. They are not
a listening comparison, GUI test, exhaustive preset audition or long-session stability
test. Instrument fixtures use fixed output attenuation, not automatic normalization.

## Official builds and acquisition

Download and retain the full package plus its notices. Extraction here was local; no
global plugin folders were overwritten and no package installation scripts were run.
SHA-256 values are artifact fingerprints; a matching self-computed hash is not by itself
publisher authentication.

| Product | Exact tested official artifact | Bytes | SHA-256 |
|---|---|---:|---|
| Surge XT 1.3.4 | [Stable release](https://github.com/surge-synthesizer/releases-xt/releases/tag/1.3.4), full Linux amd64 `.deb`, including factory data | 223,339,140 | `a6e55064487f624147d515b9ae5fc79a568b69746675b2083abde628ca7bb151` |
| Dexed 1.0.1 | [Release](https://github.com/asb2m10/dexed/releases/tag/v1.0.1), Linux ZIP | 7,725,160 | `2bac3d0c4237e8c22c4274b6d5b59fe6329fcae72864f81b5830393eff354fc1` |
| TDR Nova 2.2.3 | [Linux archive](https://www.tokyodawn.net/labs/Nova/2.2.3/TDR%20Nova.tar.gz) | 9,379,224 | `00e93b7084f23dd992a65faac31af8aa62d0e02a665a06f09d456c70f6ad353f` |
| CHOW Tape Model 2.11.4 | [Linux x64 DEB](https://github.com/jatinchowdhury18/AnalogTapeModel/releases/download/v2.11.4/ChowTapeModel-Linux-x64-2.11.4.deb) | 5,112,948 | `71aaae1c454ac83ac16b248d4cc99c12bf6d11452a87376fcb6b1e79060e3a5c` |
| Dragonfly Reverb 3.2.10 | [Linux x86_64 archive](https://github.com/michaelwillis/dragonfly-reverb/releases/download/3.2.10/dragonfly-reverb-3.2.10-linux-x86_64.tar.xz) | 2,267,368 | `59f1593120de82e31dd194e2ab1536af14fec2b3ec6ec45abf6d9c8ac02ef430` |

All archives passed full decompression/integrity and safe-path checks; extracted VST3
shared libraries are ELF x86-64. Dexed's current [GitHub asset SHA-256](https://api.github.com/repos/asb2m10/dexed/releases/assets/374347239)
matches the download, but its separate legacy MD5 manifest does not. The Linux asset was
updated after the release; retain that discrepancy rather than claiming every published
checksum passed. Nova's detached signature was not verified in this check.

## Platforms, data and rights

- **Surge XT:** official Windows x86/x64, macOS Intel/Apple Silicon universal and Linux
  x64 releases include VST3; AU/CLAP availability is platform-dependent. The stable
  releases live in `releases-xt`; the main repository's latest release can be a nightly.
  The full Linux package supplies `usr/lib/vst3/Surge XT.vst3` and
  `usr/share/surge-xt`. For an isolated extracted package, set `SURGE_DATA_HOME` to that
  factory-data directory; the [versioned loader](https://github.com/surge-synthesizer/surge/blob/release_xt_1.3.4/src/common/SurgeStorage.cpp)
  supports this override. Declare both the bundle and data with `tool()` so the receipt
  records them. [FAQ](https://surge-synthesizer.github.io/faq/): GPL governs software
  redistribution; music/sounds made with factory presets or original patches may be
  used commercially. External third-party material retains its own conditions.
- **Dexed:** Linux x64 and Windows x64 VST3 builds; macOS Intel/Apple Silicon universal
  also offers AU. The tested ZIP contains `Dexed.vst3` with embedded resources; no external
  sample library is needed. [Versioned README](https://github.com/asb2m10/dexed/blob/v1.0.1/README.md)
  identifies GPLv3 and component notices. Ordinary musical output is distinct from
  redistribution of the plugin or patch banks. Preserve third-party `.syx` provenance;
  do not label all available banks CC0.
- **Nova:** the current [product page](https://www.tokyodawn.net/tdr-nova/) supplies Linux
  x64 VST2/VST3 (glibc >= 2.14), Windows 32/64-bit VST2/VST3 and macOS 64-bit
  VST2/VST3/AU with native Apple Silicon support. Choose `TDR Nova.vst3` from the Linux
  archive. Its bundled `license.txt` explicitly permits commercial music production;
  redistribution of the software requires TDR permission. It is proprietary freeware,
  not open-source or permission to ship the binary with Tactus.
- **CHOW Tape:** tested Linux DEB provides VST3/CLAP/LV2/standalone and requires glibc
  >= 2.29; do not infer VST2 from the general project description. Official Windows
  64-bit and macOS packages exist, but their binaries/CPU slices were not inspected.
  The extracted bundle is `usr/lib/vst3/CHOWTapeModel.vst3`.
  [GPLv3 license](https://github.com/jatinchowdhury18/AnalogTapeModel/blob/v2.11.4/LICENSE):
  processing ordinary music does not make that music GPL; binary redistribution has
  separate obligations.
- **Dragonfly:** tested Linux x86_64 package has four VST3 bundles. Official releases
  also provide other Linux architectures, Windows 32/64 and macOS Intel/universal
  packages; none of those host combinations was tested here. The GUI requires OpenGL
  3.0 per the official README; headless audio success does not verify that GUI.
  Use `DragonflyHallReverb.vst3` for the tested result.
  [GPLv3 license](https://github.com/michaelwillis/dragonfly-reverb/blob/3.2.10/LICENSE)
  separates ordinary music output from redistribution of the program.

## Tactus handoff

Use `pedalboard.load_plugin(str(tool("/absolute/path/Plugin.vst3")))` in a work;
retain the downloaded package and the factory data it needs. Consult the
[runtime helpers](../../references/runtime.md#helpers-from-tactus-import-fx) and
[compose](../../compose/SKILL.md) for MIDI/effect rendering and receipted audio.
Read back parameter values: requested Nova 400 Hz resolved to 401 Hz, and Dragonfly's
2-second decay resolved to 2.0008 seconds. With `fx.set_param`, specify `unit="s"`
for that decay rather than assuming a unitless number means seconds.

Recheck one chosen build after changing host, architecture or dependencies. Preserve
warnings alongside passes; plugin version, archive hash, bundle/data identity and run
receipt together explain what was actually exercised.
