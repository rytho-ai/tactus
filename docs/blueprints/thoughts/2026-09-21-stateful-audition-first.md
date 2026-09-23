# Stateful audition first

> 2026-09-21 · 目前的 working conclusion。這份 thought 收斂本輪關於
> code-first production、offline audition、real-time pacing、Production Graph 與 checkpoint
> 的討論及 disposable probes。它支持下一個正式實驗方向，但不宣稱真實 VST 或主觀音樂創作已被驗證。

## 結論

Tactus 應先成為一個以 Python production code 為唯一真相、專為 Agent 提供快速
**stateful audition** 的 production runtime，而不是先成為 real-time DAW。

```text
Python Production Source
          ↓ compile
Derived Production Graph + Material Store
          ↓
Stateful Block Renderer
          ↓
Range / Stem Audition + Metrics
          ↓
Agent edits source
```

這裡的 stateful audition 是指：renderer 按音樂時間分 block 執行，保留 compressor、
sidechain、reverb、delay 與 automation 的跨 block 狀態，但不等待牆上時鐘。相同的
DSP semantics 可以用 real-time scheduler 以 1× 速度執行，也可以用 offline scheduler
盡硬體速度完成；目前 Agent workflow 的預設應是後者。

Agent 在正式修改 source 前試多個候選值的隔離機制，另見
[`Transactional audition`](2026-09-23-transactional-audition.md)。這份 thought 的
stateful execution 證據不等於該 transaction contract 已在正式 runtime 實作。

## Authority boundary

Production code、版本化素材 identity 與 dependency locks 是 source of truth。Git 負責
creative history。Graph、render、metrics 與 checkpoint 都是可刪除、可重建的 derived
artifacts，不得成為另一份需要人工同步的 arrangement。

```text
Versioned source
├── arrangement and musical logic
├── routing and automation decisions
├── effect parameters
└── immutable material identities

Ignored derived state
├── compiled graph
├── materialized computations
├── audition renders
├── analysis metrics
└── checkpoint cache
```

這延續 [`Material identity belongs in production source`](2026-09-21-material-identity-in-source.md)
的界線：material bytes 可以被忽略，但會改變作品的 material identity 必須出現在版本化
source 或 lockfile 中。

## 實驗一：沒有 Audio LLM 的數值 audition loop

### 問題

Agent 能否只靠 Python source、rendered audio 與 NumPy measurements，完成具有明確數值
目標的 mixing 工作？

### 方法

使用現有 `examples/chop-flip`：8 bars、21.3 秒、sample／drums／bass 三個 stems。Disposable
harness 每輪修改複製出的 `mix.py`，執行完整 build 與 render，再從 WAV 量測 peak、RMS 與
stem balance。產品 code 保持不動。

### 結果

| 任務 | 修改前 | 目標 | 修改後 |
|---|---:|---:|---:|
| Mix peak | -8.003 dBFS | -12 dBFS | -12.000 dBFS |
| Mix RMS | -24.967 dBFS | -20 dBFS | -20.000 dBFS |
| Bass 相對 drums RMS | +1.411 dB | -3 dB | -3.000 dB |

三項都在一次計算與 source edit 後命中。完整 build + render 的中位數是 `0.356s`，最慢
`0.370s`；單獨 render 21.3 秒音訊的中位數是 `0.212s`，約為播放速度的 `100×`。

Repeated build 沒有重寫八個 content-addressed materials，但 cold build `0.190s` 與 warm
build 中位數 `0.166s` 的差距很小。當時的 `Project.compute()` 仍會重新執行 computation；
已有的是 storage deduplication，不是 computation cache。

### 能支持的主張

Peak、RMS、stem balance 等 metric-driven tasks 不需要 Audio LLM；快速離散 audition 已足以
形成 code → render → measure → code 的閉環。這不能回答 groove、空間、張力或「好不好聽」。

## 實驗二：offline audition 與 real-time pacing

### 問題

對不依賴主觀聽感的 Agent 任務，wall-clock real-time 是否提供 offline audition 無法提供的
stateful DSP 能力？

### 方法

兩個 conditions 共用相同音訊、50ms blocks、stateful NumPy DSP、候選參數與評分器。唯一
差異是 scheduler：

- **Audition:** block 算完後立刻算下一個 block。
- **Real-time:** block 算完後等待 audio clock，以 1× 播放速度前進。

三個 tasks 分別調 stateful compressor、sidechain release 與 smoothed section automation。
另一個 adaptive-control trial 每 50ms 依前一個 block 更新 gain，共更新 80 次。

### 結果

