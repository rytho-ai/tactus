# Tactus 對 Agent 有沒有加值：value probe 與 excerpt probe

> 2026-09-25 · Paul 要求用 fresh Agent 驗證「這些設計有意義嗎」。兩個實驗的判定規則都在試驗前寫定
> （scratchpad `probe-value/PREREGISTERED.md`、`probe-excerpt/PREREGISTERED.md`）。
> 所有 Agent 皆為 sonnet；結果以檔案與解碼後的音訊核對，不採信 Agent 自述。

## 結論

- **素材釘選與 receipt 有明確價值。**偷換樣本後，兩個 Tactus Agent 都沒有受影響，而且能說出雜湊；
  純 Python 組一個沒察覺（新舊 piano 相關係數 0.011），另一個是自己追查才發現。
- **`tactus excerpt` 不是正確性的必要條件。**只要 skill 寫明「不要自己把 render 開窗」、而且完整的
  WAV 已經存下來，沒有 excerpt 指令的 Agent 也會直接切存好的 WAV，9 個片段全部與來源逐樣本相同。
  它的價值是方便與可追溯（excerpt 的 manifest 記下來源 run 與其 manifest 雜湊）。保留，成本很小。
- **A1 那次 43 分鐘是環境問題，不是 Tactus。**

## Value probe：Tactus vs 純 Python＋Git

設計：A = Tactus＋skill，B = 同樣的函式庫與 Git、沒有 Tactus；每組 2 個 Agent，三輪任務（做 16
小節、只聽第 9–12 小節並定版、偷換 piano 樣本後重出定版並說明來源）。

| 指標 | A（Tactus） | B（純 Python） |
|---|---|---|
| M1 偷換樣本 | 2/2 不受影響（釘選的雜湊擋住） | 1/2 自己追查發現；1/2 沒察覺 |
| M2 第 9–12 小節試聽 | 2/2 正確 | 2/2 正確（自己切 WAV） |
| M3 來源說明 | 2/2 說得出 commit 與樣本雜湊 | 本文未逐項記錄 |
| M4 音量 | 通過 | 通過 |
| M5 token | 約 1.36 × B | — |

依規則判定為「mixed」：A 在 M1、M3 勝出，但 token 超過 1.3 倍。M2 平手，因此另做 excerpt probe。
Paul 判定 token 較多可以接受：多出來的是 Agent 依 skill 做事（釘選、讀 receipt）的成本。

## Excerpt probe：三組

任務：從已定版的 v5 取第 9–12 小節、從 v4 取第 13–16 小節、把 pad 殘響拉長後出新版本的第 13–16
小節與完整混音。pad 是 OB-Xf，每次 render 結果不同，所以重新 render 的片段會和定版對不上。

| 組 | 條件 | 片段正確 | 平均 token | 平均時間 |
|---|---|---|---|---|
| E | 現行 skill＋excerpt 指令 | 9/9 | 75.9k | 92 s |
| N | skill 拿掉 excerpt 段落，指令仍在 | 9/9（3 人都從 `--help` 找到 excerpt） | 74.6k | 108 s |
| X | skill 同 N，Tactus 完全移除 excerpt | 9/9（3 人都用 soundfile 直接切存好的 mix） | 81.1k | 138 s |

- N 組受污染：它只證明 skill 那段說明不必要。所以補做 X 組，給一個完全沒有 excerpt 的 Tactus
  （`tactus-noexcerpt/`，指令、Python export、README 與 docstring 都拿掉）。
- 事先寫定的規則：X 有 2/3 以上出錯，或 token／時間達 E 的 1.3 倍，才算 excerpt 有正當性。
  X 零錯誤、token 1.07 倍，時間 1.50 倍。時間這一項照字面算是觸發了，但 X 組執行期間我同時在跑
  pytest（58 秒）和 pytimestretch 編譯，干擾無法排除，所以只當弱證據。
- 三個 X Agent 都引用 skill 的「不要自己開窗 render」來說明為什麼要切存好的檔。真正防止錯誤的是
  這條規則加上存下來的 WAV，不是 excerpt 指令本身。

## A1 為什麼花了 43 分鐘

- value probe 的 A1 三次 `tactus run` 分別花 722、1192、328 秒，但 receipt 的 render 每次都是 1.4 秒。
- 事後用同一份專案重跑，整個 `tactus run` 只要 2.15 秒（render 1.44 秒），連跑兩次都一樣。
- 有一個分析 Agent 懷疑是 BrickwallLimiter，實測只要 0.032 秒，這個假設不成立。
- 最可能的原因是當時的 IO 競爭：4 個 probe Agent 同時在跑，A1 還在背景留了一個沒結束的
  `find /` 掃整個磁碟，而每次啟動都要載入大量套件。這無法事後證實。
- 目前不改設計。如果再發生，可以考慮讓 receipt 分段記錄時間（載入、render、寫檔）。
