# MIDI 演奏驗收（B1）：pitch bend 會提早 170 ms，Agent 沒發現

> 2026-09-27 · Paul：「那我們先做 midi 驗收」，並要求「你要 probe 一下有這些存在的必要」，以及
> 「我們應該借鑑 DawDreamer 的做法但不換 engine」。判定規則在試驗前寫定（scratchpad `probe-midi/PREREGISTERED.md`）。
> 驗收清單來自 [inventory](2026-09-24-implementation-evidence-inventory.md) §B1。

## 結論

**找到一個真的問題，而且 Agent 自己抓不到。已修正。**

- 透過 `fx.render_instrument` 送出的 pitch bend 最多提早約 170 ms；CC 也可能受影響。
- 修正前，3 個全新 Agent 做同一份需要準時 bend 的題目，全部交出提早 120–255 ms 的 bend，而且都沒發現。
- 修正：`render_instrument` 預設改用 64 樣本的區塊，並開放 `buffer_size` 參數。

## 量測：`render_instrument` 送進真實外掛後的行為

Tactus 自己碰到 MIDI 的只有 `fx.render_instrument`，而它把整串訊息原封不動交給 Pedalboard。
過去的 MIDI probe 只測了 mido 寫檔，從沒量過這條路。以下用 Dexed 實測，它是決定性的（重新載入三次，輸出逐位元相同）。

| 項目 | 結果 |
|---|---|
| 力度 | 單調遞增，正常 |
| 延音踏板 CC64 | 放開踏板那一刻才開始衰減，正常 |
| mido 訊息與 `(bytes, seconds)` | 輸出逐位元相同 |
| 超過 `duration` 的訊息 | 靜默丟掉，不報錯 |
| 同一時間點的 note-off／note-on | 不論列表順序，輸出都相同：由 Pedalboard 決定，不是呼叫者 |
| 音符起音 | Dexed 會對齊到 64 樣本區塊，另加 16 樣本延遲（最多約 1.65 ms）；OB-Xf 沒有這個現象，也不受 `buffer_size` 影響，屬於 Dexed 自己的特性 |
| **pitch bend** | **在它所在的 `buffer_size` 區塊開頭就生效**。Pedalboard 預設 8192 樣本，所以最多提早約 170 ms；改成 64 後誤差約 1 樣本 |

**原因**（sonnet 讀了 Pedalboard 與 DawDreamer 原始碼）：
- Pedalboard 自己把每個 MIDI 事件放在區塊內正確的樣本位置。
- VST3 沒有「pitch bend 事件」，bend 和 CC 會轉成外掛的參數變化，而多數外掛每個區塊只讀一次參數。
- 音符 on／off 是 VST3 真正的事件，外掛必須照樣本位置處理，所以不受影響。

DawDreamer 的做法也一樣：事件照樣本位置放進區塊，自動化則每個區塊讀一次。所謂樣本精確，是靠縮小區塊（必要時縮到 1）換來的，不是另一套機制。
Paul 要「借鑑但不換 engine」，因此採用同一個想法：縮小區塊。

## 必要性 probe

- **題目：**Dexed 預設音色的一段貝斯，要求每個 bend 的誤差在 5 ms 以內，內容包括：
  - 兩次瞬間 bend；
  - 51 個訊息組成的 bend 滑音；
  - 同一個音無縫重複觸發。
- **評分：**`check.py` 與正確時間的真值比對。評分程式先驗證過：正確做法 0 錯；直接用 `render_instrument` 錯 4 項，與 `buffer_size=8192` 直接呼叫逐位元相同。

**修正前，3 個全新 sonnet Agent（M1–M3）：各錯 4/6**
- 四個 bend 都提早 120–255 ms；重複觸發與音符都正確。
- 三份交出的檔案逐位元相同（`bass-ff45d8bf`），都是直接呼叫 `render_instrument`。
- **沒有一個發現：**
  - M1 與 M2 說音訊量不到 5 ms 的精度，改為信任「Pedalboard 文件記載的樣本精確排程」；
  - M3 其實量到「bend 好像提早」，但判定是測量雜訊而排除。

依事先規則（至少 2/3 做錯而且沒發現），需要修正。

## 修正

- `fx.render_instrument(..., buffer_size=64)`：暖機與正式 render 都用它，也可以自己指定。
- 代價：一段 8 秒的 Dexed 樂句，render 時間 0.24 s 對 0.21 s。
- 測試：
  - 預設與自訂的 `buffer_size` 會傳給外掛；
  - 非正數會拒絕；
  - 有 Dexed 時，實測 bend 在 2 ms 內生效（沒有 Dexed 就跳過）。

## 修正後的驗證

用同一份題目，再派 3 個全新 sonnet Agent（M4–M6）：**3 個都是 0/6 錯誤**，每個 bend 的時間誤差都是 0 ms。
它們照常呼叫 `render_instrument`，沒有做任何額外處理；M4 與 M5 在報告中提到 docstring 說明的區塊大小。
依事先規則（修正後 3/3 沒有時間錯誤）通過。

## 還沒處理的

- **`fx.process_automated` 的參數自動化：**它每 20 ms 一段，本來就是逐區塊設參數，精度就是那個區塊長度，這是文件寫明的設計，這次沒改。
- **同一時間點的 off／on 順序：**由 Pedalboard 決定。這次重複觸發都正確，所以沒加說明。
- **SFZ／sfizz 那條路（寫 MIDI 檔）：**粗測力度、踏板、重複觸發都正常，但那是 mido 與 sfizz 的責任，不是 Tactus 的程式碼。
