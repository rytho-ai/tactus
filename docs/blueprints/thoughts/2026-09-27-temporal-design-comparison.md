# 時間工具設計比較：常見音樂時間變化情境

> 2026-09-27 · Paul：「想辦法找到 temporal abstraction 最好的設計」，並要求用常見的音樂時間變化來測
> （BPM、突變與漸變、swing、groove），「不一定要包含到 tool 裡」。判定規則在試驗前寫定
> （scratchpad `probe-feel/PREREGISTERED.md`）。
> 前兩次 probe（[精確題](2026-09-27-temporal-helpers-necessity-probe.md)、[高負荷](2026-09-27-temporal-helpers-load-probe.md)）
> 的題目都沒有突變、曲線漸變或 groove。

## 結論

**v3 是最好的設計，而且證明有必要。**兩個 v3 Agent 三輪都零錯誤。沒工具的組共錯 7 項，
只有時間換算的 v2 也錯 7 項。token 三組相近：A 230k、B 207k、C 228k。創意指標沒有差別，
三組的 Agent 大多都沒做人性化偏移。

兩種錯誤的原因不同，各自說明了一件設計上的事：

- **沒工具（A）：從 0 數還是從 1 數的混淆。**題目以音樂人的習慣寫「backbeat 是第 2、4 拍」「第 3 拍的後半拍」。
  兩個 A Agent 的 snare 都放對，大鼓卻都放在第 4 拍的後半拍（0-based 3.5 而不是 2.5），
  三輪都沒發現，因為它們自己驗證時用的也是同一個錯的位置。四個有工具的 Agent 都放對了；
  工具文件開頭寫明「beats are 0-based quarter notes」，這可能就是差別所在。
- **v2（B）：缺少曲線，只能近似。**v2 只有依拍位置線性的漸變。兩個 B Agent 分別用
  「幾乎重疊的兩個點」模擬突變，用很多小段直線近似 cosine 漸慢，第三輪又近似「依時間線性」的漸快，
  小節線因此偏了 1～24 個 frame（最多 0.5 ms）。聽不出來，但每一輪都不符合規格。
  v3 只要寫 `"smooth"`、`"ramp-time"` 或一個 step 點就完成了。

所以：常見的時間變化（step、依拍或依時間的線性漸變、平滑曲線、swing、groove）應該內建，
而且拍子的計數方式要寫清楚。swing 與 groove 只提供計算方式，數值由 Agent 決定，並沒有讓節奏變死板。

## 設計

- **三組**（每組 2 個 fresh sonnet Agent，prompt 除了一行 helper 說明外完全相同）：
  - A：沒有工具；
  - B：tclock v2（tempo map，只支援依拍線性漸變；拍號、ms 偏移、絕對拍、bars、span）；
  - C：tclock v3（v2 再加上 step、`ramp`、`ramp-time`、`smooth` 四種速度形狀，以及 `swing()`、`Groove`）。
- **第一輪：**
  - 5 秒自由前奏；
  - 96 BPM，含一個 7/8 小節；
  - 第 13 小節突變到 120，再依拍線性漸快到 132；
  - climax 之後接 cosine 漸慢到 80；
  - hi-hat 分三段 swing（56%／直拍／60%）；
  - 第 1～12 小節的 groove：backbeat snare 晚 12 ms、第 3 拍後半的大鼓早 8 ms；
  - 另有製作要求：素材固定、marker、音量、濾波與 reverb、片段、commit。
- **第二輪（一次多項）：**突變延後一小節、swing 改 62%、snare 改晚 18 ms、bass −2 dB、pad 變暗、climax 片段。
- **第三輪（一次多項）：**
  - 插入 2 小節 breakdown，這次明確寫出新的小節編號；
  - 漸快改成依時間線性；
  - 漸慢改到 72；
  - climax 的鼓 +1 dB；
  - 前奏改成 3.5 秒；
  - climax 片段。
- **評分：**`check.py` 讀取音檔。小節線對照 `truth.py`，它用 scipy quad 數值積分，和 v3 交叉核對過三輪、
  逐 frame 一致。另外檢查三段 swing、groove 的 snare 與大鼓 push、各項音量與音色、片段範圍、
  修改點之前的內容沒有移動，以及不在格子上的比例。評分腳本先用參考解答驗證過。

## 結果（依檔案核對）

| | 時間錯誤 | 製作錯誤 | 合計 | 最終 tokens |
|---|---|---|---|---|
| A1 | 3（三輪大鼓 push 都錯一拍） | 1（climax 的鼓只 +0.43 dB） | 4 | 189k |
| A2 | 3（同上；它的大鼓在 3.5 −8 ms，所以評分找不到 2.5 附近的大鼓） | 0 | 3 | 270k |
| B1 | 3（三輪的小節線都有近似誤差，最多 24 frames） | 0 | 3 | 208k |
| B2 | 3（同上，1～2 frames） | 1（climax 的鼓只 +0.28 dB） | 4 | 205k |
| C1 | 0 | 0 | 0 | 218k |
| C2 | 0 | 0 | 0 | 237k |

- 所有 Agent 在修改時都沒有動到不該動的部分，也都保留了已交付的 run（這次 prompt 有明寫）。
- A2 在第三輪用 `np.clip` 把 climax 硬切到 ±0.98。這不在評分項目裡，但 skill 已說明這樣會隱藏失真。
- 三組都有 Agent 碰到 Pedalboard `Limiter` 吃掉「+1 dB」的問題；有兩人最後差距沒做到位。
  這和時間工具無關。

## 下一步（待 Paul 決定）

把 v3 做成 Tactus 的可選模組 `tactus.time`：
- 保留 v3 的 API：`Clock`、tempo 形狀、`swing`、`Groove`、`frame_of`、`place`、envelope；
- 補上測試：與數值積分比對，以及長時間不漂移；
- skill 加一小段說明，主要講清楚拍子從 0 開始數；
- 拿 dogfood 3 改用它，確認輸出不變；
- 再做一次 fresh-Agent 驗證。
