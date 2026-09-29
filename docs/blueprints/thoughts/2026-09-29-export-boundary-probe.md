# Render／export 邊界 probe

> 2026-09-29 · Paul 要求驗證是否應把 export 從 run 獨立出來。
> 這份結果供下一步設計決策使用；正式程式未修改。

## 結論

**建議：讓 export 能獨立執行，並在交付前保存 render 結果；`run` 保留一次指令即可試聽的預設行為。**

事前判讀規則：既有 WAV 足夠完成的工作，不算拆分證據；精度保留與失敗重試若需要原始音訊，
支持保存 render 結果；強制兩個指令必須另外證明價值。

| 測試 | 結果 |
|---|---|
| 既有 PCM24 WAV 轉 FLAC、stems 重新命名打包 | 完全保留已保存的 samples／檔案，不需重跑 |
| 同一次 render 的原始陣列重新交付 PCM24 | 六個 WAV 的 hash 全部一致 |
| 原始陣列交付 float WAV | 六個輸出逐 sample 相同 |
| PCM24 再轉 float WAV | 無法恢復原始精度；短素材的 1.25／−1.5 已被裁切 |
| 現有 `run` 在寫第一個 WAV 後注入失敗 | 整個 run 被清除，包含尚未發布的 takes；重試生成了不同演奏 |
| 原型先保存 render，再注入相同 export 失敗 | 原始結果保留，重試不必重新生成 |
| 相同保存／匯出機制，由一個或兩個指令呼叫 | 交付內容完全一致，兩者都保留 render 結果 |

完整作品長 149.19 秒、六個 stereo outputs。PCM24 約 237 MB，原始 float32 陣列約 316 MB；
若兩份全留，合計約 553 MB。這是需要明確處理的儲存成本。

## 方法與判讀邊界

輸入取自 saved-takes 完整作品的 playback source。用既有 `uv run tactus run` 生成一次，
透過 optional `takes` 保存相同執行的六個最終 output arrays，作為原始資料。
這裡保存的是 `render()` 回傳的 mix／stems，不是只有原始 pads／bass 的中間 take。
兩種編碼都讀同一批 arrays，避免不同演奏混進比較。

故障案例以短的未固定亂數演奏執行實際 `run`：在 worker process 內替換
`OutputStore.add`，寫出第一個檔案後拋出 `OSError`，觀察現有 runner 的清除行為。
每次生成另外記錄一個 hash，確認重試真的重新生成，而且演奏不同。
原型把 `.npy` 與內容 hash 清單先存好，再執行相同的故障位置；export 清掉自己的半成品，
保存結果維持原 hash，重試沒有多一次生成。損壞的原始陣列也會在 export 前被拒絕。

一個指令與兩個指令的比較，使用完全相同的保存／匯出函式和固定輸入；由獨立的
`uv run …` processes 執行。兩種流程的保存清單與交付 hash 相同。這只證明呼叫方式
不妨礙相同技術保證；沒有量測人類或 Agent 的操作偏好，也不宣稱一個指令較容易使用。

完整作品在此主機的一次量測：render 7.053 s；另存原始 arrays 0.456 s；原始 arrays
匯出 PCM24 2.716 s、float WAV 1.373 s；既有 PCM24 轉 FLAC 1.056 s。
這些是描述性數字，不是效能 benchmark。六個輸出都是 6,579,243 frames、44,100 Hz、stereo；
PCM24 檔案合計 236,853,012 bytes，原始 `.npy` 合計 315,804,432 bytes。

完整歌曲 PCM24 相對原始 float32 的最大 sample 誤差約 `1.1921e-7`，未測可聽性。
邊界素材 `[0, 2^-27, -2^-27, 0.123456789, 1.25, -1.5]` 經 PCM24 再轉 float 的
最大誤差是 0.5；直接從原始陣列輸出 float 則完全一致。保存 output arrays 也無法恢復
作品 source 內已經做掉的 `np.clip` 或其他處理。

範圍是一首作品與一段邊界素材，驗證資料完整性與失敗行為。原型不代表正式 export 已實作，
也不保證 render 結果尚未保存完成時能從失敗中恢復。Float64 保存／交付政策、自訂 exporter
契約、舊 run 相容方式、預設保存多少檔案與清理策略仍需後續設計。這輪沒有驗證 plugin 註冊。

## 紀錄

- 起點：`72aac4e`（saved takes）。`src/` 與既有測試皆未修改。
- 判讀規則在執行前寫入 ignored `probes/2026-09-29-export-boundary/preregistered.md`。
- 試驗以 `uv run python probes/2026-09-29-export-boundary/probe.py` 執行；harness、
  `evidence.json`、stdout／stderr 與音訊都在同一個 ignored 目錄，只保存本 findings。
- 首次啟動遇到舊容器建立的素材目錄權限問題，尚未完成生成；改為複製 blobs 到獨立 pool，
  不沿用 materialized trees／stage cache 後完成。第一次失敗紀錄保留。
- 所有上述 equality、failure、retry、integrity assertions 通過；既有 WAV 與 snapshot
  在匯出後 hash 未變。這是實驗執行驗證，沒有重跑無程式變更的完整 pytest suite。
