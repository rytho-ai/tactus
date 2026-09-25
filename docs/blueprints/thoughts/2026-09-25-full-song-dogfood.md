# 整首歌 dogfood：從短曲到 2:35 的完整作品

> 2026-09-25 · Paul 同意用一首完整歌曲實際走一遍，找出看板上 A1／A5／A6 哪一項真的需要。
> Session 資料在 gitignored 的 `dogfood/2026-09-25-full-song/`（`INTENTS.md`、`crate/`、
> `work/` 與其 `LOG.md`）。本文件保存結論與證據。

## 結論

依證據排序的下一步如下：

1. **receipt 還原缺口**：已修正，`59ae34a`。
2. **A5 區段試聽**：由 runtime 提供，而且必須和整首一致。見
   [range audition plan](../plans/2026-09-25-range-audition.md)。
3. **A6 效果器**：自寫 DSP 的成本與品質壓力已經出現。
4. **SFZ 等資料夾素材的身分**：確認是缺口，與 A6 或下一件用到樂器的作品一起處理。

A1 時間工具這次沒有出現錯誤壓力，Git 流程也正常。

## 設定

- **Agent**：一個 fresh sonnet Agent，只讀 `tactus-authoring` skill（`0b342a0`）。
- **素材**：33 個 Rytho library 素材，loop 分別是 73／130／156 BPM，也有不同 sample rate。
- **樂器**：FluidR3 soundfont、Karoryfer SFZ bass 資料夾，外加 `rubberband` 與 `sfizz_render`。
- **Brief**：82 BPM、有段落結構、帶 half-time bridge 的 neo-soul／lo-fi 曲子。
  - brief 本身有錯：段落小節數加總約 5 分鐘，卻要求約 2.5 分鐘。Agent 把每段減半，並記錄了
    理由。這是 brief 的錯誤，不是 Tactus 的發現。

兩輪：

- 第一版：作品、stems 與 commit；
- 修改：bridge 到 final chorus 的轉折，外加「先只給我聽那一段」與「reverb 太廉價」。

共約 223k sonnet tokens。

## 發現

**1. Receipt 無法還原未提交的新檔案（gap，已修）**

被選中的 r2 是在第一次實質 commit 前 render 的：`git.commit` 指向空的 init commit，所有 stage
模組都是 untracked。當時的 `source.patch` 只含 tracked diff，因此 commit + patch 無法還原。
現在 patch 會附上 untracked `.py` 的 new-file diff。

**2. Agent 自製的區段試聽與成品不一致（gap，A5）**

Agent 自己加了 `bar_range` 參數，並把視窗一路傳到每個 stage。預覽只要 5 秒，整首要 46 秒。
以整首 render 的同一段比對（位置對齊在第 35 小節、先做 gain match）：

- 第 1 小節差 88%：reverb 與 compressor 冷啟動；
- 第 4、8、12 小節差 50–100%：keys loop 從視窗起點重新開始，沒有延續相位；
- 其餘小節約差 15%：整體正規化與 compressor 處理的素材不同。

Agent 用自己算的 RMS「驗證」預覽良好，沒有察覺差異。製作人會依據一段不存在於成品中的聲音
做判斷。區段試聽的需求真實存在（製作人不想每次聽整首；reverb 改進後整首從 17 秒變成
46 秒），但正確性必須由 runtime 保證。

**3. 效果器全部自寫（friction，A6）**

reverb（Schroeder／FDN，之後改成 8 條 damped comb）、compressor、saturation、sidechain duck
都是用 NumPy 自寫的：

- 第一版用逐 sample 的 Python 迴圈，在 680 萬 frame 上慢到無法使用，後來改成向量化的
  `lfilter`；
- 第一版 reverb 被判定「廉價、有金屬聲」，改良後 render 時間約增加一倍。

聲音品質仍待 Paul 聆聽。

**4. SFZ 資料夾無法固定（gap）**

`tactus material add` 拒絕資料夾，而 `.sfz` 依賴相對路徑下的多個 samples。Agent 只能保留一個
未固定的路徑，並在 LOG 中標記為已知缺口，做法與 phonon-ballad 的 `sfz_piano` 相同。

**5. 沒有出現的壓力**

- half-time bridge 以節奏型態處理，全曲維持單一 tempo，沒有時間換算錯誤，A1 暫無新證據。
- Git 流程（`.gitignore`、只 commit source、封存認可的 mix）正常。

## 數據

| Render | 內容 | elapsed_seconds | 牆鐘時間 |
|---|---|---|---|
| r1 | 整首 | 16.4 | 18.4 s |
| r2 | 整首（調整 mix） | 16.8 | 19.0 s |
| transition-1 | Agent 自製的 13 小節視窗 | 5.1 | 6.8 s |
| r3 | 整首，改良 reverb | 46.1 | 48.2 s |
