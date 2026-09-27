# 統一的音檔分析有沒有幫助？CLI 還是 code？三組對照 probe

> 2026-09-27 · Paul：「那沿著這個角度，你覺得我們是不是也會需要有統一的音樂分析？」「幫我做個 probe 來驗證這個問題」，
> 以及「分析是不是要以 cli 為主而不是 code?」。判定規則在試驗前寫定（scratchpad `probe-analysis/PREREGISTERED.md`）。
> 背景是前一個 probe：[機械性 helper](2026-09-27-mechanical-helpers-probe.md)。

## 結論

**統一的基礎量測有幫助，而且幫在正確率上。CLI 與函式平手，兩個都做，共用同一份實作。**

| 組別 | 錯誤（兩輪） | tokens（兩輪累計） | 第一輪時間 |
|---|---|---|---|
| 沒工具 N1 / N2 / N3 | 45 / 22 / 4，共 71 | 230k / 243k / 215k，平均 230k | 14–23 分鐘 |
| CLI C1 / C2 / C3 | 0 / 0 / 0 | 101k / 105k / 99k，平均 102k | 3–5 分鐘 |
| 函式 L1 / L2 / L3 | 0 / 0 / 0 | 109k / 94k / 93k，平均 99k | 2–4.5 分鐘 |

- 依事先規則，兩個有工具的組都遠超「少 2 個錯」的門檻。兩組之間 token 差 3%，低於 10%，算平手，所以兩個門都做、底下只有一份量測。
- **沒工具組的 71 個錯全部出在起音偵測。**三個 Agent 各自發明一套方法（librosa spectral flux 加手動補點、高通包絡重新對時、自訂的上升比例判斷），都自認驗證過了。N2 兩輪都認定 loop 只有 8 擊（實際 19 擊），N1 兩輪多抓或漏抓 17–28 個。
- **稽核交付檔案的七項，沒工具組全對。**這七項是 LUFS、true peak、平頂削波、DC、相位、數位靜音斷點、長度。題目明寫了量法（BS.1770、oversample、run 長度），它們用 pyloudnorm 和 `resample_poly` 照做就對了，只是花的 token 約是有工具組的兩倍。
- CLI 組的 Agent 大多也直接 import 了函式。分析素材、檢查交付檔時用 CLI 或 `analyze()`，在 `render` 裡則用函式。兩個門的分工就是這樣自然形成的。

## 前置調查

一個 sonnet Agent 讀了 30 個受試 Agent 自己寫的驗證腳本，發現：

- 最常見的是比對題目自己的 marker 位置。這不算通用量測。
- sample peak 常被重算，但 manifest 早就有 `peak_dbfs`。
- 手寫、沒有 gating 的 RMS 出現 3 次，LUFS 只出現 1 次。
- 從來沒人量過 true peak。
- 有作者不信任自己寫的起音偵測，改成只印出來、不判斷。
- 硬削波 `clipped_samples` 看不到。

所以這次題目刻意放進會騙過天真量法的地方。

## 題目

- **Part A，稽核：**7 個合成的交付檔，逐項判斷 pass/fail，並寫出 LUFS 與 true peak 數值。陷阱包括：
  - sample peak 沒過頂但 true peak 過頂；
  - 前段很安靜，未 gating 的 RMS 比 LUFS 低 2.5 dB；
  - `np.clip` 造成的平頂；
  - 局部或整段左右聲道反相；
  - 80 ms 的斷音加上長度不對；
  - DC 偏移。

  第二輪加入必須判 pass 的「差一點」案例（30 ms 靜音、3 個樣本的平頂、DC 0.0008、true peak −2.2 dBTP），以及方向相反的響度陷阱（RMS 看起來在範圍內，LUFS 其實超出）。
- **Part B，先分析再處理：**一段重疊尾音的鼓 loop，含 ghost note（低 24／30 dB）與 flam（相隔 15／10 ms）。要交出起音 marker（容許 2 ms）和指定 LUFS、true peak 上限的 mix。

評分程式先用參考解驗證過（零錯誤），7 種天真做法也都會被抓到：

- sample peak 當 true peak：錯 9 項；
- 未 gating 的 RMS 當響度：錯 14 項；
- 用 `|x| > 1` 數削波：錯 2 項；
- 只看整段的相關係數：錯 2 項；
- librosa 預設的起音偵測：錯 36 項；
- 把 mix 的 sample peak 正規化到 −1 dBFS：錯 1 項。

## 誠實交代

- **起音偵測只在合成的 loop 上驗證過。**原型能在兩個 loop 都抓到 19/19，靠的是起音乾淨的合成素材。真實錄音更難，整合前要拿真實素材再試。
- **混音題太簡單。**兩輪都只要調一次 gain 就能同時達到 LUFS 與 true peak，沒有真正考到 limiter。
- **CLI 組看得到函式原始碼。**CLI 是包在函式外的一層，所以「CLI 對函式」的比較其實是「以指令為入口對以模組為入口」，不是兩套獨立工具。
- 沒有測調性、和弦、拍點、段落這類音樂解讀。它們仍在範圍之外。

## 下一步（未決）

依事先的逐項規則，有工具的組用到的量測都要整合：

- 起音偵測；
- 響度與峰值：LUFS、true peak、sample peak、RMS；
- 檔案健康：平頂削波、DC、左右聲道相關性、數位靜音斷點、長度。

形式是一份實作、兩個門：Python 函式，以及 `tactus analyze FILE|RUN_DIR`。只回報數值，不下判定。另外要考慮讓 `tactus run` 的 `levels` 順便報平頂樣本數，這也能解掉看板 Future 的「回報平貼在滿刻度的樣本」。放在哪個模組、要不要自動附在 run 結果裡，寫 plan 時再決定，並先用真實素材驗證起音偵測。

## 後續討論（同日）

- **沒工具組確實用了現成套件。**三個 Agent 都用 pyloudnorm 量響度、`resample_poly` 量 true peak、librosa 做起音偵測
  （N2 在 `analyze_onsets.py` 直接呼叫 `librosa.onset`，N1、N3 另外跑、把結果寫死在 `song.py`）。
  所以這次比較的是「只有 skill 列出的現成套件」對「加上統一分析工具」。
- **起音偵測的優勢可能被高估。**原型偵測器是對著這兩段測試 loop 調出來的，要先用沒見過的素材驗證。
- **拍點偵測要納入範圍。**Paul：「但拍點偵測很重要欸對 daw 來說」。它是 warp、切片、對齊 loop 的地基，
  不同於調性、和弦這類詮釋，但這次沒測，要另外證明。
- Paul 決定先 pending，記在看板的 Next。
