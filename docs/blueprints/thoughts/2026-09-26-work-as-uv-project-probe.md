# 每個作品都是 uv 專案：可行性與 fresh-Agent 驗證

> 2026-09-26 · Paul：「整個 tactus 都要用 uv 做環境管理」。實作見
> [計畫](../plans/2026-09-26-work-as-uv-project.md)（`efa37e9`、`8953e90`）。判定規則在試驗前寫定
> （scratchpad `probe-init/PREREGISTERED.md`）。

## 可行性測試發現的坑

- 作品用 git 網址依賴私人 repo 的 Tactus，可以安裝。pytimestretch 也能透過 Tactus 自己的
  `tool.uv.sources` 固定在正確的 commit。
- 但 uv **沒有**把 Tactus 的 `requires-python <3.13` 套用到作品，建出了 Python 3.13.5 的環境；
  Pedalboard 在 3.13 上一 import 就崩潰（exit 132，也就是已知的 AVX-512 問題）。
- 把作品限制在 `>=3.12,<3.13` 就正常了。

這種細節不該靠 Agent 每次自己記得，所以 `tactus init` 直接從正在執行的 Tactus 複製這個限制。

## fresh-Agent 驗證

兩個 fresh sonnet Agent 只有 skill 可以參考，要從零開始做一首 4 小節的作品，並加入一個 Tactus 沒有內建的套件
（`pretty_midi`），然後 render。

| | 自己的 `pyproject.toml`／`uv.lock`，Tactus 固定到 commit | Python | receipt 的 `dependency_lock` | `pretty_midi` 只在作品的 lock | render |
|---|---|---|---|---|---|
| I1 | ✅（`efa37e9`） | 3.12.11 | 作品自己的 `uv.lock` | ✅ | ✅ |
| I2 | ✅ | 3.12.11 | 作品自己的 `uv.lock` | ✅ | ✅ |

- **判定：通過。**
- **兩人都遇到同一個摩擦：**`init` 沒有建立 Git repo，他們得自己執行 `git init`。I1 在建立 repo
  之前就先 render，那份 receipt 的 `git` 是 null。已修正（`8953e90`）：`init` 發現資料夾不在任何
  Git work tree 裡時，會自動 `git init`。
- 成本：每人約 62k tokens，1.5 分鐘。
