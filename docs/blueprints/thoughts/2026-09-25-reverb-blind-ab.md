# Reverb 盲聽 A/B：Pedalboard 內建 vs Agent 自寫

> 2026-09-25 · 回答 A6 的前提問題：Pedalboard 的內建效果器是否明顯比 Agent 自寫的 DSP 好。
> 判定規則在 render 之前寫定。

## 結論

**Paul 盲聽排序：Pedalboard（X）> Agent 第一版（Y）> Agent「改良版」（Z）。**

- 符合預先規則 1：A6 第一版採用 Pedalboard。
- Paul 另外指出，Pedalboard 的意義還包括 **VST3 hosting**，讓 Agent 能使用插件生態，這一點也列入
  A6 的範圍。

**Agent 的「改良」讓聲音變差。**在完整歌曲 dogfood 中，Agent 用 impulse response 的
peak-to-median 指標「證明」改良版比較平滑，實際聆聽卻排在最後。這和同一次 dogfood 中
自製區段預覽的問題是同一類：Agent 聽不到聲音，只能用數字自我驗證，而數字合理不等於聲音好。
音色類的處理應優先交給成熟的工具。

## 方法

**素材。**素材箱中的 keys loop `OS_RSV_73_piano_chords_3_u_never_call_Am.wav`，取前 10 秒，
後面補 3 秒靜音以便聽尾音。

**三個變體。**
1. Agent 第一版：`80ab5c8` 的 `plate_reverb`，當時被評為「廉價、有金屬聲」。
2. Agent 改良版：8 條 damped comb。
3. Pedalboard `Reverb`：`room_size=0.7`、`damping=0.5`。

**對齊條件。**三個 wet 訊號都調成相同 RMS 後疊回 dry 訊號，再全部正規化到 -20 LUFS integrated，
避免響度影響判斷。

**盲測。**標籤以固定 seed 洗牌，對照表保存在 `KEY.json`，Paul 作答後才開啟。
（Paul 一開始說喜歡「B」和「a」，但標籤是 X／Y／Z，經確認後才得到答案。）

## 速度（2:35 立體聲，44.1 kHz）

| reverb | 秒 |
|---|---|
| Agent 第一版 | 0.70 |
| Agent 改良版 | 2.08 |
| Pedalboard | 0.23 |

## 限制

- 只有一位聽者，只有一種素材（鋼琴 loop）。
- Pedalboard 只試了一組參數。
- 結論是「Pedalboard 的預設品質足以勝過自寫」，不是對所有 reverb 的品質排名。
