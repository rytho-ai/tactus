# pytimestretch 對 Agent 是否友善：fresh-Agent 試用

> 2026-09-25 · Paul 要求派 fresh Agent 試用 pytimestretch，看它是否適合 Agent 使用、需要
> 哪些 helper。採用決定與音質證據見另一個 session 的 consumer probe
> （`2026-09-25-pytimestretch-consumer-probe.md`）。協定在試用前寫定（scratchpad `probe-pts/PROTOCOL.md`）。

## 結論

**pytimestretch 對 Agent 友善，API 不需要再包一層。**兩個 fresh sonnet Agents 只讀 skill 和
套件自己的 docstring，完成四個任務：

- 沒有任何 pytimestretch 錯誤；
- 長度都精確；
- 都明確選擇了 backend；
- 各花約 127k 與 132k tokens。

兩人都自己寫了一個 variable-rate resampler 做 tape stop，因為 pytimestretch 會保留音高，
而 tape stop 需要音高隨速度下降。這個工具改由 `fx.varispeed` 提供（`7b97c3b`）。
其他發現以 skill 指引處理。

## 任務與觀察

Fixture 為 16 小節 lo-fi，84 BPM，A minor。

| 任務 | Agent A | Agent B |
|---|---|---|
| 73 BPM 鋼琴 loop 對齊 84 BPM | `time_stretch`，`duration_ratio = 目標 frames / 長度`；輸出正好 16 小節（2,016,000 frames），接縫無跳動 | 同樣做法，用 BPM 比例；結果相同 |
| D 大調人聲移入 A 小調，放在第 13–16 小節 | 選 -5 半音（比 +7 小），加上 `formants="preserve"` | 同樣的選擇；兩人都自行發現 preserve 在同時 stretch 時比較自然 |
| 90 BPM 黑膠 loop 的拍點對齊 grid | librosa onset 被雜訊干擾（找到 28 個假拍點），改用由 BPM 推算的 marker 做 `time_warp` | 自寫 RMS 峰值偵測並凍結成常數。撞上 marker 規則：第一組必須是 `(0, 0)`，而第一個拍點不在 0 |
| 最後一小節 tape stop（刻意設的陷阱） | 識破：pitch-preserving 做不到，自寫變速重取樣 | 識破並自寫；過程中把起點錯接到 pad 的 reverb 尾巴，後來自己修正 |

## 據此的改動

- `fx.varispeed(audio, rate, speed)`：以每個 frame 的速度曲線播放，音高跟著速度走。曲線由
  作品決定；速度 0 表示停住，讀到來源結尾之後輸出靜音。
- skill 新增三點說明：
  - 人聲移調時使用 `formants="preserve"`；
  - `time_warp` 的 marker 規則，以及第一拍不在 0 時的處理；
  - pitch-preserving 與 varispeed 的分界。
- marker 建構的 helper 暫不做。證據只有一次踩坑，先以指引處理。

## 限制

- N = 2，只用 sonnet。
- 沒有請 Paul 聆聽這兩次試用的成品。
- tape stop 的聽感只驗證了程式邏輯與結尾淡出，沒有量化音高下降的曲線。
