# pytimestretch consumer probe

2026-09-25。本證據交回「是否作為 Tactus stretch 核心套件」的待決定事項，
不代表已採用、已修改產品依賴或已通過音質驗收。

## 判斷

pytimestretch 適合成為 Tactus 的 stretch 核心套件候選。它直接接受 NumPy、
回傳明確長度的音訊，讓作品自行決定目標長度、引擎與音樂處理方式，符合目前的
產品原則。正式採用仍待音質驗收與固定安裝版本；本次不修改正式依賴。

## 方法與結果

- 按 [README](https://github.com/openmirlab/pytimestretch/tree/1b7fce0e4f0fc22a79ad8c652e7d8922362078f8)，
  用 `uv` 安裝 `v0.1.0` 原始碼與 submodules，成功編譯兩個引擎。
  Tag 對應 commit 為 `ab6871ab9cc1c59956f6c9182b59d93cde61f585`。
- 使用約 155.195 秒、82 BPM 的現有歌曲副本，替換 stretch 和 pitch-shift 呼叫。
  Tactus 固定在 `59ae34a`，排除同時進行的開發。判準先記於 probe 的 `preregister.md`。
- 原版、新 Rubber Band、Signalsmith 全部完成整曲。原版重跑一致，也與既有作品
  `dogfood/2026-09-25-full-song/work/runs/r3/` 的全部音檔一致。
- 整首縮短至 80%：兩引擎均為 **5,475,283 frames／124.156 秒**。
- 整首拉長至 125%：兩引擎均為 **8,555,130 frames／193.994 秒**。
- 四組規律節拍／440 Hz 控制測試全部通過：節拍位置最大誤差 **1.265 ms 以下**，
  tempo 誤差 **0.002% 以下**，音高誤差 **0.003 cents 以下**。
  事前判準分別為 20 ms、1%、10 cents；這些結果只適用於本次控制訊號，
  不是對實際音樂每個瞬態的保證。
- 整曲 stretch 與節拍控制的輸入陣列 hash 保持不變；原作品 Python source 保持原樣。
- 最初一次 Rubber Band render 的 bass 在約 11.9–16.1 秒不同。獨立重跑 bass 六次
  未重現，六次 MIDI hash 與 SFZ 輸出 hash 一致，原因未明；固定同一份 SFZ bass take
  後，兩引擎未處理的 drums、bass 均完全一致。不能宣稱任意完整作品都能確定性重現，
  也不能把這個異常直接歸因於 pytimestretch。

## 接入要處理的事情

1. `rate` 改成倒數的 `duration_ratio`；對齊指定長度時用
   `target_frames / len(audio)`。
2. 新套件不自動限幅。本次整曲 stretch 峰值最高 **1.145**；Tactus 輸出前需由作品
   明確設定 headroom／gain。試聽檔統一乘以 0.75，原始 FLOAT 檔另存。
   這符合套件契約，不是自動判定的套件 bug。
3. 新 Rubber Band 是 4.0.0 R3，舊版為系統 3.3.0；不能承諾音色相同。
   保留 backend 選擇，不由 Tactus 隱藏切換。
4. 固定套件 revision／wheel 與 dependency lock。README 目前沒有 PyPI release，
   套件標示 GPL-2.0-or-later。
5. 先讓作品直接使用套件；目前沒有證據需要再新增一層 `tactus.stretch` API。

## 證據範圍與重跑資料

只驗證本機 Linux、Python 3.12、這首作品與指定比例。尚未經人的聆聽，不能宣稱
「沒有怪聲」；marker warp、其他平台與極端比例不在本次結論內。
原作品既有的 keys clipping、reverb、master peak normalization 保持原樣，
因此整曲比較也包含這些處理對不同引擎輸出的反應。

來源副本、事前判準、環境版本、native hashes、receipts、原始測量與試聽頁保存在
`dogfood/2026-09-25-pytimestretch/`（ignored local artifacts）：

- `probe.py`、`preregister.md`、`results.json`：初始整曲、長短比例與訊號控制測試。
- `bass_probe.py`、`bass-diagnostic/`：六次獨立 bass 診斷與 MIDI／音訊 hashes。
- `controlled.py`、`controlled-results.json`：固定 bass 後的三次完整 render。
- `works/`、`runs/`：作品副本與每次 manifest、receipt、完整輸出。
- `index.html`、`listen/`：整曲、副歌、轉場與獨立音軌的試聽；片段由整曲裁切。
- `environment-notes.md`、`requirements.freeze.txt`、`original-source-hashes.json`：
  安裝命令、實際版本、原 source 身分；`results.json` 另記 native module hashes。

這次獨立環境的實際版本記在 `requirements.freeze.txt`、`results.json`；
receipt 找到的祖先 `uv.lock` 並不代表本次安裝環境。未修改產品 dependency 或正式作品。

本機試聽入口：`http://localhost:4181/`（需要伺服器與 port forwarding 仍運作）。
