# Git 工作流程觀察：fresh Agent 在五個情境下怎麼用 Git

> 2026-09-24 · Paul 要求給 fresh sub-agent 需要用到 Git 的場景，觀察它會怎麼做。這是
> behavior probe，不是 A/B，觀察項目在第一輪之前寫定。證據回饋給兩個問題：是否要用程式控制
> Git，以及 skill 的 Git 規範是否足夠。

## 結論

**Git 操作本身不需要程式控制；缺的是音檔的保存規則。**

一個 fresh sonnet agent 只依 `tactus-authoring` skill（`9b6b95c`）連續處理五個情境：

- 全程沒有破壞性操作；
- 沒有把 WAV 放進 Git；
- 保留候選、結構實驗與回到舊版本的做法都正確。

真正的失敗是**被聽過的音檔在清理 worktree 時一起被刪掉**，共發生兩次。另外，Agent 在沒有
重跑驗證的情況下宣稱可以 bit-for-bit 重現。這三點都用 skill 指引修正，不需要新程式。

## 情境與觀察

判讀依據 repo 狀態與 run 目錄，不依據 Agent 的自我回報。

| 情境 | 做法 | 判讀 |
|---|---|---|
| 1 建立專案 | `git init`，建立只含 `runs/` 的 `.gitignore`，commit `song.py` 與 `.gitignore`；首次 render 的 receipt 為 `dirty: false` | 正確。pool 路徑第一次寫錯，靠錯誤訊息自行修正 |
| 2 試參數並保留 | 比對 receipt 的 `git.commit` 確認 base 沒有移動；只改一個預設值；重跑確認 mix hash 相同；commit 訊息寫出 run 與 mix hash | 正確 |
| 3 結構實驗 | `git worktree add -b arrangement-alt`；兩版並存 render；選定後 `merge --no-ff`；合併後重跑 hash 相符 | Git 正確，但 **commit 訊息指向的 `runs/alt-arrangement` 位於 worktree 內，`git worktree remove --force` 後已不存在** |
| 4 回到舊版本 | 以 detached worktree 讀取舊 commit 並 render，沒有使用 `reset --hard`，main 未變動 | Git 正確，但 **交給製作人試聽的檔案隨即因移除 worktree 而刪除**，Agent 自己也承認路徑已失效 |
| 5 追溯來源 | 從 manifest 對到 run，由 receipt 取得 commit 與參數，用 `git log`／`git diff` 說明之後的變化 | 正確，但 **沒有重跑就宣稱可以 bit-for-bit 重現** |

另一個現象：Agent 把自己環境的 `Co-Authored-By`／`Claude-Session` 署名帶進了作品 repo 的
commit。這不算錯誤，只是會沿用自身習慣的例子。

## 修正（`skills/tactus-authoring/SKILL.md`）

1. **Run 輸出放在固定位置：**主 checkout 的 ignored `runs/`，或 repository 外的資料夾。
   worktree 內的 run 要用 `--out` 指到主 checkout 的 `runs/`。交給聽者的檔案在對方聽完前
   必須留在原路徑。
2. **認可的版本要封存：**commit 前先用 `tactus material add` 存入認可 run 的 mix（以及交付的
   stems）。pool 的 key 與 manifest 記錄的 SHA-256 相同（已實測），因此 commit 訊息中的 hash
   日後仍能用 `material("sha256:…")` 取回。
3. **重現要先驗證：**只有在重新 render 並比對所有輸出 hash 後，才能說舊版本可以重現；
   否則要說「預期可以，但未驗證」，並指向封存的檔案。

## 相關決定

- **不以程式控制 Git。**runtime 只做唯讀的紀錄（receipt 的 `git` 欄位）；commit、branch、
  merge 由人或 Agent 直接使用 Git。這與擱置 `accept` 的
  [probe](2026-09-24-accept-necessity-probe.md) 結論一致。
- **Render 的音檔不進 Git。**音檔體積大、無法 diff 或 merge，而且屬於衍生物；認可的版本存入
  本機 pool。需要備份或分享時，再評估 Git LFS 或同步儲存，並且只放認可的版本。

## 未驗證

- 修正後的指引尚未再跑一次同樣的情境。
- 只有一個 Agent（sonnet），沒有觀察多人協作或 remote／push。
