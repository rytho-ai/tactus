# 快速候選試聽（沿用沒改的步驟）有沒有必要

> 2026-09-26 · Paul 要求先用 probe 證明必要再做。判定規則在量測前寫定
> （scratchpad `probe-need/PREREGISTERED.md`）。起點是 transactional audition 還沒完成的部分：
> 試聽要快，而且沒改到的部分可以沿用（[原始設計](2026-09-23-transactional-audition.md)）。

## 結論

**現在還不需要。**依事先寫定的判定，兩個條件都落在「還不需要」：
- 實際 session 裡等 render 的時間最多只占 10.4%，門檻是 15%；
- 32 軌的合成作品一次 render 只要 14.3 秒，門檻是 60 秒。

transactional audition 其他部分都已經有了：候選不動正式程式、每個候選獨立、捨棄不留痕跡、
定版前核對原始碼。還沒做的只有「快」，而目前的速度還不構成成本。

## A：實際 session 花多少時間等 render（用既有資料）

每個 run 取 `elapsed_seconds`，再加約 1.5 秒的 process 開銷，和 Agent 整個 session 的時間比較。

| Session | runs | 等 render 約 | session | 占比 | 最慢一次 |
|---|---|---|---|---|---|
| dogfood 3（4 輪，Paul 當製作人） | 7 | 104 s | 995 s | 10.4% | 17.2 s |
| dogfood 2 第一輪 | 7 | 71 s | 1117 s | 6.3% | 9.4 s |
| dogfood 1 | 4 | 91 s | 1114 s | 8.1% | 46.1 s（手寫 NumPy reverb） |
| levels L1／L2 | 3／2 | 15／9 s | 378／254 s | 3.9%／3.3% | 3.5 s |
| discovery c／d | 1／1 | 5／4 s | 593／452 s | 0.8%／1.0% | 3.1 s |

限制：只算有 receipt 的成功 run，失敗的 run 和 Agent 自己跑的臨時腳本沒有算進去。
Agent 的時間主要花在思考與寫程式。

## B：軌數變多時會多慢（合成作品，2:30）

每軌是一個鼓取樣的 pattern，加上 Pedalboard 的 Compressor 與 Reverb；每 8 軌有一軌是 OB-Xf pad。

| 軌數 | 整首 render | 一個樣本軌 | 一個 OB-Xf 軌 | 若沿用沒改的部分，一次候選約 |
|---|---|---|---|---|
| 8 | 3.7 s | 0.27 s | 1.68 s | 1.8 s |
| 16 | 7.2 s | 0.27 s | 1.64 s | 1.8 s |
| 32 | 14.3 s | 0.26 s | 1.69 s | 1.8 s |
| 64 | 28.5 s | 0.26 s | 1.68 s | 1.8 s |

時間大致跟軌數成正比，每軌約 0.45 秒。沿用的效益很明確（64 軌時 28.5 s → 約 1.8 s），
但在目前的規模下還用不到。

另外量了 dogfood 3 實際作品各步驟的時間：
- 整首約 10 秒（第一次冷啟動約 14 秒）；
- pad 3.0 s、drums 2.3 s、keys 2.0 s、bass 1.3 s（冷啟動時 5.5 s）、textures 1.1 s、master 0.3 s。

## 這個量測沒有涵蓋的

- 合成軌的效果很輕。重的商業外掛、長的 convolution reverb、大量 VST 樂器，每軌可能慢上數倍。
- 人類製作人等待的是「改完到聽到」的時間。dogfood 3 每輪 1.5～3 分鐘，主要是 Agent 自己在工作。

## 什麼時候回頭做

符合任一條件時，就回頭做「沿用沒改的步驟」：
- 實際 session 等 render 的時間占 30% 以上；
- 一次候選 render 超過 60 秒。

做法照[原始設計](2026-09-23-transactional-audition.md)：只限參數候選，同一份原始碼下，
輸入沒變的步驟直接沿用；receipt 記錄沿用了哪些步驟、從哪裡沿用，並補回那些步驟用過的素材與工具。
「只算一段」（存檔點）排在它之後。
