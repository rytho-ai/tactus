# 2026-09-25～26 工作回顧：做了什麼、為什麼

> 這段工作從 `fdde406` 到 `03a7122`，共 20 個 commit，全部由 fresh-Agent probe 或 dogfood 的證據驅動。
> 每一項的細節都在各自的 thought 裡，這份只整理決定與理由，方便日後回頭查。

## 定下的原則（已寫進 positioning 第 1 條）

- **品質問題由 Tactus 如實回報，不替 Agent 擋下。**
  - 起因是 dogfood 3 的 Agent 從初稿起就用 `np.clip` 繞過「超過滿格就拒絕存檔」的檢查。
  - 擋下只會讓 Agent 繞過去，問題依然存在。
- **給 Agent 的 skill 只教怎麼用 Tactus**，不教做音樂，也不代替各套件自己的文件。
  - 起因是我把「稀疏分軌只量大聲的部分」寫進 skill，Paul 指出這是混音建議，不屬於 skill。

## 做了、而且留下的

| 項目 | 理由（證據） | 紀錄 |
|---|---|---|
| 音量回報取代拒絕（`peak_dbfs`、`clipped_samples`、`levels`） | Agent 會繞過拒絕；改成回報後，兩個 Agent 都依數字修正，沒有用 `np.clip` | [levels probe](2026-09-25-levels-and-midi-probe.md) |
| `mido` 成為預設依賴 | 三次 dogfood 的 Agent 都手寫了 MIDI 檔案產生器 | 同上 |
| `extreme_stretch`（PaulStretch） | Paul 試聽：pad 會產生很神奇的質地；兩個 Agent 照 skill 正確處理長度、音量與固定 | [試聽與驗證](2026-09-25-extreme-stretch-listening.md) |
| skill 精簡成只講 Tactus（355 → 約 230 行） | 原則如上；兩個 Agent 重測外掛設定沒有退步 | [discovery probe 重測段](2026-09-25-plugin-discovery-probe.md) |
| `@stage` 加 `--reuse`，完成 transactional audition | 價值在於比較公平，不在速度：有 reuse 時 3/3 交出「只有 bass 變」的候選，沒有時 0/3 | [必要性](2026-09-26-fast-audition-necessity.md)、[Agent probe](2026-09-26-stage-reuse-probe.md) |

## 做了又拿掉的

| 項目 | 理由 | 紀錄 |
|---|---|---|
| `tactus accept` 與它的分支 | 說明寫清楚後 9/9 的 Agent 都處理對了；分支已落後 main 33 個 commit | [刪除紀錄](2026-09-26-delete-tactus-accept.md) |
| skill 裡的混音建議，包括 Limiter 用法與稀疏分軌的量法 | 不屬於 skill 的範圍 | 本文件的原則 |

## 驗證後決定先不做的

| 項目 | 理由 | 回頭的條件 |
|---|---|---|
| 只為了速度而加快試聽 | 實際 session 等 render 的時間只占 1～10%；32 軌 14 秒、64 軌 28.5 秒 | 等待占 30% 以上，或一次候選超過 60 秒 |
| 只算一段（stateful checkpoint） | 只聽一次時比較慢，每次修改又要重建 | 改到的那一步本身就超過 60 秒 |
| 偵測已被削平的樣本 | 有盲點（23～775 個樣本），但還沒有人聽出問題；Paul 決定先不做 | Agent 交出聽得到、但回報沒抓到的削頂 |
| `time_scrub` | 內部試用；人聲與 keys 轉向平順，鼓的起音會被抹平 | 有作品需要 |
| 授權 | pytimestretch 改成 GPL-2.0-only，和 Pedalboard 的 GPLv3 不能一起對外發佈；目前只在內部使用 | 開始規劃任何公開發佈 |

## 用 dogfood 與 probe 找問題的方式

- **dogfood 3 由 Paul 當製作人，意見原文轉給同一個 Agent。**三輪修改後定版，過程中找到兩個問題：
  `np.clip` 繞過檢查，以及手寫 MIDI 產生器。
- **每個 probe 都在試驗前寫定判定規則，並依檔案與音訊核對，不採信 Agent 自述。**有兩次結果推翻了我原本的判斷：
  - Limiter 會在外掛內部削頂，讓回報看不到；
  - 精簡 skill 時漏掉了 `load_plugin` 需要 `str()`。

## 我自己的失誤（記下來避免重犯）

- 數字先寫、後驗證。量測表寫錯過兩次，實驗紀錄裡也有一格寫了自己不確定的說法。
- 計時的實驗跑的時候，我同時在跑重的工作，時間數字因此只能當弱證據。
- 一開始把 transactional audition 講窄了，只講了「定版前要檢查」。Paul 指出後，回頭查了原始設計。
- 把時間工具（A1）排到 Future 時，沒有指出這和盤點清單「證據已足以實作」的判斷互相矛盾。

## 還開著的

- **A1 時間計算工具：**盤點清單認為證據已足以開始最小實作，但目前放在 Future，需要和 Paul 重新決定。
- **Paul 新增的「統一的音檔基礎分析」：**已確認方向是每次 run 附上基本量測、只量不判斷，但還沒寫計畫。
- **A7 換個地方重建作品：**作品不在 Tactus repo 裡時，receipt 沒有鎖定檔；從 git 安裝的套件只記版本號，
  不記是哪個 revision。
- **C3 試聽比較頁：**這段工作裡手工做了 4 次，可以抽成可重複使用的工具，但放在 runtime 外面。
