# 用 Agent 熟悉的寫法做 Pattern：純 Python、NumPy 格子、Tidal/Strudel 三組對照

> 2026-09-27 · Paul：「那你可以幫我重做幾個 probe 來測試看看這種 pattern 是否有價值，另外你可以 reference agent
> 擅長的寫法讓他不需要學太多東西（ex numpy or tidalcycle strudel supercollider 等等）」；
> 「我的意思是你在發明 pattern 想法時可以參考 agent 本來就熟悉的語法」「不是叫你用套件」。
> 判定規則在試驗前寫定（scratchpad `probe-pattern2/PREREGISTERED.md`）。
> 前一次 probe（[自創 API 的 Pattern 模組](2026-09-27-pattern-helpers-probe.md)）沒有幫助。

## 結論

**依事先規則，兩種熟悉寫法都「有幫助」，但證據很薄，而且真正的價值很窄。**

| 組別 | 錯誤（五輪） | tokens（五輪累計） | 修改輪動到的行數 | 最後 song.py 行數 |
|---|---|---|---|---|
| 純 Python N1 / N2 / N3 | 0 / 0 / 2，共 2 | 128k / 123k / 119k，平均 123k | 157 / 133 / 93，平均 128 | 216 / 222 / 180，平均 206 |
| NumPy 格子 G1 / G2 / G3 | 0 / 0 / 0 | 119k / 111k / 127k，平均 119k | 174 / 90 / 155，平均 140 | 177 / 127 / 184，平均 163 |
| Tidal/Strudel T1 / T2 / T3 | 0 / 0 / 0 | 135k / 124k / 130k，平均 130k | 125 / 93 / 103，平均 107 | 145 / 129 / 149，平均 141 |

- **錯誤：**純 Python 組唯一的錯，是 N3 在第五輪把 Tidal 的 `(3,8,2)` 旋轉方向做反了。Tidal 是往左轉，它往右轉。
  ghost 要避開 kick 的位置，所以也跟著錯，算 2 個錯。兩個工具組都把這個慣例寫進 `euclid` 或 mini-notation 裡，所以沒踩到。
  依規則「少 2 個錯」剛好成立，但這是**一個 Agent 的一次失誤**，不像先前 0/1-based 拍子的錯那樣在每輪反覆出現。
- **token：**NumPy 組少 3%，Tidal 組多 5%，都在雜訊範圍內。
- **修改量：**Tidal 組少 16%，沒到 30% 的門檻；NumPy 組反而多 9%。
- **程式碼長度：**Tidal 組最短，比純 Python 短 32%；NumPy 組短 21%。

依事先規則，兩組都「有幫助」（錯誤少 2 個），token 差距 9%（小於 10%）算平手，所以兩種都要回報。

## 真正幫上忙的是「慣例」，不是 pattern 系統

- 三個純 Python Agent 都自己實作了 Bjorklund，程式碼裡都寫著「照 TidalCycles/Strudel 的 `bd(k,n)`」，
  其中一個把旋轉方向做反了。兩個工具組只是呼叫已經定好慣例的 `euclid(k, n, r)` 或 `x(k,n,r)`。
- 前一次 probe 用的是自創的名字，Agent 得先學；這次用 Agent 熟悉的語法，第一輪的 token 三組都差不多
  （81k／79k／84k），學習成本確實消失了。但熟悉的語法也沒有讓修改變少多少。
- 各組三個 Agent 都用到的操作：
  - NumPy 組：`euclid`、`cycle`、`seeded_mask`、`tile`、`to_frames`；
  - Tidal 組：`mini`、`realize`、`rev`、`stack`、`velocity`、`degradeBy`、`early`、`exclude`（`lastOf`、`when` 各 2/3）。

## 題目與有效性

- **題目：**8 小節、5 個聲部，用鼓手或 live coder 的說法描述，例如「Euclidean (3,8)，照 TidalCycles 的定義」「第 2、4 拍」「`x ~ x` 跨小節循環」。
  之後四輪小修改：
  - kick 移一個八分音符；
  - perc 換成 5 步循環，hat 每 3 小節倒放；
  - bar 8 換成三連音，每個 clap 加 32 分音符的 flam；
  - 延長到 16 小節，kick 每小節交替使用 Tidal 的 `(k,8,2)` 旋轉。

  每輪都規定哪些聲部必須逐位元不變，九個 Agent 全部做到，包括 ghost 在改 perc、改 clap 時保持不變。
- **防止洩題：**兩個原型的說明文件原本列了剛好是題目要用的 Euclidean 展開，派出前已改成無關的數字。
- **評分程式：**先用三組各一份參考解驗證（五輪零錯誤、輸出逐位元相同），8 種故意做錯的版本也都抓到。
- **限制：**
  - 旋轉方向的錯只出現一次，要確認是穩定的風險，需要更多樣本；
  - 沒有人來讀程式碼、評估可讀性；
  - 沒測 SuperCollider 風格。

## 可能的下一步（未決，交給 Paul）

1. **最小整合：**只把「有慣例、容易做錯」的部分放進 `tactus.timing`：
   - `euclid(k, n, r)`：Bjorklund，照 Tidal 的旋轉方向；
   - 跨小節的循環；
   - 不會因延長而重洗的 seeded 機率。

   這對應到三組都用上的共同部分，也符合「機械性、有慣例、會分歧」的一貫標準。
2. **Tidal 風格的 mini-notation：**程式碼最短、修改最少，但要維護一個小語言，而且 `every` 的 Strudel 語意
   （從第一小節算）跟音樂人說的「每 n 小節」不同，本身就是一個陷阱。
3. **不整合：**以「一次失誤」作為證據太薄，維持 C1 關閉。
