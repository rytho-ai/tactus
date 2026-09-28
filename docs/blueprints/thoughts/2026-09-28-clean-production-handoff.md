# 完整作品在乾淨環境重建、修改與交付

> 2026-09-28 · [計畫](../plans/2026-09-28-clean-production-handoff.md) ·
> [執行腳本與重建步驟](../../../experiments/clean-production-handoff/README.md)

## 結論

**保存演奏後，搬移與單軌修改可以精確重現；只保存樂器、音符與 dependency lock，仍不足以重現聲音。**

本輪用 Paul 先前認可的 46 小節 ambient／lo-fi 作品測試，保留原作不動。
先修正驗收副本直接讀取家目錄 OB-Xf 的問題：改成明確工具路徑並呼叫 `tool()`，
再為五個聲部加上 `@stage`。沒有新增 runtime API。

## 兩輪結果

| 驗證 | 結果 |
| --- | --- |
| 直接重跑所有樂器 | **未通過**。drums、keys、textures 相同；bass 有四個音符不同，OB-Xf 尾段 RMS 差 1.075 dB，超過原訂 1 dB。 |
| 固定 pads、bass 的演奏，再搬移 | **通過**。乾淨環境的 mix 加五個 stems 都和主機基準逐 byte 相同。 |
| 只把 bass gain 從 -3 改為 -6 dB | **通過**。實測 -3.00000047 dB；bass 與 mix 改變，其餘四軌完全相同。 |
| 遺失素材、遺失 SFZ 內部檔案、損壞素材、遺失工具 | 第二輪 14 個反向案例全部明確失敗；還原後通過。 |
| 交付包重新解壓 | 231 個檔案 checksum 全數相符；重建包另驗證 2,314 個 blob 與兩個工具。 |

第二輪的「固定」是把第一輪主機基準的 **pre-gain float32 stage arrays** 存成素材，
以 `material()` 和 `np.load(..., allow_pickle=False)` 讀回。三個其他聲部與 master bus
仍重新計算。這兩份演奏成為 source 明確引用的輸入，沒有把主機 cache 搬過去冒充重算。
生成程式、原始工具／素材身分與 generation receipt 一併保留。

保存的是**本輪主機演奏**，不是先前 c7 的 OB-Xf take；不能說重現了先前核可的 mix。
原 c7 與本輪主機基準的四個確定性 stems 一致，但 pads、mix 不同。
A、B 均未經 Paul 接受，也沒有修改原作的預設值。

## 後續：原生修補也能重現

同日的[固定合成實驗](2026-09-28-deterministic-instruments.md)進一步修正 OB-Xf 的
隨機初始化與 sfizz 的背景載入等待機制；兩個本機修補版在不使用 cache／固定演奏的情況下，
三次整曲重新合成得到相同的六個 WAV。以下保留原始交接實驗的觀察，原安裝仍未替換。

## SFZ 差異追查

第一次 bass 差異發生在第 29、31、33、39 小節，開始於 note-on 後約 0.206 秒；
經處理的最大 sample 差為 0.03385。獨立重跑的單音、完整 MIDI 和完整前置 DSP
一度全部一致，不能據此認定已修復。

把 `sfizz_render` 限制在單一 CPU 後，同一份完整 MIDI 連跑兩次，**未經 Tactus／effects
處理的原始 WAV** 最大差為 0.00494384765625；其中一次與主機基準相同。
之後再跑同一類測試又一致，確認是間歇性不一致。原始碼顯示引擎有背景 sample loading，
但這不足以確認已安裝 binary 的內部根因；目前不能宣稱已修正 streaming、random seed 或浮點問題。

保留 [`probe_sfizz.py`](../../../experiments/clean-production-handoff/probe_sfizz.py)
供後續縮小外部引擎問題。固定演奏解決本次交付需求；它不代表 sfizz 已變得可重現。

## 環境與交付

- Ubuntu 24.04 容器、Python 3.12.11；image、system packages、source、lock 與 native tools
  都有身分紀錄。建置時可連網，渲染以 `--network none` 執行。
- 只掛入指定的 pool blobs、tools、inventory，以及全新輸出目錄；沒有掛入主機家目錄、
  原作、venv 或 stage cache。兩輪都有自己的 fresh pool 與 cache。
- 第二輪 baseline 8.083 秒，bass 候選 1.516 秒。baseline 五個 stage 全部未命中 cache；
  其中兩個讀固定演奏，三個執行 DSP。候選五個 stage 全部命中。
- 每版一個 mix、五個 stems；44.1 kHz、stereo、PCM24，6,579,243 frames，約 149.189 秒。
  起點都是 frame 0；附 74 BPM、4/4、段落 frames、source／lock、receipts、校驗碼。
- Stems 在 master bus 之前，直接相加不會等於經非線性壓縮／limiter 的 mix。
  原作內部 `np.clip` 會讓 runtime 看不到先前的削頂，這輪不宣稱「音訊沒有削頂」。
- 交付 ZIP 約 295 MB；原素材／工具重建包約 1.08 GB；已安裝環境 image 約 404 MB。
  三者留在 ignored dogfood 目錄，沒有公開上傳原始素材或工具。

## 驗證範圍

`pytest`：400 passed、1 個既有 opt-in 測試 skipped。Ruff 全 repo 通過。
真實 CLI／container 渲染、兩版 WAV 比較、交付解壓與完整 blob closure 驗證都已執行。
試聽頁驗證載入、切換聲部／候選、保留播放位置、播放與 390 px 版面；沒有代替人類試聽。

這仍使用同一主機的 CPU／kernel，尚未證明另一台機器、macOS／Windows 或任意外掛的行為。
`tool()` 本身只記錄身分；本次驗收的 preflight 額外核對預期 hash。

## 對產品下一步的影響

完整交接需要區分「保留選中的演奏」和「從 generator 重新演奏」。前者已能用既有
material 機制完成；cache 不應成為唯一存放處。本輪可作為後續交接流程的固定驗收案例。

需要再收斂的是：如何在實際作品裡清楚保存演奏與生成依據、收集完整素材依賴、
檢查缺少的 native tools，並交付對齊 stems 與資料。先沿用這份可執行流程，
再依其他作品的重複困難決定哪些部分值得成為共用介面。
