# Faust vs Numba: owned DSP authoring, verification, and native export probe

這份證據回答「Tactus 若要自己擁有 DSP，是否需要 Faust」。起點是 DawDreamer 為何特別綁定 Faust；結論是 Faust 的語言優勢可被 Python/Numba + Agent 翻譯 + 自動 parity 驗收取代，Faust 保留為演算法參考庫。它延伸 [effect hosting 決策](2026-09-23-effect-hosting-boundary.md) 中「Python + NumPy/SciPy remain valid for Agent-authored DSP」的那一半；不改變 Pedalboard 作為 VST3 host 的方向。每輪事前判定規則皆先寫定；產品程式碼未改。

## 結論

- **Agent 能從 Faust stdlib 原始碼正確移植演算法**：濾波器、VA ladder、waveguide、FDN reverb 皆達 float64 精度等級的一致（−260 至 −308 dB）。
- **Numba 可當 AOT compiler**：`@cfunc` kernel → LLVM IR → `.o`，零手動步驟，無 Python/Numba runtime，輸出與 Python 內執行逐位元相同，速度為 Faust C++ 的 0.79–1.4×。
- **同一條管線可輸出 wasm32**，parity 不變，速度約原生 50–80%。
- **Faust 剩下的不可替代價值只有 stdlib 本身**，適合作為 reference / oracle。
- 此做法適用於任何「逐 sample、有 state 的串流處理」：effect、發聲（ks 已驗）、automation／控制訊號、量測分析；不限於 effect。
- Rytho workspace 目前沒有訓練程式碼，沒有需要可微分 DSP 的情境；PyTorch 版本暫不投資。

## 實驗與結果

| # | 實驗 | 結果 |
| --- | --- | --- |
| 1 | 6 個 Faust stdlib 演算法 × 獨立 Agent 移植（Numba 12、PyTorch 4），golden 由 `faust -double` C++ 產生，參數以 audio-rate input 餵入 | Numba：resonlp／peak_eq／moog_vcf／diodeLadder／ks 10/10 通過；zita 0/2（後證實為 golden 錯誤，見 #4）。PyTorch 3/4 通過 |
| 2 | 單執行緒 RTF | Numba 為 Faust C++ 的 0.35–1.2×；PyTorch forward+backward RTF 0.03–0.07（逐 sample loop，無 batch） |
| 3 | Numba `@cfunc` → IR → `.o`（resonlp、diodeLadder） | 零手動步驟；`nm -u` 僅 libm；與 Python 內 Numba 逐位元相同；block 64/4096 逐位元相同 |
| 4 | zita 2×2：{sonnet, Opus} × {只讀 .lib, 另可讀生成 C++} | 對原 golden 只有讀 C++ 的組吻合；改用正確 golden 後，只讀原始碼的 Opus 2/2、sonnet 1/2 正確，讀 C++ 的組反而連 bug 一起照抄 |
| 5 | Faust delay buffer 根因 | 非 widget 的 raw input 被 interval analysis 視為 [−1,1]，buffer 開 256 而非 ≥960，無警告；`min/max` 無效；`hslider`／`nentry`／常數皆正確 |
| 6 | AOT 大 state：ks（16 KB）、zita（820 KB） | 全部事前條件通過；block 64/4096/37 逐位元相同；0.84–0.86× Faust |
| 7 | wasm32（wasi-sdk 34、node 24） | 兩 kernel −263／−308 dB；與原生差 0 或 ~1e-14 |

## 判斷與邊界

**驗收方法比技術結論更重要。**
- Agent 失敗時會給合理但錯誤的解釋並提前停手（3 例）。驗收只看 parity 數字。
- Golden 自身可能錯。本次靠「多個獨立實作互相一致、卻與 golden 不一致」抓出。多實作互比優先於單一 oracle。
- 參數變化（automation）的測例不可省：2 個 bug 只在時變參數下出現（−77 dB），固定參數時為 −270 dB。
- 靜默錯誤是常態：Faust buffer 過小無警告；wasm 指標錯誤只輸出 NaN。

**用 Faust 當 oracle 時**，參數一律用 `hslider`／`nentry` 或常數，不要以 raw input 餵控制參數；生成 C++ 後檢查 delay buffer 大小。

**Numba 管線的已知限制：**
- Numba 以 host 的 64-bit 指標寬度 lowering；`double**` 參數在 wasm32 靜默讀錯。約定應禁止指標陣列，改傳單一連續 buffer + channel 數（建議，未驗證）。
- LLVM 22（llvmlite）與系統 clang 18 版本不一，需文字 fixup；改用 llvmlite 直接輸出 object 應可消除（未驗證）。
- `memset` 會出現在未定義符號中（clang 向量化 init 清零）。
- zita state 目前僅按 48 kHz 配置；`state_size(sr)` 未實作。

**未驗證：** FFT／頻譜處理（Numba nopython 不支援 `np.fft`）、複音與 MIDI 事件邏輯、denormal 等 realtime 細節、新版 Faust 是否修正 buffer 推算、可微分 DSP 的實用做法。

## 成本與素材

約 3.1M tokens，sonnet 為主，Opus 2 個 Agent。harness、ports、`aot2/CONVENTION.md`（state layout 約定草稿）與建置腳本的原始碼封存於本機 `probes/2026-09-23-faust-vs-numba-dsp/`（gitignored，不進版本控制）；golden／stimuli 資料與編譯產物未收，可依其 README 重建。版本：faust 2.70.3、faustlibraries `36661b5`、numba 0.67.0、llvmlite 0.49.0（LLVM 22.1）、clang 18.1.3、wasi-sdk 34.0。
