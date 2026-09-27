# 非神經網路的 BPM／拍點／第一拍引擎：調查

> 2026-09-27～28 · Paul：「我想要請你幫我找 reliable 的 beat, downbeat, bpm engine（c++ 的也可以，主要希望能夠盡量開源，
> 然後不要 nn based 的）」。調查完後 Paul 說「先不用做」，所以只記錄結果，沒有實測準確度。
> 這是看板 Next「統一的音檔分析」第 3 塊（拍點偵測）的前置資料。

## 結果

| 引擎 | BPM | 拍點 | 第一拍 | 授權 | 本機（Linux、Python 3.12）|
|---|---|---|---|---|---|
| librosa `beat_track`（Ellis 2007 動態規劃） | ✅ | ✅（假設速度固定） | ❌ | ISC | ✅ 已內建；合成 120 BPM 測得 120.19 |
| Essentia RhythmExtractor2013（multifeature／degara）、PercivalBpmEstimator | ✅ | ✅（附信心分數） | ❌（`Meter` 只給拍號） | AGPL-3.0-only（另有商用授權） | ⚠️ PyPI wheel 只到 cp310，3.12 需自行編譯；在 3.10 測得 119.85–120.19 |
| aubio（Davies 的因果式 beat tracking） | ✅ | ✅ | ❌ | GPL-3.0-or-later | ✅ 從原始碼建置成功，測得 121.7；0.4.9（2019）後沒有新版 |
| QM Tempo and Beat／Bar and Beat Tracker（qm-dsp，Davies & Plumbley） | ✅ | ✅ | **✅ 唯一的非 NN 第一拍方案**，Mixxx 也用它 | GPL-2.0-or-later | ❌ `vamp` host 可裝，外掛本體 Ubuntu 沒有套件，要自行編譯 qm-dsp 依賴鏈（不需 root） |
| BTrack（Stark） | — | ✅（即時） | ❌ | GPL-3.0 | ❌ PyPI 非官方套件的 sdist 是壞的，要從 GitHub 自行編譯 |
| SoundTouch BPMDetect | ✅（只給平均值） | ❌ | ❌ | LGPL-2.1 | 未測 |
| Marsyas IBT、BeatRoot | — | ✅ | ❌ | LGPL／GPL | 未測，看起來已停擺 |

排除的 NN 方法：madmom 的 RNN／DBN、beat_this、BeatNet、All-In-One、Essentia TempoCNN。

## 要點

- **非 NN 的第一拍偵測實際上只有 QM 一家**，但在本機還沒跑通。
- **授權：**aubio、BTrack、QM 都是 GPL，不會在 Tactus 既有的 GPL 義務之外再增加負擔。Essentia 的 AGPL 多了網路服務條款；本地工具影響不大，如果將來要做線上服務，就得重新考慮。
- **這次沒有公開準確度數字**（MIREX、Ballroom、GTZAN 等），也沒有做自己的準確度實測。

## 恢復時的下一步（未做）

1. 在本機編譯 QM 外掛；
2. 在 3.12 編譯 Essentia，或先在 3.10 環境測試；
3. 用標好答案、而且引擎沒見過的素材實測，素材要涵蓋速度變化、弱起拍與非 4/4；
4. 判定規則先寫定。

測試腳本放在 scratchpad `beat-engines/`。
