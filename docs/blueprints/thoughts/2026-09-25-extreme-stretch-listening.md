# pytimestretch `extreme_stretch`：最小接入與試聽

> 2026-09-25 · pytimestretch main（`e43cc6d`，0.2.0.dev0，尚無 tag 與 PyPI）新增 PaulStretch
> 風格的 `extreme_stretch`。Paul 要求找最小接入方式，把它當作可選的創作處理，不取代精確拉伸，
> 並用實際作品的 beat、pad、vocal 試聽，含一次 0.1 倍率。試聽作品在
> `dogfood/2026-09-25-extreme-stretch/`（ignored）。

## 結論

- **接入方式：Tactus 不加程式碼。**把依賴的 git rev 升到 `e43cc6d`，在 skill 的 Time stretch
  段落加一條說明即可。`render()` 直接呼叫 `pytimestretch.extreme_stretch`，receipt 記錄版本
  `0.2.0.dev0`。這和先前「沒有 `tactus.stretch` 包裝」的決定一致。
- **長度：由作品裁切到用途需要的長度。**輸出長度只是近似值，所以放進作品時要裁切或補零到
  精確的 frame 數，頭尾再淡入淡出。這只有幾行 NumPy，不需要 helper。
- **音量：先前沒預料到的坑。**輸出沒有正規化，而且峰值很尖。直接把 RMS 設在 −18 dBFS，
  beat ×8 就會超過滿格，被 `tactus run` 以 `invalid_output` 擋下。要依 RMS 設音量，並限制峰值。
- **隨機性：比文件描述的更可控。**同一個 process 內連續呼叫，每次結果都不同；但新 process 的
  第 N 次呼叫結果固定。因為 `tactus run` 每次都開新 process，兩次完整執行的輸出逐位元組相同。
  但只要增減或調換前面的 `extreme_stretch` 呼叫，後面所有質地都會改變。要保留喜歡的質地，
  就把輸出匯入 pool，當作 material 使用。

## 量測

長度（輸入取自 full-song-2 的 pad）：

| 輸入 | ×0.1 | ×0.5 | ×2 | ×8 |
|---|---|---|---|---|
| 1.86 s（下限 81,920 frames） | +0.0% | −10% | −10% | −10% |
| 2.00 s | +39% | −7% | −7% | −7% |
| 8.00 s | +4.5% | −0.2% | −1.3% | −1.3% |

- 輸入少於 81,920 frames 會拋出 `InvalidAudioError`。
- 速度很快：8 秒輸入拉 8 倍約 0.18 秒；整組試聽 8 個輸出的 render 共 1.0 秒。

試聽組（全部透過 `tactus run` 產出）：

| 輸出 | 來源 | 長度 |
|---|---|---|
| `beat_x8`／`beat_x0_1` | drums 第 5–8 小節／第 5–20 小節 | 92.9 s／4.7 s |
| `pad_x8`／`pad_x0_1` | OB-Xf synth 第 13–16 小節／第 29–48 小節 | 92.9 s／5.9 s |
| `vocal_x8`／`vocal_x0_1` | 人聲分軌前 10 秒／全部 30 秒 | 78.8 s／3.1 s |
| `intro_texture`／`intro_dry` | r5 第 1–12 小節，加上／不加人聲 ×8 底層（裁成 35.1 s，淡入淡出 2 s，−25 dBFS） | 35.1 s |

- 頻譜描述：×8 後 onset 強度下降（pad 的最大值從明顯的起音降到 1.4）。
- beat ×8 的頻譜重心升到約 5.8 kHz，因為鼓的高頻噪聲被拉長成嘶聲。
- Paul 的聽感評語待補。

## 未做

沒有做 fresh-Agent 試用。skill 的說明來自這次實測，Agent 讀了之後能不能正確處理長度與音量，
尚未驗證。

## 授權：待 Paul 決定

這次升級把 pytimestretch 的授權從 `GPL-2.0-or-later` 改成 `GPL-2.0-only`，原因是 libpaulstretch
只允許 GPLv2。Tactus 同時依賴 pedalboard，而 pedalboard 是 GPLv3。GPLv2-only 的程式碼和 GPLv3 的程式碼
不能合併成同一個對外發佈的程式；先前兩者相容，是因為有「or later」這個條款。Paul 決定先擱置這個問題，照常升級（2026-09-25）。
`time_stretch` 本身沒有變：兩個 revision 之間，Rubber Band 綁定程式碼只改了註解。
