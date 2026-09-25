# 刪除 `shelved/tactus-accept` 分支

> 2026-09-26 · Paul 決定直接刪除，並要求留下這份紀錄說明原因。

## 決定

刪除只存在本機、從未 push 的分支 `shelved/tactus-accept`（唯一的 commit 是 `cade5be`，
2026-09-24）。`tactus accept` 不再是「擱置、等錯誤出現再拿回來」的功能，而是確定不做。

## 為什麼刪

- **它要防的錯誤，Agent 靠說明就不會犯。**在三回合 probe 中，只要 skill 清楚說明「定版前核對原始碼
  有沒有變」，有沒有這個指令結果都一樣：
  - 第二回合，同樣清楚的說明，有 `accept` 和沒有 `accept` 兩組共 6 個 Agent 全對；
  - 第三回合（2026-09-26），skill 精簡後只靠說明，3 個 Agent 全對。

  見 [accept 必要性 probe](2026-09-24-accept-necessity-probe.md)。
- **實際做歌時也沒出錯。**完整歌曲 dogfood 3 裡，Agent 只靠 skill 就完成了定版：核對原始碼、
  把 mix 存進 pool、再 commit。
- **分支已經不能直接用。**它落後 main 33 個 commit，中間改過 manifest 格式、存檔流程與 skill，
  要拿回來也得照當時的 main 重做，所以留著沒有節省成本的價值。
- **它和 positioning 的方向相反。**`accept` 是 Tactus 唯一會改寫作者原始碼的地方；定版的決定和
  Git 操作本來就留給 Agent（positioning 第 1、6 條）。

## 它做過什麼（留作參考）

約 780 行，包含實作與測試：

- `tactus accept RUN_DIR`：把某個候選 run 的參數寫回 `render` 的預設值；
- 兩道防護：
  - 原始碼必須和 run 的 receipt 一致，否則報 `base_changed`；
  - 每個不同的參數都必須已經有預設值可以取代，否則報 `not_promotable`；
- 只改寫預設值所在的 AST 片段，改完重跑一次驗證輸出能重現，失敗就原子性地還原原始檔；
- 不會自己 commit，commit 仍由呼叫者用 Git 完成。

## 什麼情況會重新考慮

實際製作中出現 Agent 在原始碼已經變動後，仍宣稱「和製作人聽到的一樣」而定版，而且補強 skill
的說明也修不好時。到時照當時的 main 重新設計，不從這個分支復原。
