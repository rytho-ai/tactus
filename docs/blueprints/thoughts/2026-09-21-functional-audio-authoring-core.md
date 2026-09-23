# Functional audio authoring core

> 2026-09-21 · 目前的 working conclusion。這份 thought 收斂 Track/Bus abstraction、
> functional Python coding discipline、DAW vocabulary 與 minimal authoring API 的 disposable
> probes。它支持第一版 Agent-facing authoring surface，但不宣稱主觀音樂品質或 autonomous
> audition 已被驗證。

## 結論

Tactus 應以 Functional Python + NumPy 作為 Agent 的主要創作語言。Production code 是唯一的
creative source of truth；framework 提供可靠的 mechanics 與少量低假設 primitives，不要求
Agent 先把作品翻譯成傳統 DAW 的 Track、Bus、Session 或 Project object model。

目前最小、已有行為證據的 authoring surface 是：

```python
selected = select(palette, tag="texture")
texture = render_audio(palette, selected)
space = mix((texture, feedback_reverb(texture)))


def render_all() -> dict[str, np.ndarray]:
    ...
```

四個名稱的暫定語意：

- `select(...)` 只選 source identities，不產生 audio。
- `render_audio(palette, identities)` 將 identities materialize 成一個 audio signal。
- `mix(signals)` 合成已經 materialize 的 audio signals。
- `render_all()` 是 production entry point，回傳作品宣告的所有 outputs；`all` 不表示把所有
  source 無差別混合。

這修正了先前過度收斂的判斷：`render` 並非不適合低階操作。只要同一層的語意清楚，
`render_audio()` 與 `render_all()` 可以同時存在而不撞名。

## Responsibility boundary

Framework 應負責每次都必須正確、但本身不構成 creative decision 的 mechanics：

- Musical time、BPM、sample positions 與 sample-accurate automation expansion。
- Audio I/O、immutable material identity 與 deterministic execution。
- 已知 DSP、resampling、time-stretch 與 stateful block processing。
- Audition、validation、dependency tracking、cache 與 checkpoint mechanics。

Agent 應直接在 production source 中決定：

- Materials、arrangement、分組與角色。
- Signal topology、processing order 與 parallel paths。
- Automation shape、effect parameters、stem formation 與 mix balance。
- 依 audio analysis 動態產生的 cohorts、切片與重組方式。

一項規則只有在不同任務中重複暴露相同的機械失敗，才應升級成 framework API。單一作品需要的
helper 不足以成為 core abstraction。

## Evidence 1：Track/Bus 並非必要核心

先前 probes 比較了 plain imperative Python、Functional Python 與 Track/Bus representations：

- 小型 production 中，Functional Python 與 Track/Bus 都能 first-pass 完成，Track/Bus 沒有
  correctness 優勢。
- 48-track production 中，imperative Python 曾因重複計算與 processing order 失敗；加入
  functional discipline 後，Functional Python 與 Track/Bus 都能 first-pass 完成。
- Order-sensitive、stateful topology 可由 Functional Python 清楚表達；已觀察到的失敗來自
  mutation、stage naming 與 nonlinear processing order，而不是缺少 Track/Bus objects。

因此 Track、Bus、Session 與 Project 可以是 metadata、局部 vocabulary 或 optional helpers，
但沒有證據支持它們成為 mandatory authoring schema。

## Evidence 2：命名會影響分解方式，但不影響 correctness

DAW vocabulary 與 neutral operation vocabulary 各跑三個隔離 Agent trials。兩組都是 3/3
first-pass 通過，沒有 framework escape 或表示能力差異。

DAW condition：

```python
select_tracks / mix_tracks / mix_route / send / mix
```

Neutral condition：

```python
select / combine / combine_family / parallel / merge
```

Neutral 組 19 次 selection 中有 15 次依 `tag` 重組、4 次沿用固定 `family`；DAW 組 12 次
selection 中各有 6 次依 `tag` 與既有 `route`。這是 naming 會改變 Agent 第一時間如何分解問題的
方向性證據：DAW terms 產生沿用既有 routing 的重力，neutral terms 較鼓勵依內容重新組合。

這不能證明 neutral naming 會讓音樂更有創意或更好聽。沒有 Audio LLM 或 human blind listening
時，code topology 的不同不能被升格成 creative-quality claim。

三個 DAW trials 都沒有使用 `send(...)` 或 `mix_route(...)`；三個 neutral trials 也都沒有使用
`combine_family(...)`。Agent 普遍偏好 identity selection、materialization 與 signal combination
三個基本階段，支持繼續縮小 API，而不是補齊 DAW mixer vocabulary。

## Evidence 3：Minimal API escape-pressure probe

三個 fresh Agent sessions 共用相同 framework 與 functional rules，只改 production brief：

1. **Spatial/spectral:** explicit mid/side、兩條獨立 spectral/spatial paths、group-level nonlinear
   processing。
2. **Alternating roles:** caller/responder 每三秒交換主從，同一 source collection 隨時間改變角色。
3. **Analysis-driven:** 不用 names、tags 或 families 決定角色；直接從 48 個 audio arrays 計算
   RMS、zero-crossing activity 與 stereo spread，再依 runtime quantiles 建立 cohorts。

三題都得到有效 output，而且只有 `candidate.py` 被修改。所有 trials 都：

- 保留 `render_all()` entry point。
- 只將 identities 傳給 `render_audio()`。
- 只將 audio signals 傳給 `mix()`。
- 沒有修改 protected framework files。
- 沒有自行建立 Track、Bus、Session 或 Project model。

