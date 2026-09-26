# 沿用沒改的步驟（`@stage` / `--reuse`）：fresh-Agent 驗證

> 2026-09-26 · 驗證 [stage reuse 計畫](../plans/2026-09-26-stage-reuse.md)（`4df3d25`）。判定規則在試驗前寫定
> （scratchpad `probe-reuse/PREREGISTERED.md`）。起因見[必要性 probe](2026-09-26-fast-audition-necessity.md)：
> 速度本身還不構成需要，但 OB-Xf 這類每次 render 都不同的外掛，會讓候選之間的比較混進隨機差異。

## 結論

**有價值，而且這個價值跟速度無關。**有 reuse 的 3 個 Agent 都交出「除了 bass 什麼都沒動」的候選版本；
沒有 reuse 的 3 個 Agent 一個都做不到，pad 每次都不一樣。兩組的成本幾乎相同。

## 設計

- 兩組只差一件事：R 用 Tactus `4df3d25`（有 `@stage`／`--reuse`）與它的 skill；N 用 `3666c27`（沒有 reuse）
  與它的 skill。每組 3 個 fresh sonnet Agent。
- 作品是同一份已定版的 dogfood 3 作品，沒有標任何 stage。
- 題目：製作人要一個 bass 小 1 dB 的候選，而且要確定其他東西都沒動，並說明兩者除了 bass 還差在哪。

## 結果（依 manifest 與 receipt 核對）

| | V1：pads、textures、keys、drums 逐位元組相同 | V2：說法與檔案相符 | 平均 tokens | 平均時間 |
|---|---|---|---|---|
| R | 3/3 | 3/3 | 73.7k | 148 s |
| N | 0/3（pad 每次都不同） | 3/3 | 73.9k | 142 s |

- **R 組：**三人都自己在五個 `*_bed` 函式加上 `@stage`，兩次 render 都用 `--reuse`，候選的五個 stage 全部是
  `reused: true`。三人都說明加標記是尚未 commit 的原始碼修改，等製作人決定要不要保留。R1 另外驗證了
  bass 正好是原本的 `10^(-1/20)` 倍。
- **N 組：**三人都正確發現 pad 不同，也歸因於 OB-Xf 本身的隨機性。N3 還多 render 一次來證明這一點。
  N2、N3 提議「把 pad 凍結成 material 再重做」，但沒有人真的去做。skill 裡的手動做法存在，Agent 卻沒有主動採用。
- **小錯誤：**R2、R3 說 `extreme_stretch` 的質地每次 render 都會變。其實在呼叫順序不變時，每個新 process
  的結果都相同；dogfood 3 的 textures 就一直不變。這沒有影響它們交出的檔案。

## 判定

事先寫定的規則是：R 至少 2/3 同時達到 V1 與 V2，而 N 至多 1/3 → 證明有價值。結果 R 3/3、N 0/3，
成本相當，判定為**有價值**。
