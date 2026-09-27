# `tactus.timing` 出貨後：缺口 probe 與重複程式碼分析

> 2026-09-27 · `tactus.timing` 出貨於 `943c9b2`（[plan](../plans/2026-09-27-tactus-timing.md)）。
> Paul 先問「現代音樂的時間表示還有什麼沒涵蓋」，再要求「確認 agent 搭配 tactus + 原生 python 能不能做到」，
> 最後問「有沒有什麼很常重複的地方」。判定規則在試驗前寫定（scratchpad `probe-gaps/PREREGISTERED.md`）。

## 結論

1. **出貨模組檢查通過。**兩個全新 sonnet Agent（D1、D2）只靠 skill 學會 `tactus.timing`，
   重跑設計比較第一輪的題目，時間項目全部正確。
2. **缺口都不需要新工具。**網路調查找到的常見缺口（quantize strength、以音符值換算 delay 毫秒、
   可重現的 seeded humanize）加上 live-coding 式 pattern（Euclidean 加旋轉、polymeter、
   「每 n 小節反轉／位移」），三個 Agent（G1–G3）用 `tactus.timing` 加原生 Python 三輪都做對。
   依事先規則，這些項目不加 helper。
3. **但 Agent 會反覆手寫同一批機械程式碼，而且寫法彼此不一致。**這不是正確性失敗，
   是「重複 + 行為分歧」：今天每個都對，換個情境就可能各自出錯。是否要收成 helper，留給 Paul 決定。

## 缺口 probe

- **題目：**48 kHz，8 小節 4/4，96 BPM，某小節起突變成另一個 BPM（兩輪參數不同）。要交出的 marker 軌：
  - 小節線；
  - 以 strength 部分量化的 16 個演奏拍點；
  - 依音符值（附點八分、三連音）在 BPM 下換算的 delay；
  - k/16 Euclidean，每 n 小節旋轉一格；
  - 每 p 個十六分音符一擊的 polymeter；
  - 每 n 小節反轉的 pattern；
  - 高斯 humanize 的 shaker（標準差 σ ms），重新 render 必須逐位元相同。
- **評分：**`check.py` 對照 `truth.py` 的獨立公式（先用參考解驗證過），拍點誤差 ≤1 frame；
  shaker 看偏移的標準差、平均與最大值；可重現性用 Agent commit 的原始碼重 render 比對 sha256。
- **結果：**G1–G3 三輪全部通過。每個 Agent 每輪約 80–108k tokens、3–6 分鐘。
- **題目的兩個瑕疵：**
  - 第二輪的反轉 pattern `x.x.xx.xx.xx.x.x` 是回文，反轉等於沒做事。因此加了第三輪：
    非回文的 `x..x..x...x.x...`，3 的倍數小節反轉、4 的倍數小節位移 +2。三個 Agent 都做對。
  - 題目沒定義 humanize 後落在 frame < 0 的拍點怎麼處理：G1 丟掉、G2 與 G3 夾到 0。
    G1 因此少一擊，這算題目沒寫清楚，不算 Agent 的錯。
- 評分時的真值曾誤把第 8 小節結尾（在音檔之外）算進小節線，已修正為 range(8)，與 Agent 無關。

## 重複程式碼分析

一個 sonnet Agent 讀了本 session 的 10 個 probe 作品（包含 D1 與 G1–G3），
找「機械性、每個作品都要寫、而且寫法不同」的程式碼：

| 重複的東西 | 出現 | 分歧 |
|---|---|---|
| 在 buffer 上蓋 marker／impulse | 10/10 | 三種語意：相加、取最大、覆蓋；超出範圍時有的丟掉、有的夾住 |
| 讀取 sample 並重新取樣 | 7/7 | 聲道處理不同；有的修剪起音前的靜音、有的不修；D1 寫死 160/147 的比例 |
| 調 gain 到目標 RMS，再加 limiter | 7/7 | 有的在 limiter 前量、有的在後面量 |
| dB 與線性值互換 | 7/7 | 寫法一致，只是每次重寫 |
| 把 clip 放到某個 frame | 只有 G1 用 `timing.place` | 其他作品嫌它每次複製 buffer，自己寫就地版本；D1 的版本遇到負的 frame 會從尾端繞回來（bug） |
| 音符值換算毫秒 | G1–G3 | G1 重抄一份 tempo map；G2、G3 用 bpm 的浮點數相等判斷區段 |
| quantize 的平手規則 | G1–G3 | G1、G2 用 Python `round`（偶數優先），G3 用 `floor(x + 0.5)` |

以下已經收斂，不必處理：Euclidean 的算法、seeded RNG 的用法、各作品的創意表格（pattern、和弦）。

## 可能的下一步（未決）

依「重複 + 分歧」這個標準，候選 helper 是：

- 有明確語意的 marker 蓋印；
- `quantize(beat, grid, strength)`，由它決定平手規則；
- 依目前 tempo 把音符值換成秒數；
- 帶聲道規則的讀取加重新取樣；
- 調到目標 RMS 再做安全處理；
- `place` 的文件寫清楚複製成本，或提供就地版本。

這些都還沒有正確性失敗的證據。要加的話，先用 probe 證明能減少分歧或錯誤，再動手。
