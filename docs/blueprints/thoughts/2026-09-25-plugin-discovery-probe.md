# 外掛參數刻度：以 describe 查詢是否足夠（fresh-Agent 驗證）

> 2026-09-25 · 延續完整歌曲 dogfood 2。那次 Agent 把 OB-Xf 0–100 % 的 sustain 設成 1.0，
> 另外振盪器預設是關閉的，結果 pad 小了約 40 dB。判定規則在試驗前寫定
> （scratchpad `probe-describe/PROTOCOL.md`）。

## 結論

**以查詢為主的解法目前已足夠。**這個解法包括：

- `fx.describe`／`format_table`，列出目前值、單位、範圍與標籤；
- `set_param` 的錯誤訊息附上範圍；
- skill 要求逐段量測音量，取代「峰值大於 0」。

兩個 fresh sonnet Agents 在兩種外掛上都沒有設錯刻度：Dexed 完全不回報單位，OB-Xf 有 64% 的參數回報單位。
兩人的逐段音量都落在目標的 ±1 dB 內，兩人都先用 `describe` 查看參數才設定。
因此不需要依範圍極端值發出警告，也不需要強制指定單位。

## 為什麼不強制指定單位

先調查了本機外掛回報單位的比例：

| 外掛 | 有單位 | 無單位的參數長什麼樣 |
|---|---|---|
| OB-Xf | 64% | 開關、文字選項 |
| Dexed | 0% | 75% 是沒有單位的數值範圍，例如 0–99、-1–1 |
| CardinalSynth／FX | 1% | 98% 是 0–127 的 MIDI CC 參數 |
| DrumCraker | 0% | `master_volume` 範圍 -60–12，沒有標示 |

單位 metadata 因外掛而異，強制指定單位只對少數外掛有用。每個外掛都會回報名稱、範圍與目前值，
所以通用的解法是查詢，而不是強制。

## 結果（依音檔與程式碼核對）

任務：在 16 小節 fixture 上用 Dexed 做 bass（每小節約 −18 dBFS），用 OB-Xf 做 pad
（第 9–16 小節約 −24 dBFS，第 1–8 小節靜音）。

| | Dexed 刻度 | OB-Xf 刻度 | bass 各小節（dBFS） | pad 第 9–16 小節（dBFS） | pad 第 1–8 小節 |
|---|---|---|---|---|---|
| A | 從範圍讀出 output level 0–99（設 99），並看出 cutoff 是 0–1 的比例 | 全部帶 `unit=`；打開預設為 `-inf` 的 osc 2 | −18.4…−18.2 | −24.9…−22.3 | 靜音 |
| B | 同樣從範圍判斷；還掃描 algorithm 1–32，自行找出 FM 路由 | 同上 | −18.0…−17.9 | −24.4…−23.4 | 靜音 |

- A 的第一次 render，bass 比目標小了 20 dB，是靠逐段量測發現並修正的。這正是 skill 新說明的
  用途。
- 兩人都自行發現 OB-Xf 的 osc 2 預設關閉，因為 `describe` 的目前值會顯示出來。
- Dexed 的 algorithm 路由無法從參數表得知，B 用掃描自行查出。這屬於外掛本身的領域知識，
  不列為 Tactus 的缺口。

## 限制

N = 2，只用 sonnet，只測了兩個外掛；VST3 效果器沒有測。

## 精簡 skill 後重測（2026-09-25，skill `fb9fca1`）

skill 精簡成只講怎麼用 Tactus，拿掉了「OB-Xf 振盪器預設關閉」、各段音量範例程式碼和外掛的用法說明。
用同一個任務、同一個起點，派兩個 fresh sonnet Agent（c、d）重測，判定規則事先寫定（`PROTOCOL.md`）。

- **兩人都通過，沒有退步。**兩人都沒有設錯刻度：Dexed 都照 0–99 設定，OB-Xf 的第二個振盪器都自己打開了。
  bass 每小節都在 −18.0 dBFS 左右；pad 第 9–16 小節 c 是 −22.3～−25.8、d 是 −21.2～−29.4，
  第 1–8 小節都是靜音。兩人都先用 `fx.describe` 看過參數。
- **精簡時弄丟的一個細節：**d 直接把 `tool()` 回傳的 `Path` 傳給 `load_plugin`，出現
  `TypeError`（它需要字串）。舊版 skill 的範例有 `str(...)`，已經補回說明。
- 成本：c 165k tokens／9.9 分鐘，d 163k tokens／7.5 分鐘；上一輪是 145k 與 165k。