| 任務 | Audition | Real-time | 結果 |
|---|---:|---:|---|
| Stateful compressor，四個 candidates | 0.007s | 12.005s | 同樣選出 `threshold=-24` |
| Sidechain release，四個 candidates | 0.008s | 16.007s | 同樣選出 `release=0.48` |
| Smoothed automation，四個 candidates | 0.006s | 16.006s | 同樣選出 `(-3, +1.5)dB` |

所有 candidates 的 scores、audio hashes 與 samples 都完全相同。Adaptive-control trial 的 80
次 parameter updates 也得到完全相同的 control trace 與 audio output；offline 花 `0.0015s`，
real-time pacing 花 `4.0006s`。

這些極大的倍率來自簡單的 in-memory NumPy DSP，不是產品效能承諾。可靠的結論只有：
wall-clock pacing 本身沒有增加 DSP semantics；stateful block processing 可以 faster than
real time 執行。

## 實驗三：Agent 實際修改 stateful production source

### 問題

真正的 Coding Agent 能否透過 source edit 與快速 audition，在較長、較多軌且含 stateful
effects 的 production 中收斂？

### 方法

Disposable Tactus-shaped runtime 使用 120 秒、48kHz、32 logical tracks 的 synthetic
production。它包含 stateful compressor、sidechain、reverb tail 與 section automation。
本 session 直接讀取 audition metrics、判斷問題並修改 Python `PARAMS`；沒有內建 optimizer，
也沒有額外 LLM calls。預先要求每項工作最多五次 edit、每次 artifact 五秒內完成。

Agent 共進行三次 source edits：

1. 提高 master、加深並縮短 sidechain、建立 chorus lift。
2. 依第一次結果加大 chorus contrast，同時降低 master 避免 peak 過高。
3. 發現 compressor 尚未實際觸發後，降低 threshold，再平衡 chorus 與 master。

### 最終結果

| 指標 | 預先目標 | 結果 |
|---|---:|---:|
| RMS | -22 至 -18 dBFS | -19.24 dBFS |
| Peak | 不高於 -1 dBFS | -2.25 dBFS |
| Crest factor | 8–18 dB | 16.99 dB |
| Sidechain 最深 | -8 至 -4 dB | -5.87 dB |
| Sidechain recovery | 高於 -1.5 dB | -0.29 dB |
| Chorus − verse | 4–6 dB | 5.07 dB |
| Compressor gain reduction | 必須實際觸發 | -2.08 dB |

40 秒 working audition 約 `0.66s`；120 秒 full render 約 `1.99s`，約為播放速度的 `60×`。

### 能支持的主張

Coding Agent 能用 source、range audition 與數值 observations 完成這組 stateful production
工作，不需要 real-time clock。這仍是 synthetic disposable runtime，尚未證明現有正式
`tactus_code` renderer、真實 audio tracks 或 VST 能得到相同結果。

## 實驗四：checkpoint correctness 與 break-even

### Correctness probe

Full render 在 64 秒保存包含 sidechain、compressor、reverb 與 automation 狀態的 checkpoint。
Region audition 從 checkpoint 恢復，pre-roll 64–66 秒，再輸出 66–74 秒。

- Full render 的 66–74 秒與 checkpoint audition 逐 sample 相同。
- 最大誤差為 `0.0`，decoded samples 的 SHA-256 相同。
- 從頭處理到 74 秒花 `1.20s`。
- 從 checkpoint 處理 10 秒花 `0.17s`，cache hit 約快 `7.1×`。
- Source revision 改變後，舊 checkpoint 因 source hash 不符而被拒絕。

這證明 checkpoint 可以在不犧牲正確性的情況下加速後段 audition，但不代表建立 checkpoint
本身免費。

### Break-even probe

依實測 block cost 推算，建立 64 秒 checkpoint 約需 `1.04s`。將建立、hit 與 invalidation
成本一併計算：

| 同一 revision 的 audition 次數 | 不用 checkpoint | 使用 checkpoint | 節省 |
|---:|---:|---:|---:|
| 1 | 1.20s | 1.21s | -0.6% |
| 2 | 2.41s | 1.38s | 43% |
| 3 | 3.61s | 1.55s | 57% |
| 5 | 6.02s | 1.89s | 69% |
| 10 | 12.03s | 2.74s | 77% |

如果任何 source edit 都讓整份 checkpoint 失效，五輪 edit + audition 是 `6.05s`，比完全不用
checkpoint 的 `6.02s` 稍慢。若 dependency-aware invalidation 讓五輪中只有兩次需要重建，
則可省 `34%`；失效三次只省 `17%`，失效四次便沒有收益。

### 決定

Checkpoint 是已證明有效的 cache mechanism，但不是第一版核心。合理順序是：

