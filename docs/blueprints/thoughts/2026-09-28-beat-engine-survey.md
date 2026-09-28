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

## 實測比較（2026-09-28）

Paul：「那你可以幫我 run 起來比較一下嗎」。判定規則事先寫定（scratchpad `beat-eval/PREREGISTERED.md`）。

**做法：**
- 引擎與素材由兩個互相看不到對方的 Agent 分別準備；所有引擎都用文件上的預設參數，不調參。
- QM 從原始碼編譯（qm-dsp、vamp-plugin-sdk，放在使用者目錄，不需要 root），透過 Python `vamp` host 呼叫。Essentia 在獨立的 Python 3.10 環境執行。
- 素材有兩部分：
  - 31 個合成檔，用 crate 裡真實錄製的鼓聲排成，真值取自生成參數。分成穩定、變速、弱起拍、奇數拍號、切分、完整混音六類，每類 5–6 個；
  - Ballroom 真實音樂 41 首，附人工標註（CPJKU BallroomAnnotations），在 9 種舞曲間分層抽樣。
- 評分用 `mir_eval`。

**拍點 F-measure（±70 ms）：**

| 引擎 | 穩定 | 變速 | 弱起拍 | 奇數拍號 | 切分 | 完整混音 | Ballroom |
|---|---|---|---|---|---|---|---|
| librosa | 0.86 | 0.80 | 0.98 | 0.89 | 0.64 | 0.91 | 0.71 |
| QM tempo | 0.98 | 0.94 | 0.98 | 0.98 | 0.85 | 0.97 | 0.80 |
| QM bar | 0.96 | 0.92 | 0.96 | 0.84 | 0.84 | 0.97 | 0.81 |
| Essentia multifeature | 0.96 | 0.95 | 0.96 | 0.96 | 0.84 | 0.96 | 0.77 |
| Essentia degara | 0.96 | 0.95 | 0.96 | 0.84 | 0.84 | 0.96 | 0.80 |
| aubio | 0.83 | 0.50 | 0.77 | 0.58 | 0.73 | 0.90 | 0.60 |

**BPM 準確率（±4%）：**
- 切分：librosa 0.20，其他引擎 0.60；
- Ballroom：Essentia multifeature 0.71、Percival 0.68、degara 0.66、QM bar 0.63、QM tempo 0.59、librosa 0.54、aubio 0.54。

**第一拍 F-measure（只有 QM bar 做得到）：**
- 穩定 0.48、變速 0.16、弱起拍 0.19、Ballroom 0.44；
- 提供正確拍號後：Ballroom 0.56，奇數拍號反而從 0.25 降到 0.07。

**依事先規則判定：**
- **拍點：**QM tempo 明顯比 librosa 準。三類困難素材平均 0.92 對 0.78；Ballroom 0.80 對 0.71；穩定素材也沒有變差。Essentia multifeature 同樣過門檻（0.92；Ballroom 0.77）。
- **BPM：**Essentia multifeature 最好；QM 略優於 librosa。
- **第一拍：**QM 在穩定 4/4 只有 0.48，低於 0.8 的門檻，**不可用**。目前沒有可用的非 NN 第一拍方案。
- aubio 全面落後。

**限制：**合成素材每類只有 5 個檔案，只能看趨勢；Ballroom 全是舞曲，不代表所有曲風。

**建議（待 Paul 決定）：**拍點偵測如果要做，用 qm-dsp。照 Mixxx 的做法直接綁定 `DetectionFunction` 與 `TempoTrackV2`，不經過 Vamp；授權是 GPL-2.0+，與現有的授權相容。Essentia 需要 AGPL 和另一個 Python 版本，整合成本高。第一拍暫不做。
