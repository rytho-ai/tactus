# 換個地方重建作品（A7 驗收）

> 2026-09-26 · 盤點清單 A7 要求「到另一個目錄驗證重建流程」，這一步一直沒做。判定規則在試驗前寫定
> （scratchpad `a7/PREREGISTERED.md`）。實作見 [計畫](../plans/2026-09-26-environment-attribution.md)（`16de3c4`）。

## 發現的缺口（實作前）

Agent 的作品通常放在 Tactus repo 外面，用 `uv run --project <tactus>` 執行，因此：
- `dependency_lock` 在每個 probe 的 receipt 裡都是 null；
- 從 git 安裝的套件只記版本號，pytimestretch `e43cc6d` 和 `bc15497` 都是 `0.2.0.dev0`；
- Tactus 本身永遠記成 `0.1.0`，看不出是哪個 revision。

receipt（`format_version` 4）現在多記兩個欄位：
- `environment`：執行環境的 prefix，以及它所屬專案的 `uv.lock`；
- `package_sources`：非 index 安裝的套件來自哪裡（git commit，或 editable 目錄的 commit 與 dirty 狀態）。

## 驗收

- **參考版本：**dogfood 3 定版作品的一份複本，放在 repo 外，用乾淨的 Tactus `16de3c4` render。
- **重建：**一個 fresh sonnet Agent 只拿到三樣東西：receipt、skill、這台機器的 pool 位置。它照 receipt 做了這些事：
  - clone 作品 repo，checkout 到 `git.commit`，`song.py` 的雜湊和 `source_files` 相符；
  - clone Tactus，checkout 到 `package_sources.tactus.git.commit`，`uv.lock` 的雜湊和 `environment.lock` 相符；
  - 執行 `uv sync --frozen`，pytimestretch 由 lock 自動固定到記錄的 commit；
  - 用 receipt 的 `parameters` 重新 render。

## 結果（依 manifest 核對）

| 輸出 | 結果 |
|---|---|
| bass、drums、keys、textures | 逐位元組相同 |
| pads（OB-Xf，每次 render 都不同） | 雜湊不同；每 8 小節的音量差 0.12～0.69 dB，在 1 dB 容許範圍內 |
| mix | 雜湊不同，因為包含 pads |

- 重建版本的 receipt 顯示，它確實用的是新建的環境（`a7/rebuild/tactus-checkout/.venv`）。
- Agent 除了 receipt、skill 和 pool 位置之外，不需要猜任何資訊。

**判定：通過。**A7 完成。

## 仍然不涵蓋的

- 非 Python 工具本身的依賴：receipt 記錄 `sfizz_render` 的雜湊，但不記錄它依賴的函式庫。
- 跨平台逐位元組一致。
- pool 裡缺少的素材。
- 沒有 `tactus rebuild` 自動化指令，重建靠 skill 的說明。
