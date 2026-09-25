# 讓 Agent 在 Tactus 裡好好用 Pedalboard：四輪迭代

> 2026-09-25 · Paul 要求多迭代幾輪，找出如何讓 Agent 在 Tactus 中妥善使用 Pedalboard（效果器、
> VST3 hosting、automation）。延續 [reverb 盲聽](2026-09-25-reverb-blind-ab.md) 與先前的
> [segmented automation](2026-09-23-pedalboard-segmented-automation-probe.md)／
> [latency-tail-state](2026-09-23-pedalboard-latency-tail-state-probe.md) probes。
> 協定在第 0 輪之前寫定。

## 結論

A6 v1 由以下幾部分組成：

- Pedalboard 列為 base dependency；
- skill 新增「Effects and plugins (Pedalboard)」一節；
- 新增三個小 helper：`tactus.fx.set_param`、`process_automated`、`render_instrument`。

四輪、八個 fresh sonnet Agents 的結果：

- 每一輪功能都完成：尾音保留、automation 平順、VST 有聲音；
- 平均成本從約 183k 降到約 137k tokens；
- 「自己重寫機械工作」與「靜默出錯」逐輪消失。

helper 的內容限於機械部分（單位換算、分段順序與 reset、延遲補償、暖機），曲線與音色的
選擇仍然由作品決定。

## 協定

- **Fixture。**16 小節 lo-fi，84 BPM。
- **固定任務：**
  1. pad 改用 Pedalboard 效果，並讓尾音在最後一小節之後自然響完；
  2. 第 9–16 小節 low-pass 從 400 Hz 掃到 8 kHz，同時 reverb 逐漸變濕；
  3. 用 OB-Xf VST3 在第 9–16 小節加一條 lead，release 要響得出來。
- **判讀。**每輪 2 個 Agent，依輸出音檔與 code 判讀：
  - C1：尾音；
  - C2：automation 的狀態連續、沒有 click；
  - C3：lead 有聲音、設定寫在 source、身分可追溯。

## 各輪結果

| 輪 | 條件 | tokens（兩個 Agent） | 自己重寫的東西 | 靜默或實際錯誤 |
|---|---|---|---|---|
| 0 | 原 skill，沒有 Pedalboard 指引 | 191k、176k | 兩人都寫了分段迴圈、補尾音、參數對應、`.so` 身分、轉置 | 環境：`--with` overlay 無法進入 worker（是 harness 的問題，由加入依賴解決） |
| 1 | 加入 skill 指引 | 139k、160k | 兩人仍各自寫參數對應 | r1b 參數匹配忽略單位（10 ms 對上「9.97 s」，產生 10 秒 attack），已自行修正；**r1b 交出的 lead 在第 1–8 小節有 0.09 的起始雜訊，沒有察覺** |
| 2 | 加入 `set_param`、`process_automated` | 134k、149k | r2b 遇到 `semitones` 單位不支援，退回自己寫 | r2a 發現 OB-Xf 起始雜訊並自行歸零 |
| 3 | 加入 `render_instrument`、任意單位比對、bundle 路徑範例 | 118k、156k | 無 | r3b 照 skill 中已經過時的「instrument 輸出要 `.T`」再轉置一次（skill 自相矛盾，已修）；兩人的 lead 在第 1–8 小節峰值都是 0.0 |

C1 到 C3 每一輪兩人都通過：尾音延伸 3.5–6 秒並衰減到約 0；分段邊界的二階差分峰值是
中位數的 10–12 倍，屬正常訊號範圍；lead 都有聲音，身分都透過 `tool()` 記錄 `.so`。

## 找到並驗證的機制問題

- **OB-Xf 改參數後的起始雜訊。**改過參數後的第一次 render，在任何音符之前就有峰值約
  0.07 的聲音。預設音色沒有這個現象。先做 1 秒靜音暖機，再以 `reset=False` render，
  峰值降為 0.0；若暖機後用 `reset=True`，雜訊會再出現。六個 Agent 中有兩個交出帶雜訊的
  lead。`render_instrument` 內建了暖機。
- **參數單位。**4/4 個 Agent 各自寫了最近值對應，其中一個錯把 ms 對到 s。`set_param` 在
  已知單位族（ms／s、Hz／kHz、cents、dB、%）內換算，其他單位則依標籤自己的單位比對。
- **VST 路徑有兩種。**`tool()` 要的是 bundle 內的 `.so`，`load_plugin` 要的是 `.vst3`
  資料夾。四個 Agent 都在這裡卡過，skill 改為附上兩行範例。
- **OB-Xf 不可逐 sample 重現。**同一份 source 重新 render，lead 的 hash 不同（RMS 差約 0.04）。
  skill 提醒這類作品要以封存的音檔為準，不能用 hash 比對。
- **`LowpassFilter` 只有 6 dB/oct。**做明顯的掃頻應該用 `LadderFilter`。

## 未驗證

- `process_automated` 的延遲補償只用 fake chain 做了單元測試。實際回報延遲的 VST3 效果器，
  搭配首段 `reset=True` 時是否會重複補償，尚未用真實插件驗證。
- 只測試了 OB-Xf，其他插件的參數標籤格式可能不同。
- 沒有測 VST3 效果器（只測了 instrument），也沒有測外部 sidechain（已知不支援）。
- 每輪 N = 2，只用 sonnet。第 3 輪修正 skill 矛盾後沒有再重跑。
- Fixture 的 pad 是正弦波，掃頻的可聽度無法以頻譜重心量化；automation 改以 code 與 click
  proxy 驗證。
