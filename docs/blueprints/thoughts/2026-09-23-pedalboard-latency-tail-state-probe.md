# Pedalboard effect-chain latency, tail, and state probe

這份證據回到 Tactus 是否能先以 Pedalboard 支撐小型 offline effect chain 的問題；它不宣稱正式 runtime 已完成。測試用 48 kHz stereo、2 秒脈衝音訊，一條乾聲路徑平行於「受控 128-sample latency VST3 → 真實 mda Delay VST3」。比較完整 render、局部重播、冷啟動，以及同一顆效果器重複使用。事前規則固定在 scratch 的 `preregistration.md`；產品程式碼未改，沒有付費模型呼叫。

## 結果

| 檢查 | 觀察 |
| --- | --- |
| Latency | 受控 plugin 回報並實際延遲 128 samples。Pedalboard 的單次 `reset=True` 處理把直接聲對回原位置；新 plugin 的 `reset=False` 輸出晚 128 samples。兩種平行混音的最大逐 sample 差為 `0.53466`。 |
| 分段補償 | `reset=False` 的整段處理與不規則邊界的分段處理差異為 `0`。在串流輸入末端補 128 個零，輸出整體向前對齊 128 samples，與單次 `reset=True` 處理差異為 `0`。這是補充診斷，不是 Pedalboard 自動補償所有串流路徑的證明。 |
| Region context | 從歌曲開頭重播至區段尾端，再截取 `[15000, 80000)` 的 audition，與完整 render 同區段差異為 `0`。直接從第 15000 個 sample 冷啟動則差 `0.33066`，漏掉先前脈衝的回音。 |
| Tail | 請求區段在第 40000 個 sample 結束；後續窗口中的尾音最大值為 `0.27555`，不能在 40000 直接截斷並宣稱完整。 |
| State | 不同 fresh instances 重跑差異為 `0`；同一條 chain 每次用 `reset=True` 重跑差異也為 `0`。故意用 `reset=False` 連續跑兩次，第二次與第一次差 `0.00954`，證明前一次的效果器狀態會污染下一次。 |

四項事前判定均通過：受控 latency 的回報與實際行為一致、補償後直接聲與乾聲對齊、保留前置脈絡的局部 audition 與 full render 一致且有可測尾音、乾淨重跑一致而髒狀態可測出差異。

## 判斷與邊界

這個小型 chain 的 latency、tail 和 state 可由 Pedalboard 加明確的 offline 排程處理。關鍵是分清單次 `reset=True` 與分段 `reset=False`：前者在本測試中由 Pedalboard 自動補償 plugin latency；後者需要 Tactus 在串流結果上明確安排補零與對齊。Region audition 也必須取得區段開始前的 DSP 脈絡，並按需求保留區段後的 tail。不能把 cold-start region 當成完整歌曲的等價切片。

這不驗證多條複雜路由、plugin 動態改變 latency、多顆有 latency 的 plugin、任意商用 VST、正式 Tactus audition API、external sidechain 或跨平台行為。因此結果支持延續 [Pedalboard + helper 的工作方向](2026-09-23-effect-hosting-boundary.md)，不支持宣布一般 effect chain 已完成。

第一次跑 SDK validator 時，受控 fixture 因固定讀取兩個 channel，在 mono layout 測試中崩潰。修正 fixture 的 channel 邊界與 silence flag 後，validator `-q` 以 exit 0 完成；同一份 `results.json` 與重跑結果逐位元相同。這是測試工具修正，不是 Pedalboard host 修正。

一次性 harness、受控 VST3 source 與原始測量保留在 `/tmp/tactus-pedalboard-chain-probe.N5ZUqS/`，尚未封存；`run_probe.py` 可以重印數據。Pedalboard 版本為 `0.9.25`。
