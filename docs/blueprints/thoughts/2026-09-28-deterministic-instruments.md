# OB-Xf 與 sfizz 可以固定重新合成的結果嗎？

> 2026-09-28 · 接續 [完整交接驗收](2026-09-28-clean-production-handoff.md) ·
> [計畫](../plans/2026-09-28-deterministic-instruments.md) ·
> [patch、腳本與證據](../../../experiments/deterministic-instruments/README.md)

## 結論

**可以，這次兩個本機原生修補版都通過整首作品的重新合成測試。**

三次在全新、斷網的容器中執行同一份 46 小節作品，每次重新跑 OB-Xf、sfizz 和其餘 DSP，
沒有使用 stage cache 或保存的演奏。mix 加五個 stems 的 WAV 全部逐 byte 相同。
這補上了前一輪只能靠固定演奏材料達成的一致性。

目前成果是可重建的局部 patch 與測試工具；既有安裝、原作、先前試聽候選均未替換。
Tactus 的 public API 沒有改動，也沒有對外發佈 fork 或提交上游。

## OB-Xf：把內部隨機狀態固定

只把四個 slop 旋鈕歸零、只設定 C RNG seed，或兩者並用，都沒有通過：
各組三次 fresh-process 渲染仍然不同。

使用與現有外掛一致的 source revision `1223e6f` 重建後，未修改版三次輸出不同；
同一個 build 加入固定初始化後，五次 float32 輸出完全相同。

修補涵蓋三組來源：

- Voice 的 level、envelope、filter、portamento 偏差，改用明確的局部 RNG。
- Oscillator 的相位、tuning slop、noise，改用該聲部的固定 seed。
- Global／voice LFO 的 sample-and-hold 初值與 RNG，也使用固定 seed。

各聲部仍使用不同的 seed，slop 參數與既有 DSP 也保留。因此每次使用同一組聲部差異，
不用把所有類比變化關掉。實驗目前把 root seeds 固定為 42／43，尚未實作可由 host 設定、
寫入 preset 的 seed 介面。這會選定一個新的演奏狀態，不會找回先前核可的隨機 take。

## sfizz：等待機制漏掉尚未派出的工作

原本的 `waitForBackgroundLoading()` 只等待 `loadingJobs` 裡已經派出的工作。
載入請求如果還在 `filesToLoad` 佇列，dispatcher 又尚未獲得執行機會，函式就可能直接返回。
離線 render 跑得很快，會在 samples 準備好以前繼續計算。

為了區分「剛好十次都成功」和真正修好，加入一個只用於測試的 20 ms dispatcher 延遲：

| 情況 | 結果 |
| --- | --- |
| 未修改版、一般排程 | 本輪十次恰好一致；前輪已觀察到間歇性差異。 |
| 未修改版、延後派工 | 單音三次都偏離正常參考，最大 sample 差 0.000732421875。 |
| 補齊等待、同樣延後派工 | 單音三次及完整 bass 三次，全部和正常參考完全相同。 |
| 補齊等待、移除測試延遲 | 單一 CPU 下完整 bass 十次，全部和正常參考完全相同。 |

修補在既有 mutex 保護下，先把尚未派出的請求送入 worker pool，再等待全部工作完成。
最終執行檔沒有測試用延遲。這驗證了該 source revision 的排程缺口與修補效果；
不能由此宣稱所有 SFZ 的隨機 opcode 都會變成 deterministic。

## 完整作品驗收

- 三個新容器，每次 `reuse: false`、`stages: []`，沒有讀固定演奏的 `.npy` material。
- 原始生成 source hash 仍是 `4f9b2cf...b8020`，與前輪直接合成使用的 source 相同。
- 六個 WAV 三次完全相同。bass、drums、keys、textures 同時與前輪主機基準一致。
- 新 pads hash：`82f0be422500b987e6698c602756d7f316da24f1e88faa6ae8c1090a7773350a`。
- 新 mix hash：`4786ffda677f957e7f07e94ff4d9235d608d87836d794d814183bc940a6c6a30`。
- 三次執行耗時 16.803、13.925、12.513 秒。

仍然只驗證同一 CPU／kernel 的 Linux 環境與這份作品。尚未測試其他平台、所有 preset、
同一個長駐 plugin instance 的任意 reset／seek，也沒有經人類試聽接受新的演奏。

## 下一個產品決定

技術可行性已成立。若要正式採用，需要決定 OB-Xf 的 seed 如何由作品明確指定與保存，
並將 sfizz 的等待修補交給可維護的依賴版本。這輪先保留獨立工具與 patch，沒有把修改
藏進 Tactus runtime，也沒有要求每個作品改用固定演奏素材。

驗證：400 pytest tests 通過，1 個既有 opt-in 測試 skipped；全 repo Ruff 通過。
