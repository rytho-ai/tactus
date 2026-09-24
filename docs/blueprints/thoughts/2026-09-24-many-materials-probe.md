# 多素材 probe：現有 per-file 固定是否撐得住大量音檔

> 2026-09-24 · Paul 要求用 fresh agents 驗證「素材很多時需要新機制」的必要性。
> 證據回饋給 Paul 的待決問題：是否新增 ref 產生器（例如 `material add --python`）或
> 資料夾整包的素材身分。判定規則在試驗前寫定，全文收在本文件末。

## 結論

**以一件作品 14–21 個素材的規模，不需要新機制。** 三個 fresh sonnet agents 只讀
`tactus-authoring` skill，全部做到三件事：

- 一次批次 `tactus material add`，把印出的 ref 貼成具名常數；
- 所有讀檔都經過 `material()`；
- 兩輪（建立、換素材）共六次交付，都沒有出現與素材相關的失敗。

這落在預先寫定的規則 3。ref 產生器與整包素材身分目前沒有存在理由。

這次真正值得處理的發現與素材數量無關：**四個 agent 各自重寫了「讀檔、重採樣、轉立體聲」**
（三次 probe，加上先前的 [fresh-agent trial](2026-09-24-fresh-agent-authoring-trial.md)）。

## 方法

- **形式：**behavior probe，只有一個條件（現有工具）。N = 3 個 fresh sonnet agents，各自有
  隔離的 pool 與工作目錄，prompt 完全相同。
- **Fixture：**從 Rytho library 多個 pack 取出 69 個 one-shot，分成 kicks 15、snares 15、
  hats 20、percs 12、claps 8，其中四個檔案的 rate 或聲道不同（48／96 kHz、mono）。
- **第一輪任務：**90 BPM、16 小節 boom-bap。要從整個 pack 試聽挑 kick／snare，hats 至少輪流
  使用 4 個，perc 每一下從整個 percs 資料夾以固定 seed 隨機挑選，下半段 clap 疊在 snare 上。
  交付 mix、drums-core、hats、perc。
- **第二輪修改：**換成較暗的 kick／snare，並把 perc 限制在一半的檔案。
- **判讀依據：**直接讀 code 與 receipt，而不是 agent 的自我回報。

## 結果

| | Agent 1 | Agent 2 | Agent 3 |
|---|---|---|---|
| 讀檔只經過 `material()`，`render` 內無路徑或 glob | ✓ | ✓ | ✓ |
| 兩輪成功 | ✓，皆一次成功 | ✓，皆一次成功 | ✓，第一輪因自行修正 mix/stem 電平多跑一次，與素材無關 |
| ref 進入 source 的方式 | 一次 `add` 20 檔，貼成常數 | 一次 `add` 20 檔 | 分三批 `add`，共 21 檔 |
| 自寫 ref 產生器 | 無 | 無 | 無 |
| 素材相關失敗 | 0 | 0 | 0 |
| 第二輪換素材 | 再 `add` 2 檔，改 2 行、刪 6 行 | 同左 | 同左 |
| receipt 的 materials 數量（兩輪） | 20 → 14 | 20 → 14 | 21 → 15 |

三個 agent 都用行尾註解記下每個 ref 對應的原始檔名，並自行表示這在 20 個檔案的規模下不算負擔。
沒有 agent 把 refs 存在 `.py` 以外的檔案（預先登記的觀察項 X 未發生）。

## 發現

1. **讀檔 adapter 反覆出現。**三個 agent 都寫了「`material()` → `sf.read` → 重採樣
   （`scipy.signal.resample_poly` 或 librosa）→ mono 轉 stereo」。寫法各異，但做的事相同。
   [second production plan](../plans/2026-09-24-second-production-through-run.md) 把共用讀取
   adapter 的條件設為「第二件作品重複同一套讀檔邏輯」，這個條件已經成立。這屬於 A2 的讀檔
   銜接，與素材數量無關。仍需決定哪些選擇留給作品：重採樣演算法、聲道轉換方式、是否截取區段。
2. **receipt 會記錄非 render 的 scratch script。**Agent 2 在作品目錄放了用 glob 掃 pack 的
   `audition.py`，`render` 沒有 import 它，但 `source_files` 仍然記錄了它。這不影響聲音，只是
   紀錄範圍比實際依賴大。skill 已補上說明，runtime 暫不改動。
3. **skill 缺口（已修正）：**
   - `python_packages` 的形狀未寫明；
   - 沒提醒 pack 內 rate 與聲道常不一致；
   - 範例路徑預設讀者身在 repo 內。

## 未驗證

- 只測到每件作品 21 個素材。數百個素材，或依名稱或標籤從整包挑選的情境，才是整包素材
  身分可能有價值的地方，本次沒有涵蓋。
- 每個條件 N = 3，只用 sonnet。Paul 決定不測 haiku。
- Agent 沒有聽覺，挑選 kick／snare 靠檔名與頻譜量測。音樂品質尚待 Paul 聆聽。

## 預先登記的判定規則（試驗前寫定）

1. 任何一次試驗在不經 `material()` 的情況下讀取 pack 檔（runtime 以路徑或 glob 讀取），
   代表現有固定方式在大量素材下撐不住，整包層級的機制有理由存在，採用前需要 A/B。
2. 否則，若 3 次中至少 2 次各自寫了產生器或對應步驟，或出現至少 2 次與素材相關的失敗，
   代表共用產生器（`material add --python` 或同類）作為便利功能有理由存在。
3. 否則，若全部完成、固定完整且額外負擔很小，不需要新機制；若有反覆出現的模式，最多補一行
   skill guidance。
4. 結果不符合以上任何一條時，判定為不明確，不做任何東西。

觀察項 X（refs 存在 `.py` 以外的檔案）不論判定結果都另外回報。
