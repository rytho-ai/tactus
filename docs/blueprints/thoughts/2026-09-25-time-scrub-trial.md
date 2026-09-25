# pytimestretch `time_scrub` 內部試用

> 2026-09-25 · Paul 要求試用 pytimestretch main（`bc15497`，0.2.0.dev0）新增的 `time_scrub`：
> 讓播放停住、倒轉、來回拖。這次只是內部試用，裝在 scratch venv，**Tactus 的依賴沒有動**。
> 試聽頁與腳本在 scratchpad `trial/listen/scrub/`、`scrub/`。

## 結論

- **接法：** 跟其他 pytimestretch 函式一樣，在 `render()` 裡直接呼叫，不需要包裝。
  `control_points` 是 `(輸出 frame, 原音檔 frame)`；輸出 frame 必須是遞增的整數，最後一個
  就是輸出長度，所以長度是精確的，這點和 `extreme_stretch` 不同。作品用秒或拍子寫曲線，
  乘上 sample rate 並把輸出端四捨五入即可，只要一行，不需要 helper。
- **輸出是固定的：** 同樣的輸入，同一個 process 內或換新的 process，結果都逐位元組相同。
- **要注意的兩件事：**
  - 峰值可能比原音檔高約 3 dB（人聲原本 −0.1 dBFS，輸出到 +2.7），所以之後一定要重新設增益。
  - 停住的時候，音量比原音檔在那個點低 2～7 dB；開頭 50 ms 也低約 5 dB（引擎剛啟動）。
- **哪種素材效果好：** 人聲與 keys 轉向時很平順：音量最多只掉 3～7 dB，轉向點也量不到尖刺。
  鼓的起音會被抹平（文件也提到這是 granular 視窗造成的），slow stop 在減速段掉了 19 dB。
  所以如果要讓鼓「停下來」，磁帶式（音高跟著速度走）可能比較適合；試聽頁兩種都有。
- **Tactus 現有工具的缺口：** `fx.varispeed` 不接受負速度，沒辦法用來倒轉；磁帶式對照是另外
  直接沿位置曲線讀原音檔做出來的。要不要讓 `varispeed` 支援倒轉，等有作品需要時再說。
- Paul 的聽感評語：待補。

## 試聽組

素材：
- 人聲：人聲分軌前 8 秒；
- 節奏：full-song-2 r5 drums 第 5–8 小節；
- keys：r5 keys 第 9–12 小節。

手法：
- 範例：往前 1 秒、停 1 秒、往回 0.5 秒；
- freeze：往前 2 拍、停住 2 拍，再從停住處繼續；
- rewind：往前 1 小節，在 1 拍內倒回開頭；
- rock：在半拍內來回 4 次；
- slow stop：2 拍內減速到停。

3～7 秒的輸出，render 只要 0.02～0.05 秒。
