# Fresh-Agent authoring trial：只靠 `tactus-authoring` skill

> 2026-09-24 · Paul 要求直接派 fresh sub-agent 測試。對應盤點 A8 的驗收，以及
> [second production plan](../plans/2026-09-24-second-production-through-run.md) step 5。
> 這是單次觀察，不是可靠度證明。

## 結論

一個 fresh sonnet Agent 只讀 `skills/tactus-authoring/SKILL.md`，沒有讀 repo 的 source、examples 或 docs。
它從零完成一首 16 小節的 lo-fi groove：固定兩個真實 one-shot 素材，交付 mix、drums、bass、pad，
並產生兩個只差 bass 音量的候選。之後接到製作人的修改需求，第一次就完成一輪結構修改。
程式大致符合 functional 紀律：

- 所有 stage 都建立新 buffer，沒有修改輸入陣列或 module state。
- `render` 由上而下就是處理順序。
- 每個 stage 都有名稱。
- 修改需求只動到相關的 stage。

唯一的失敗是 `from tactus import material` 拿到同名 submodule，不是 `material()` 函式。
這是 runtime 的 bug，不是 skill 或 Agent 的問題。Agent 回報後，已將輸出 store 模組改名為
`tactus/store.py`（commit `0d108e3`）。worker 在移植範例時也獨立回報了同一個 bug。

## 過程

- **第一輪任務：**84 BPM、16 小節、kick／rim 加 swing、minor 進行的合成 bass 與 pad。
  pad 要加 delay／reverb，drum bus 要加 saturation／compression，最後交付 mix 與三個 stems，
  以及兩個 bass 音量候選。
  - `tactus material add` 匯入兩個 sample，把 ref 貼進 source。
  - 第一次 `tactus run` 因上述 import bug 失敗，Agent 自行找到 `tactus.inputs.material` 並繞過。
  - 之後兩個候選都成功。Agent 自行確認 drums／pad stems 在兩個候選間 bit 相同，只有 bass 改變。
- **第二輪修改：**保留 bass 較小的版本、讓 pad 更暗更暖、在最後一小節加 fill、第 1–4 小節去掉 ghost notes。
  - 加入 `lowpass_fx`（作用於 dry pad 與 reverb IR）。
  - `drum_hit_times` 改寫，新增 `ghost_start_bar` 與最後一拍的 fill。
  - 一次 run 成功，receipt 正確列出兩個素材與有效參數。

## 觀察

- **時間換算重複：**`beat_dur`、`bar_dur` 與 `int(round(t * sr))` 在四個函式中各自重算。
  這是 A1 temporal helper 的實際證據，屬於「重複數學」而不是錯誤。
- **接受候選靠 source default：**skill 的做法是把接受的值寫回 default，Agent 照做。
  這一輪 default 恰好已是被選的值，所以沒有真正測到「接受候選時修改 source」。
- **作者自訂的 mix 限制：**`safety_clip` 實際上是 peak normalization，因此改 bass 音量也會
  連帶改變 mix 中其他元素的電平。這是創作選擇，validator 不應介入，但值得在聆聽時注意。
- **未涵蓋：**`tool()`（沒有外部執行檔）、多檔作品、失敗診斷路徑、較長作品的執行時間。

## 未驗證

沒有和「沒有 skill」的條件對照，也沒有重複試驗。先前 fixture 條件（48-track 的
imperative 失敗）的規模比這次大。音樂品質尚待 Paul 聆聽。
