# Free VST instruments and effects

Use this when choosing a well-reviewed plugin for a Tactus work. The catalog has
**nine instrument choices and ten effect choices**, selected by musical purpose rather than popularity. Checked **2026-10-15**:
all selected products below were obtained from official downloads at zero cost without
accounts, activation or paid trials. Exact Linux x86_64 VST3 builds were loaded and
rendered through Tactus with Pedalboard **0.9.26**, Python **3.12.11** or **3.13.12**, glibc **2.39**,
at **44.1 and 48 kHz stereo**. Windows/macOS support below is vendor information,
not our host-test result. Recheck current releases and terms before acquisition.

An independent recheck used new **12-second fixtures for all 19 choices** at both
sample rates: varied and overlapping MIDI notes, note-offs and no-note controls for
all instruments, plus plugin-level controls for six; tonal/transient inputs, dry/control
comparisons and intended-response measurements for effects. Instrument rate/block pairs were 44.1 kHz / 128 and 48 kHz /
512 frames; the eight non-ZL effects also exercised both block sizes at each rate.
Basic audio operation passes throughout; state restoration, native warnings and
repeatability have the per-plugin limitations below.

## Choose by purpose

### Instruments

| Job | Choice | Why it is worth considering | Verified scope and limits |
|---|---|---|---|
| Broad synthesis: pads, leads, bass, modulation | [Surge XT 1.3.4](https://surge-synthesizer.github.io/) | MusicRadar's [hands-on synthesis tutorial](https://www.musicradar.com/how-to/fantastic-free-synths-surge-xt), 2022-12-01, favorably assesses its breadth and modulation. Strong first general-purpose synth; a substantial interface to learn | **Qualified pass:** MIDI, no-note and level controls work. Settled state replay restores audio level but can leave a stale volume readback; verify audio, not only parameter values. Full factory data acquired; initial sound tested, not every preset. Separate Effects bundle untested |
| FM electric pianos, bells, bass; DX7 workflows | [Dexed 1.0.1](https://asb2m10.github.io/dexed/) | MusicRadar's [DX7/FM programming tutorial](https://www.musicradar.com/news/fantastic-free-synths-dexed), updated 2023-02-02, gives a positive practical assessment. Complements Surge for six-operator FM; programming FM takes practice | Instrument VST3 responds to MIDI; no-note control is silent. Initial embedded sound tested; hardware SysEx transfer and arbitrary imported banks untested |
| Analogue brass, pads and bass | [OB-Xf 1.0.3](https://surge-synth-team.org/ob-xf/) | [CDM / Peter Kirn, 2026-01-02](https://cdm.link/ob-xf-free-beta/) reports a favorable hands-on experience with the earlier beta's sound and tuning; distinct from a current-build review | **Limited pass:** fresh-instance MIDI, silent control and volume changes pass. A state/multiple-instance probe produced one native SIGSEGV; state replay after muting remained silent in two independent repeats. Startup race diagnostic persists. A later settled single-instance replay restores level at 48 kHz / 512 frames; this does not establish that the earlier crash is fixed. Factory presets/GUI untested |
| Wavetable, FM/PM, chiptune and drawn oscillators | [Odin 2, delivered 2.4.1](https://thewavewarden.com/pages/odin-2) | [MusicRadar, 2025-06-30](https://www.musicradar.com/music-tech/synths/fantastic-free-plugins-and-how-to-use-them-the-wave-warden-odin-2) favorably explores oscillator/filter/modulation flexibility in a practical tutorial | Initial sound responds to MIDI; silent control. Official heading says 2.4.0, linked archive and binary say 2.4.1. Preset installation and GUI untested |
| Compact subtractive bass, leads and chorused pads | [TAL-NoiseMaker 5.0.6](https://tal-software.com/products/tal-noisemaker) | [MusicRadar, 2023-01-29](https://www.musicradar.com/how-to/fantastic-free-synths-tal-noisemaker) praises sound and approachable layout; six-voice ceiling, and reviewed performance-control limitations | MIDI response passes; no-MIDI PCM has a negligible fixed 1.19e-7 floor, not exact silence. Additional 75-second note/tail and no-MIDI check found no periodic noise; other presets untested |
| Sampled acoustic grand piano | [sfizz 1.2.3 + Salamander Grand Piano V3](https://sfz.tools/sfizz/downloads/) | [BPB / Tomislav Zlatic, updated 2026-10-13](https://bedroomproducersblog.com/free-vst-plugins/piano/) praises Salamander’s dynamics and neutral mix tone; notes thinner high notes and mechanical repetition without round robins. This evaluates the library, not this host build | Full 641-WAV library decoded; original SFZ mapping responds to five MIDI keys at velocity 90, no-MIDI silent. **Qualified host pass:** scan/state buffer, scheduling and empty-SCL warnings; local dependency needed. Sustain, other layers/maps and GUI untested |
| Wavetable/additive textures and detailed waveform design | [Zebralette 3, 3.0.0 rev. 20399](https://u-he.com/products/plug-ins/zebralette3/) | [Audio Plugin Guy / Charlie Hatton, 2026-04-17](https://www.audiopluginguy.com/free-plugin-review-u-he-zebralette-3/) praises vector waveform editing and sonic range; a learning curve | Initial patch responds to four MIDI notes; no-MIDI silent. **Qualified pass:** registration-key, missing-parameter and cleanup diagnostics. Factory-preset browsing, experimental sample import and GUI untested |
| Analogue-style bass, leads and cinematic pads | [TyrellN6 Beta, 3.0.0 rev. 16976](https://u-he.com/products/plug-ins/tyrelln6/) | [BPB / James Nugent, 2023-07-14](https://bedroomproducersblog.com/2023/07/14/tyrell-n6/) praises oscillator tone and spacious cinematic sounds; review predates this beta | Initial patch MIDI response and silent control pass; **public beta with native diagnostics**. Commercial music permitted, **sample-library creation prohibited**; other presets/GUI untested |
| Comb-filter plucks, string-like and unusual textures | [Triple Cheese 1.3 rev. 12092](https://u-he.com/products/triplecheese/) | [Bonedo / Ruben Seevers, 2009-03-17](https://www.bonedo.de/artikel/u-he-triple-cheese/) rates an older version 4/5, favoring unusual synthesis and modular flexibility; its GUI criticism predates the current interface | Initial patch responds to four MIDI notes; no-MIDI silent. Factory-preset browsing and GUI untested; Linux support is vendor beta |

### Effects

| Job | Choice | Why it is worth considering | Verified scope and limits |
|---|---|---|---|
| Dynamic EQ and frequency-selective compression | [TDR Nova 2.2.3](https://www.tokyodawn.net/tdr-nova/) | MusicRadar's [dedicated hands-on article](https://www.musicradar.com/music-tech/plugins/fantastic-free-plugins-and-how-to-use-them-tdr-nova), 2025-06-01, recommends its accessible EQ/dynamics workflow. Standard edition has four dynamic bands; paid **Nova GE** is separate | Linux VST3 loaded; band-2 EQ changes the signal, and enabling its dynamics produces a different output from static EQ. External sidechain and all other modes untested |
| Tape saturation, wow/flutter and lo-fi color | [CHOW Tape Model 2.11.4](https://chowdsp.com/products.html) | [BPB's firsthand review](https://bedroomproducersblog.com/2020/07/14/chow-tape-model/), updated 2021-01-23, praises its tape coloration and degradation controls. Useful for coloration; high oversampling costs CPU | VST3 processes tonal transients with a nonzero dry/wet difference, finite output and no clipping. Tape drive/saturation checked, not every degradation mode. Keep input below unity as advised by the [manual](https://chowdsp.com/manuals/ChowTapeManual.pdf) |
| Conventional hall reverb on Linux | [Dragonfly Hall Reverb 3.2.10](https://michaelwillis.github.io/dragonfly-reverb/) | [LANDR's hands-on roundup](https://blog.landr.com/free-reverb-vst-plugins/), 2026-03-13, praises natural tails. It also reports Early Reflections instability on M2/macOS Sonoma; that is a different variant/host | **Hall only:** VST3 processing and tail checks pass, with DPF component/connection-point cleanup warnings. Do not call it warning-free. Room, Plate and Early Reflections were downloaded but not host-tested |
| Multitap and modulated delay | [ChowMatrix 1.3.0](https://chowdsp.com/products.html) | [BPB, 2020-12-07](https://bedroomproducersblog.com/2020/12/07/chowmatrix/) praises its flexible delay trees and node overview; useful for creative echoes, with more controls to learn | Two 200 ms nodes at 45% feedback: dry/wet difference and delay tail pass. Other trees/presets and GUI untested |
| Guitar-style overdrive before an amp simulator | [ChowCentaur 1.4.0](https://chowdsp.com/products.html) | [KVR user Ripthorn2, 2020-12-26](https://www.kvraudio.com/product/chow-centaur-by-chowdhury-dsp/reviews) recommends its tone before an amp sim. Four favorable user reviews observed: a smaller evidence base than the editorial picks | **Traditional mode only:** processing difference passes. An older 1.2.0 Windows review reports Neural-mode dropouts; current Neural mode untested |
| Ambient reverb and a wider effects toolbox | [Airwindows Consolidated, 2026-10-11-8a67b80](https://www.airwindows.com/consolidated/) | [BPB, 2024-05-08](https://bedroomproducersblog.com/2024/05/08/airwindows-consolidated/) favors Galactic ambience, Mackity distortion and ToTape transient softening, and welcomes shared documentation | **Galactic only, qualified pass:** saved-state selection, dry/wet and reverb-tail checks pass. Fresh instances with identical input/settings/block size produce different audio; preserve the chosen render. Other algorithms untested |
| Track and bus compression | [ZL Compressor 0.6.1](https://zl-audio.github.io/plugins/zlcompressor/) | [BPB / Magnus Vanebo, 2025-06-26](https://bedroomproducersblog.com/2025/06/26/zl-audio-zl-compressor/) praises flexible controls and approachable basic compression; early-version experience, not current stability certification | **Clean mode:** quiet signal unchanged, loud steady signal reduced about 12.3 dB at threshold -24 dB / ratio 4; disabled control equals dry. Other styles/sidechain untested |
| Detailed parametric and dynamic EQ | [ZL Equalizer 2, version 1.4.1](https://zl-audio.github.io/plugins/zlequalizer2/) | [BPB / Tomislav Zlatic, 2025-11-14](https://bedroomproducersblog.com/2025/11/14/zl-equalizer-2/) favors the refined interface and extensive EQ controls; notes a learning curve and then-unfinished EQ matching | **Static Minimum Phase only:** 1 kHz cut measures -12 dB while 100 Hz / 8 kHz are nearly unchanged; disabled band equals dry. Dynamic, matching and other phase modes untested |
| Vintage phaser sweeps and stereo movement | [ChowPhaser Stereo 1.1.1](https://chowdsp.com/products.html) | [BPB / Tomislav Zlatic](https://bedroomproducersblog.com/free-vst-plugins/phaser/) favors smooth, slightly gritty sound and stereo depth; controls take learning. Page heading updated 2026-04-01, body credits 2025-08-17 | **Stereo only:** processed signal differs from dry; LFO depth 0.7 differs from zero-depth control. Mono bundle not rendered; GUI untested. Tested release dates to 2021 |
| Steep filtering and a broader sound-design toolbox | [ChowMultiTool 1.1.0](https://chowdsp.com/products.html) | [BPB / Tomislav Zlatic, 2023-05-26](https://bedroomproducersblog.com/2023/05/26/chowmultitool/) favors direct EQ controls and versatile waveshaping; not a review of the tested Brickwall mode | **Brickwall Butterworth lowpass only:** 799 Hz / 12th order preserves 100/400 Hz and reduces 1600 Hz about 72.7 dB. Other tools/GUI untested |

Reviews establish attributed opinions about usefulness, often on older versions; they
do not certify the exact builds above. Our short render checks establish MIDI/audio
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
| ChowMatrix 1.3.0 | [Linux official package](https://github.com/Chowdhury-DSP/ChowMatrix/releases/download/v1.3.0/ChowMatrix-Linux-x64-1.3.0.deb) | 2,990,012 | `332749bba2fcfefeb68c105b9f55fd71aa7a8bfb524f592cbb68cc6c0581a767` |
| ChowCentaur 1.4.0 | [Linux official package](https://github.com/jatinchowdhury18/KlonCentaur/releases/download/v1.4.0/ChowCentaur-Linux-x64-1.4.0.deb) | 2,523,664 | `abd0fda32e5b45f0b144ac3d4559009e3b837a9be0b859d99a82c4bba9c52303` |
| Airwindows Consolidated DAWPlugin 2026-10-11-8a67b80 | [Linux official package](https://github.com/baconpaul/airwin2rack/releases/download/DAWPlugin/AirwindowsConsolidated-2026-10-11-8a67b80-Linux.zip) | 32,481,932 | `9144dc8b412179f862a6dd5d72e474d606d38376c2a404efefa2c5134174f12c` |
| OB-Xf 1.0.3 | [ob-xf-Linux-v1.0.3.deb](https://github.com/surge-synthesizer/OB-Xf/releases/download/v1.0.3/ob-xf-Linux-v1.0.3.deb) | 38,526,792 | `c61077525634be5c96693f81326ab6b29b5bbb4f8e8fd3a0482b9bb827898853` |
| Odin 2 2.4.1 | [Odin2.4.1Linux.zip](https://thewavewarden.com/pages/odin-2) | 66,588,004 | `8ce5353605f8bfbc9228ccdbd177a9096dae3bed7245dbcd24c642ce35a19cb2` |
| TAL-NoiseMaker 5.0.6 | [TAL-NoiseMaker_64_linux.zip](https://tal-software.com/downloads/plugins/TAL-NoiseMaker_64_linux.zip) | 7,144,872 | `328565e646f98f14dd931a33fa438a4c9eddc451e759b92d1005f4336fa3fd20` |
| sfizz 1.2.3-0, Ubuntu 24.04 amd64 | [Official package](https://download.opensuse.org/repositories/home:/sfztools:/sfizz/xUbuntu_24.04/amd64/sfizz_1.2.3-0_amd64.deb) | 3,368,080 | `4424135807cb4210fe2c332faf7cdfbb70605bba3f8a81fc1857360a59af04bd` |
| Salamander V3+20161209, 44.1 kHz / 16-bit | [Official package](https://freepats.zenvoid.org/Piano/SalamanderGrandPiano/SalamanderGrandPianoV3+20161209_44khz16bit.tar.xz) | 412,313,804 | `58750eb1366761e187f71ddb9b932355ea894d28ec4331e74ab8acb44c819936` |
| ZL Compressor 0.6.1 | [Official Linux x86-64 ZIP](https://github.com/ZL-Audio/ZLCompressor/releases/download/0.6.1/ZL.Compressor-0.6.1-Linux-x86-64.zip) | 8,943,456 | `00d7201fc9643f7b7c49d9791d1e5fc73528835a5dba40a3866fd4a274767ae6` |
| ZL Equalizer 2 1.4.1 | [Official Linux x86-64 ZIP](https://github.com/ZL-Audio/ZLEqualizer/releases/download/1.4.1/ZL.Equalizer.2-1.4.1-Linux-x86-64.zip) | 10,850,259 | `ba253ef4e608e5d6f72b2c341a7bc0d9c48b79e051806c2367d481814a4dc896` |
| ChowPhaser Stereo v1.1.1 | [Official Linux x64 DEB](https://github.com/jatinchowdhury18/ChowPhaser/releases/download/v1.1.1/ChowPhaser-Linux-x64-1.1.1.deb) | 11,990,512 | `554ef220e96ea2c355e8ed8aa0c94c8bbcc281b5ce8069a12865a75ef6737889` |
| ChowMultiTool v1.1.0 | [Official Linux x64 DEB](https://github.com/Chowdhury-DSP/ChowMultiTool/releases/download/v1.1.0/ChowMultiTool-Linux-x64-1.1.0.deb) | 11,107,512 | `69b6718b08a1072d1f27817dace1e07a689a2b8ce7cee9bc9530b107e2343803` |
| u-he Zebralette 3 3.0.0 revision 20399 | [Zebralette3_300_20399_Linux.tar.xz](https://u-he.com/products/plug-ins/zebralette3/) | 8,694,308 | `df34d1cce6712702894d3cbdeff1c3ab7465142638d3bcc82c86eb5ee02ec580` |
| u-he TyrellN6 Beta 3.0.0 revision 16976 | [TyrellN6_300_public_beta_16976_Linux.tar.xz](https://u-he.com/products/plug-ins/tyrelln6/) | 8,030,972 | `4d7a4ebd124dc2f341d9f53bc585b0ca508806accc32469bfe185ae99ba4c916` |
| u-he Triple Cheese 1.3 revision 12092 | [TripleCheese_13_12092_Linux.tar.xz](https://u-he.com/products/triplecheese/) | 8,594,840 | `04ea1233fd64173746480c85e662f3e81d3e48c1149ca419f89a216e850fb3c4` |

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
  used commercially. External third-party material retains its own conditions. The independent
  probe found an immediate volume edit after `raw_state` restoration could be overwritten;
  fresh-instance volume changes after warmup work. A settled single-instance replay at
  48 kHz / 512 frames restores audio level, but the exposed volume readback stays reduced.
  Verify rendered behavior as well as readback when restoring state; exact rerender identity
  and arbitrary state/parameter ordering are not established.
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

- **ChowMatrix / ChowCentaur:** [Matrix license](https://github.com/Chowdhury-DSP/ChowMatrix/blob/v1.3.0/LICENSE) and [Centaur license](https://github.com/jatinchowdhury18/KlonCentaur/blob/v1.4.0/LICENSE) are BSD-3-Clause for their source; packaged dependencies retain separate terms. Both are full free downloads with official Windows/macOS/Linux builds; only Linux x86_64 VST3 was exercised. Bundles are `usr/lib/vst3/ChowMatrix.vst3` and `usr/lib/vst3/ChowCentaur.vst3`. No external sample library needed. Matrix's node parameters include text values such as `200.00 ms` and `45%`; inspect host representations. Centaur's tested Traditional mode uses gain 0.75, treble 0.5 and level 0.25.
- **Airwindows Consolidated:** choose the [DAWPlugin release](https://github.com/baconpaul/airwin2rack/releases/tag/DAWPlugin), not the VCV build returned by GitHub's latest-release endpoint. The rolling release replaces artifacts; pin filename date, commit fragment and SHA. Official builds include Ubuntu x64, Windows x64 and macOS universal; Linux `Airwindows Consolidated.vst3` was tested. The [versioned README](https://github.com/baconpaul/airwin2rack/blob/8a67b80/README.md) describes MIT DSP/wrapper code and GPL dependencies in combined distributions; binary redistribution is not MIT-only. The effect selector was not exposed as a regular Pedalboard parameter: retain a selected plugin state and restore it for headless rendering. Our state identifies Galactic; its other algorithms were not tested. No external samples needed.

- **OB-Xf:** [stable 1.0.3 release](https://github.com/surge-synthesizer/OB-Xf/releases/tag/v1.0.3) provides Linux, Windows and macOS builds. The Linux bundle is `usr/lib/vst3/OB-Xf.vst3`; binary identifies `1.0.3.1223e6f`. Full DEB includes factory assets, but this check used the embedded initial sound with `OBXF_DOCUMENT_FOLDER` pointing to a private settings folder. For normal preset browsing follow the [official setup guide](https://surge-synth-team.org/ob-xf/manual/getting-started/). [GPL-3.0-or-later](https://github.com/surge-synthesizer/OB-Xf/blob/v1.0.3/LICENSE) covers software, separately from musical output and third-party presets. Download SHA matches GitHub's asset digest. Preserve the startup diagnostic rather than calling the host warning-free.
- **Odin 2:** official Windows/macOS/Linux downloads; Linux ZIP contains `Odin2.vst3`. Use the optional-email dialog's **No thanks, just download** route, then the officially linked Dropbox ZIP; neither email nor account was needed. Retain full `Odin2.4.1Linux.zip` and its README: manual bundle copying alone does not install factory presets. `install.sh` was inspected but not executed. [GPLv3 source/license](https://github.com/TheWaveWarden/odin2/blob/master/LICENSE), with separate font terms; no external samples needed for the tested initial sound. The delivered 2.4.1 archive/binary and 2.4.0 page heading differ; pin the actual artifact.
- **TAL-NoiseMaker:** listed in the official [FREE Plug-Ins catalog](https://tal-software.com/products), with Windows 64-bit, macOS Intel/Apple Silicon universal and Linux x64 builds. Linux ZIP contains `TAL-NoiseMaker/TAL-NoiseMaker.vst3` plus other formats. No external sample library or activation needed. The shared TAL EULA, extracted from the official [Chorus Windows installer archive](https://tal-software.com/downloads/plugins/install_TAL-Chorus-LX.zip), grants install/use without a noncommercial-only restriction, while limiting software redistribution; no Windows host test is implied. The old NoiseMaker manual's GPL wording does not establish the current binary's redistribution license. Odin/TAL hashes here are observed fingerprints, not vendor checksum confirmations.

- **sfizz + Salamander:** acquire both the [sfizz engine](https://sfz.tools/sfizz/downloads/) and [FreePats library](https://freepats.zenvoid.org/Piano/acoustic-grand-piano.html). The tested Ubuntu 24.04 amd64 DEB requires glibc >= 2.38, supplies `usr/lib/vst3/sfizz.vst3`, and matches the publisher’s package-index SHA. The sample archive contains two mappings and 641 WAVs: retain relative paths and use `SalamanderGrandPianoV3.sfz`; the retuned mapping was not tested. [Alexander Holm / CC-BY-3.0](https://sfzinstruments.github.io/pianos/salamander/) requires attribution, a license link and applicable change notices; free cost does not mean public domain. The library archive’s README has an older V2 title but a V3+20161209 changelog. [sfizz source](https://github.com/sfztools/sfizz-ui/blob/1.2.3/LICENSE) uses BSD-2-Clause; this VST3 distribution includes GPL-3.0 terms. Upstream offers Windows/macOS builds, untested here.

  This Linux host lacked `libxcb-cursor.so.0`. The test used `apt-get download libxcb-cursor0`, `dpkg-deb -x PACKAGE dependencies`, and a subprocess-local `LD_LIBRARY_PATH` pointing to `dependencies/usr/lib/x86_64-linux-gnu`; no system install. Tested dependency package: `libxcb-cursor0_0.1.4-1build1_amd64.deb`, 10,718 bytes, SHA-256 `137cf52479b5a9d8c5926d70d311af04be41941a32ee777340d704cc458c06d8`. Declare the resolved library file, plugin bundle and full sample tree in the run inputs. Sample selection was set through Pedalboard `raw_state` using the exact [1.2.3 version-5 serialization](https://github.com/sfztools/sfizz-ui/blob/1.2.3/plugins/vst/SfizzVstState.cpp); this is a version-specific adapter, not a portable named parameter. For interactive setup, select the SFZ in the plugin and preserve a host-supported preset/state; that GUI path was not exercised here. Buffer-capacity warnings (`2048` requested vs `1024` available) occur during scan/state setup; short playback checks pass at 64, 128 and 512 frames, without certifying realtime or arbitrary block sizes.

- **ZL Compressor / ZL Equalizer 2:** official Windows/macOS/Linux builds; tested the Linux x86-64 **non-AVX2** ZIPs, with bundles under `VST3/`. Both package hashes match official GitHub asset digests. No external sample data required. The “2” is the Equalizer product name; the tested release is 1.4.1, not legacy Equalizer 0.6.2. [Compressor AGPLv3](https://github.com/ZL-Audio/ZLCompressor/blob/0.6.1/LICENSE.md) and [Equalizer AGPLv3](https://github.com/ZL-Audio/ZLEqualizer/blob/1.4.1/LICENSE.md) govern software, with logos excluded; ordinary music output is separate from software redistribution/modification. Host parameter grids matter: requested attack 10 ms resolved to 9.98, release 100 ms to 99.69, and EQ Q 2 to 2.003. Inspect the parameter's supported `valid_values` and readback instead of requiring a decimal the host cannot represent. Tests disable makeup/automatic gain compensation; compressor oversampling is Off, EQ dynamics disabled.

- **ChowPhaser / ChowMultiTool:** full free official Windows/macOS/Linux packages; only Linux x86-64 VST3 tested, no external samples. Use `usr/lib/vst3/ChowPhaserStereo.vst3` or `usr/lib/vst3/ChowMultiTool.vst3`. [Phaser BSD-3-Clause](https://github.com/jatinchowdhury18/ChowPhaser/blob/v1.1.1/LICENSE) and [MultiTool GPLv3](https://github.com/Chowdhury-DSP/ChowMultiTool/blob/v1.1.0/LICENSE) cover source; packaged dependencies retain their terms. Ordinary music output is separate from redistribution. Phaser LFO frequency 1.0 is a host-supported value; 0.8 was rejected. MultiTool defaults to `None`: select a tool. Its tested cutoffs requested at 800/4000 Hz read back as 799/4010 Hz. The shutdown message `Exiting gracefully...` is not an error.

- **u-he instruments:** official Windows/macOS/Linux downloads; Linux support is labeled beta. The tested archives contain binaries plus factory data; retain both. Installers normally assemble symlink-based VST3 bundles and use `~/.u-he/PRODUCT` data. Our isolated test copied unchanged binaries into regular-file `Zebralette3.vst3`, `TyrellN6.vst3` and `TripleCheese.vst3` bundles because Tactus directory inputs reject symlinks. It declared bundle and original data trees with `tool()`, and used bubblewrap to bind private copied data at the expected home-directory location, leaving HOME unchanged. This mount mapping is external harness state, not automatically captured by Tactus; a bare extracted binary is not the tested setup. Initial patches worked; factory-preset browsing remains untested. Archive hashes above identify original downloads, not the assembled bundle trees.

  These are proprietary freeware. Zebralette's current [product page](https://u-he.com/products/plug-ins/zebralette3/) and [license-card announcement](https://u-he.com/news/2025/12/license-cards/) explicitly say free/no activation; its bundled license retains generic paid Zebra2/Dark Zebra wording. Preserve that discrepancy and the native debug warnings. Triple Cheese's bundled license permits ordinary commercial music but places conditions on software redistribution. **Tyrell's bundled license allows commercial music but forbids creating sample libraries, redistributing binaries, direct-download hyperlinks and commercial-software integration without permission.** Link its product page, as above; do not use it as a multisample-library source or bundle it with Tactus. Third-party preset rights remain separate. Tyrell is a public beta, and its native diagnostics are retained alongside the passing audio checks.

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