這支持 `select + render_audio + mix + render_all` 對三種陌生 topology 具有足夠的表達能力與可理解性。
它仍是 small-N disposable probe，不是 universal completeness proof。

## Pure-side correction：validator 不得偷渡 taste

Spatial trial 第一次產生 pure-side width layer：

```text
Left  = +Side
Right = -Side
```

這在 stereo 中極寬、fold to mono 時會抵消。External judge 額外要求 width layer 保留 audible
mid content，因此 Agent 第二次才得到 `PASS`。原 brief 沒有禁止 pure-side；它可以是合理的
creative mixing decision。

這次 failure 不算 API misunderstanding、framework insufficiency 或 mid/side helper 的必要證據。
它反而建立 validator boundary：

> Validator 檢查明文 technical invariants，不得把未宣告的 mixing taste 偽裝成 correctness。

適合自動驗證的內容包括 shape、dtype、finite values、determinism、peak safety 與明確宣告的 timing
relationship。Width 必須保留 mid、bass 必須置中或 reverb 必須採特定比例，都屬於 creative
policy，除非 brief 明確要求，否則不能成為 hidden correctness rule。

## Repeated gap：temporal control expansion

兩個獨立的時間型 tasks 都重複手寫 section-level values 到 sample-level control 的展開：

```python
section = np.arange(FRAMES) // section_frames
control = levels[section, None]
```

或以 imperative slicing 組裝：

```python
for start, stop in section_edges:
    signal[start:stop] = ...
```

兩個 Agents 也都主動希望 framework 提供 section automation helper。這是本輪唯一達到「不同任務
重複出現」門檻的 framework candidate。合理的下一個 probe 應測試類似：

```python
control = section_envelope(
    levels=[1.0, 0.2, 1.0, 0.2],
    boundaries=[0, 3, 6, 9, 12],
)
```

Agent 仍決定 levels、boundaries、interpolation 與 control 的用途；framework 只負責正確、
sample-accurate、可重現的 expansion。這符合「framework owns repeated math，Agent owns creative
policy」的邊界。

兩個時間型 trials 同時出現 `+=` 或 slice assignment。它們沒有修改 source arrays，也未造成輸出
錯誤，但違反 fixture 的 strict no-in-place-mutation rule。Temporal helper 是否能自然消除這類
imperative assembly，是下一個實驗應觀察的次要指標。

## Current decision

第一版 Agent-facing authoring direction 暫定為：

```text
Functional Python + NumPy
        ↓
select identities
        ↓
render_audio identities into signals
        ↓
Agent-authored DSP and topology
        ↓
mix completed signals
        ↓
render_all declared outputs
```

暫時不加入：

- Mandatory Track/Bus/Session/Project models。
- `send`、`mix_route` 或其他預設 DAW topology 的 core API。
- Mid/side core abstraction；目前只是一個 task-local convenience candidate。
- Creative mixing policies in validators。
- Hand-authored Arrangement Graph 作為第二份 source of truth。

若 runtime 需要 dependency analysis、cache invalidation、checkpoint selection 或 replay，graph 應由
production source compile/trace 而來，維持 derived artifact 身分。

## 尚未驗證

### 會影響近期設計

1. **Temporal primitive:** `section_envelope` 是否能減少重複數學、boundary mistakes 與 in-place
   mutation，而不接管 creative shape。
2. **Real production integration:** 這組 API 尚未接上正式 `tactus_code` renderer、真實 audio
   materials、musical time 或 stateful audition contract。
3. **Targeted rendering:** `render_all()` 已被正確理解，但 `render_stem()`、`render_range()`、lazy
   materialization 與只執行 requested outputs 尚未測試。
4. **Feedback and dynamic graphs:** feedback cycles、runtime-generated sources、variable-length events、
   MIDI/event-to-audio 與 multichannel formats 尚未納入 escape-pressure probe。
5. **Validation contract:** technical invariants、creative goals 與 subjective evaluation 如何分層，尚未
   形成正式 contract。

### 可以延後

1. **Audible creative quality:** Neutral vocabulary 是否真的產生更好的音樂，需要 Audio LLM 或
   human blind listening；目前只觀察到 code topology bias。
2. **Autonomous audition:** Agent 能否依離散 audition 自主改善 groove、張力、空間與情緒，尚未
   驗證。
3. **Plugin compatibility:** VST3/AU offline rendering、plugin state serialization、latency 與
   nondeterminism 尚未測試。
4. **Real-time need:** Live input、hardware monitoring 或 human live collaboration 未進入目前產品
   scope；不能由現有 offline probes 推論永遠不需要 real-time。
5. **Human editor:** 目前沒有證據要求 bidirectional canvas/editor；Tactus 仍以 Agent-first code
   production 為範圍。

## Evidence limits

- 所有 probes 使用 synthetic NumPy audio 與 disposable fixtures，而非正式 product runtime。
- Trial 數量小，Agent model 與 prompts 固定；跨模型、跨 session 的普遍性仍有限。
- Behavioral judges 驗證 technical structure 與數值關係，不評估音樂是否好聽。
- Scratch fixtures 位於 `/tmp/tactus-functional-*`、`/tmp/tactus-order-sensitive-*`、
  `/tmp/tactus-daw-naming-*`、`/tmp/tactus-vocabulary-bias-probe.uyINVT` 與
  `/tmp/tactus-minimal-api-probe.BBq4SS`；它們不是 durable project artifacts。本 thought 保存的是
  方法、證據、判決與限制。