```text
Correct stateful audition
        ↓
Dependency tracking
        ↓
Selective recomputation / invalidation
        ↓
Checkpoint cache
```

在 graph 無法判斷 edit 是否影響 checkpoint 以前的 state 時，checkpoint 只會在同一 revision
重複 audition 時獲利。這也替 compiled graph 提供一個具體、非 authoring-schema 的用途：
判斷哪些 cached execution states 仍然有效。

## 收斂後的產品邊界

### Framework owns mechanics

Tactus 應負責每次都必須正確且可重現的 mechanics：

- BPM、musical time 與 sample positions。
- Stateful block execution。
- Routing、latency compensation 與 automation scheduling。
- 已知 DSP／time-stretch algorithms。
- Render requests、metrics、dependency tracking 與 cache invalidation。

### Agent owns creative decisions

Agent 應直接在 production source 中表達會改變作品意圖的選擇：

- Arrangement 與 section development。
- Materials 與 instruments。
- Effect topology 與 parameters。
- Automation shape 與 mix balance。
- 任何需要 musical taste 的生成或變形邏輯。

Shared framework 提供 primitives 與正確執行，不預先把 creative policy 固化為 universal schema。

### Production Graph remains derived

[`Production Graph first behavior probe`](2026-09-21-production-graph-first-probe.md) 已證明 compiled
graph 對 source-free inspection、stable identity、parameter provenance、semantic diff、integrity
checking 與 replay 有用，但尚未證明它必須成為 authoring authority。新的 audition probes 進一步
指出 dependency-aware invalidation 是 graph 可以承擔的具體 runtime responsibility。

這不改變 source-of-truth boundary：Graph 必須由 source compile，不能要求 Agent 同時維護 code
與另一份 arrangement document。

## 現在不做的事情

- **Real-time transport:** 除非 live input、hardware 或某個實際 plugin workflow 證明需要。
- **Audio LLM in core:** metric-driven work 不需要；主觀創作未來透過可替換 Listener 驗證。
- **Checkpoint-first optimization:** 等 state reconstruction 成為實測瓶頸，且 invalidation 能安全判斷。
- **Human/Agent shared editor:** 目前產品範圍是 Agent-first code production，不處理 live collaboration。
- **Universal Arrangement Graph schema:** schema 由真正 consumer 與 production workflow 逐步長出。

## 下一個正式 slice

下一個實作應驗證正式 Tactus runtime，而不是再做 scheduler simulation：

```text
tactus audition production.py \
  --range 32:48 \
  --stems drums,bass \
  --metrics
```

最小 contract：

1. 使用正式 stateful block renderer。
2. 支援 range、stems 與明確的 pre-roll policy。
3. Region audition 必須和 full render 對應區段一致。
4. 回傳 audio artifact、metrics、source revision 與 latency。
5. 先從歌曲開頭或安全邊界重建 state，不先承諾 checkpoint。
6. 記錄 Agent 實際 audition ranges、等待時間與重複次數。

若真實 workflow 顯示 state reconstruction 是主要等待來源，再以 dependency-aware checkpoint
作為下一個 optimization probe。

## Evidence status

| 主張 | 目前狀態 |
|---|---|
| Code 可以作為唯一 creative source of truth | 現有 prototype 支持 |
| Stateful DSP 不需要 wall-clock pacing | Disposable A/B 強力支持 |
| Metric-driven Agent 能靠 audition 工作 | 三組小任務與一次 120 秒 workflow 支持 |
| Stateful region audition 可以正確加速 | Checkpoint exactness probe 支持 |
| Checkpoint 應立即進入第一版 | 不支持；收益依賴重用與精準 invalidation |
| 正式 Tactus runtime 已具備上述能力 | 尚未成立 |
| 真實 VST ecosystem 可完整 offline 執行 | 尚未測試 |
| Agent 能靠 audition 完成主觀音樂創作 | 尚未測試 |
| Tactus 永遠不需要 real-time | 沒有證據；目前只是 evidence-gated |

## Limits

- Stateful probes 使用 disposable synthetic runtime，而非現有正式 renderer。
- 32 tracks 是 logical synthetic voices，不代表 32 軌真實錄音、samplers 或 plugins 的成本。
- A/B 中的巨大 speedup 主要反映取消 audio-clock waiting，不能當作產品效能預測。
- 所有 creative-quality claims 都刻意排除；本輪只測 execution correctness、latency 與 numeric goals。
- Raw evidence 位於執行 session 的 `/tmp/tactus-*-results.json` 與
  `/tmp/tactus-stateful-probe-*`；它們不是 durable project artifacts。這份 thought 保存的是方法、
  數據、判決與限制。
