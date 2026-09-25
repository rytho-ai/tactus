# Run 輸出檔名 probe：hash 要放在哪裡

> 2026-09-25 · Paul 覺得 run 輸出只用完整 hash 當檔名，人看不懂；但他也希望保留 hash。本文件
> 回答 hash 該放在哪裡，判定規則在試驗前寫定。

## 結論

**採用 `<name>-<前 8 碼 sha256>.wav`**，例如 `mix-2b0fd2df.wav`，放在 run 目錄最上層，完整
SHA-256 仍然記在 manifest。分隔符號由 Paul 指定為 `-`；由於 hash 固定是最後 8 碼，`drums-core`
這類含 `-` 的名稱也能無歧義地切開。

對 Agent 來說三種放法沒有差別，**真正的判準是人的可讀性**：只有 A 同時讓人看得懂這是哪個輸出，
又在檔案被複製出去後仍帶著身分。

## 方法

**三種放法。**同一個 repo、同樣的 commits 與 runs，唯一差別是檔名：

- A：`<name>.<sha8>.wav`（試驗時用 `.` 分隔）
- B：`<name>.wav`
- C：`materials/audio/<sha256>.wav`，也就是當時的做法

**試驗設計。**每種放法 2 個 fresh sonnet Agents，prompt 相同，唯讀作答三題：

1. 最新 commit 核准版本的 bass stem 在哪裡；
2. 桌面上一個複製出來的 mix 來自哪個 commit 與 run、是否為核准版本、是否是現在的聲音；
3. c-3 與 c-9 的 drums 是否相同。

**標準答案。**事先依 manifests 與 git log 算好。

## 結果

| 放法 | 答對 | tool calls | tokens |
|---|---|---|---|
| A `mix.2b0fd2df.wav` | 3/3、3/3 | 3、4 | 約 65k、66k |
| B `mix.wav` | 3/3、3/3 | 4、5 | 約 67k、64k |
| C `<sha256>.wav` | 3/3、3/3 | 3、7 | 約 66k、66k |

- 依預先的規則，答對數平手時比平均 tool calls，A（3.5）勝過 B（4.5）與 C（5）。但 N = 2，
  這個差距不是強證據。
- B 組碰到桌面上的 `mix.wav` 時，要自己執行 `sha256sum` 才能追查來源。Agent 做得到，但人無法
  從檔名判斷是哪個版本。

| 放法 | 人看得懂是哪個輸出 | 複製出去後，看檔名就能對回紀錄 |
|---|---|---|
| A | ✓ | ✓（短 hash 可直接比對 commit 訊息） |
| B | ✓ | ✗（每個版本都叫 `mix.wav`） |
| C | ✗ | ✓ |

## 隨附的契約變更

- 輸出名稱必須能當檔名：`[A-Za-z0-9][A-Za-z0-9._-]*`。
- manifest 的每個輸出新增 `file` 欄位。
- WAV bytes 不變，只改寫入位置與檔名。
- Input pool 維持完整 hash、無副檔名，並與 tactus-daw 相容，因為那是給程式與長期保存用的。
