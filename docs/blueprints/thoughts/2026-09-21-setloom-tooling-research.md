# Setloom tooling research

> 2026-09-21 · Repository-grounded reading of `appautomaton/setloom` at commit [`e56d2c2`](https://github.com/appautomaton/setloom/tree/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5). Facts below describe that snapshot; Tactus implications are explicitly marked as inference.

## Bottom line

Setloom 證明的不是「一套 framework schema 可以承載完整音樂製作」，而是另一個更貼近目前討論的命題：

> Agent 可以用普通 Python、NumPy、MIDI 與每首歌自己的資料結構負責創作；shared framework 只需要提供可信賴的分析、MIDI、DSP、rendering primitives，以及讓 agent 持續工作的操作規約。

它的 authoritative source 也不是單一 Python AST。每首 production 的 source of truth 是一個 **source bundle**：Python renderer／instrument code、MIDI performance、JSON／NPZ controls、patch settings、assets 與 production notes 共同構成可編輯作品。Setloom 沒有通用 `build`／`render` project command、Arrangement Graph、material store 或 content-addressed song cache；每首歌自己擁有 entry point 和內部表示，shared package 則刻意不吸收 musical policy。

這讓 Setloom 同時成為 Tactus 的支持證據與反例：

- 支持：creative decisions 留在 ordinary code，framework 提供機械能力，確實能完成並重建真實作品。
- 反例：如果「code as source of truth」被窄化成「所有 truth 都必須是 Python」，會遺失 MIDI performance、control arrays、patches 與 listening decisions 這些必要來源。
- 尚未被 Setloom 驗證：統一 compiled arrangement、semantic diff、incremental materialization 或 graph-only replay 是否值得其抽象成本。

## Observed: Setloom 是 tool collection + agent harness，不是固定 pipeline

官方 README 直接把 Setloom 定義為「music-production tools and agent guidance」，並明說 agent 負責 musical taste、creative judgment 與 production quality。它也明說沒有必經的 CLI sequence，也沒有固定 arrangement template；composition 由 per-track source 負責，shared code 只提供 analysis、MIDI、DSP 和 rendering primitives。[README lines 5–20](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/README.md#L5-L20)

`setloom` CLI 本身只有四類 surface：

- `inspect`：waveform、spectrum、spectrogram、rhythm、stereo 與 A/B visual evidence；
- `transcribe`：Basic Pitch／Kong／fusion 的 note candidates；
- `separate`：寫出全部 separation estimates；
- `play`：在授權下播放指定檔案。

CLI module 的 docstring 還特別註明：musical composition lives in per-track code；parser 也確實只註冊上述四個 commands，沒有 `project`、`build` 或通用 `render`。[`src/setloom/cli.py` lines 2–7](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/src/setloom/cli.py#L2-L7) [lines 126–215](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/src/setloom/cli.py#L126-L215)

Agent 的 production loop 寫在 workflow，而不是被 hard-code 成 pipeline：

```text
musical intent → temporary audition → listening feedback → revision or promotion
```

新 source、analysis、render 與 audition 先待在 `tmp/<track>/`；使用者決定 retain／promote 後，`music/<production>/` 才成為 sole editable source of truth。reviewed artifact 必須保有 identity，production README／working note 負責記錄 current scope、editable source、reviewed render、listening verdict 與下一個 musical question。[`docs/workflow.md` lines 8–27](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/docs/workflow.md#L8-L27) [lines 41–58](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/docs/workflow.md#L41-L58)

這個 harness 的核心控制面是 guidance：`AGENTS.md` 要求 agent 從 intended effect 與 actual material 出發、自己完成 musical work，並只在 recurring code 真正節省重複時新增 CLI operation。Python 是 control plane，但可以搭配 SuperCollider、external tools 或授權的 DAW control。[`AGENTS.md` lines 10–33](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/AGENTS.md#L10-L33) [lines 48–55](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/AGENTS.md#L48-L55)

## Observed: source of truth 是 per-production source bundle

Setloom 的 retained production 並不共享同一套 project schema。幾個 production 展示了不同但相容的 source arrangement：

- **Remissionem**：`performance.json` 是 editable score，`performance.mid` 是 renderer 的直接 performance input，`patch.json` 與 instrument modules 保存聲音和 processing。若改 JSON，必須明確執行 `author_midi.py`；也可直接改 MIDI，但兩者要由作者主動 reconcile，避免 generator 靜默覆寫手改 performance。[`music/remissionem/source/README.md` lines 1–29](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/music/remissionem/source/README.md#L1-L29)
- **Pulsus Noctis**：combined MIDI 是直接 performance，`instruments.json` 保存 instrument、section controls、duration 與 mastering，`instruments.py`／`render.py` 實作聲音、performance 與 mix。[`music/pulsus-noctis/README.md` lines 3–23](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/music/pulsus-noctis/README.md#L3-L23)
- **STRIDULATION**：除了 Python 與 MIDI，兩個 NPZ archives 保存 oscillator amplitudes、tuning 與 stereo control curves；README 明說 Python files alone 無法重建 accepted sound。它還保存 JSON mix stages、delivery settings、dependency versions 與 verification report。[`music/stridulation/README.md` lines 11–36](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/music/stridulation/README.md#L11-L36)

因此「code as source of truth」在 Setloom 的實際含義比較接近：

```text
production source directory
├── Python code
├── performed MIDI / score data
├── patches and controls
├── required local assets and tool identities
└── current musical and listening record
```

它不是「只有 Python 才算 source」。可編輯 performance data 本身是一等來源；Python 負責生成、perform、mix 或 materialize 它。

## Observed: 每首歌擁有自己的 build／render entry point

沒有通用 project compiler。Retained productions 以自己的 command 重建，例如：

```bash
uv run --no-sync python -B music/remissionem/source/render.py \
  --out-dir tmp/remissionem-next

uv run --no-sync python -B music/pulsus-noctis/render.py \
  --out-dir tmp/pulsus-noctis-next

uv run --no-sync python -B music/stridulation/rebuild.py \
  --out tmp/stridulation/rebuilt
```

這些 entry points 通常要求新的／空的 scratch output，拒絕把產物寫進 production source；render 不會播放、啟動 DAW 或發布。Remissionem renderer 從 retained MIDI、score 與 patch 開始，逐 part 合成／呼叫 sampled piano renderer、mix、master，最後寫 delivery WAV 與 `render.json`。[`music/remissionem/source/render.py` lines 42–77](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/music/remissionem/source/render.py#L42-L77) [lines 79–146](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/music/remissionem/source/render.py#L79-L146)

STRIDULATION 的 `rebuild.py` 是另一個 project-owned orchestrator：它呼叫 instrument/mix render，執行 mastering 與 FFmpeg delivery，寫 loudness measurements、output SHA-256、以及整個 source directory 的 SHA-256 inventory；成功後預設刪掉 intermediates。[`music/stridulation/rebuild.py` lines 17–45](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/music/stridulation/rebuild.py#L17-L45) [lines 47–81](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/music/stridulation/rebuild.py#L47-L81)

這代表 Setloom 的 render contract 目前是 convention，而不是 framework-owned IR：entry point、empty-output safety、external tools、reports、stems 與 intermediate lifecycle 都可能由各 production 自己決定。

## Observed: framework owns mechanics; production owns policy

這條界線在 source comments 裡非常刻意。

Shared framework 擁有：

- `audio.py`：audio read/resample、WAV writing、gain/filter、LUFS、true-peak limiting、master delivery checks；例如 `write_master()` 執行明確的 drive／limiter chain 和 encoded-file measurement，但 docstring 強調 composition、bus balance 與 processing choices 留在 production。[`src/setloom/audio.py` lines 358–412](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/src/setloom/audio.py#L358-L412)
- `midi.py`：固定 PPQ、bar/tick math、event validation 與 MIDI writing；per-track code 產生 absolute-tick `NoteEvent`，writer 保證合法輸出。[`src/setloom/midi.py` lines 1–34](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/src/setloom/midi.py#L1-L34) [lines 47–102](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/src/setloom/midi.py#L47-L102)
- `conductor.py`：key／scale／degree／chord-tone math；沒有 energy curves、progressions、harmonic rhythm 或 arrangement defaults，因為那些是 track-specific musical decisions。[`src/setloom/conductor.py` lines 1–7](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/src/setloom/conductor.py#L1-L7)
- inspection、separation、transcription：提供 bounded evidence 與 candidates，不把 model output 當成 musical truth。

Production source 擁有：

- composition、voice grouping、articulation、sound design；
- notes、controllers、patches、routing、effect automation；
- arrangement structure 與 instrument boundaries；
- mix choices、mastering target／drive，以及對 listening feedback 的解釋。

甚至既有 `TrackSpec` schema 也刻意只描述 tempo、key、form、palette 與 intended feel，不 encode generator note-plans；多數欄位是給人與 per-track code 的 descriptive guidance，不是 shared generator 的 inputs。[`src/setloom/schema.py` lines 2–10](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/src/setloom/schema.py#L2-L10)

## Observed: 沒有通用 graph、material store 或 production cache

在這個 snapshot 中，沒有可辨識的 Arrangement Graph／IR，也沒有由 framework 統一擁有的 materialization layer。MIDI、JSON、NPZ、WAV 與 reports 是明確檔案；它們是否為 authoring source、render input、temporary material 或 delivery artifact，由 production directory 與 workflow stage 決定。

官方 tooling 還明確寫道，共用 `write_master()` 的 retained productions 仍把 musical mix preparation 與 level choices 留在 source，而且這條 delivery path **不需要 hash ledger 或 stem cache**。[`docs/tooling.md` lines 61–75](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/docs/tooling.md#L61-L75) Remissionem 正常 render 也不讀 release stems、manifest、reference recording 或先前 render，且不建立 stem cache。[`music/remissionem/source/README.md` lines 3–18](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/music/remissionem/source/README.md#L3-L18)

Caching 並非完全不存在，但它是局部、用途限定的：

- transcription cache 把 stem metadata、route、grid、backend、model asset hashes 與 requested outputs 收進 `cache_inputs`；只有 dossier 完全匹配且所有 outputs 存在才 reuse。[`src/setloom/anatomy/transcribe.py` lines 439–503](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/src/setloom/anatomy/transcribe.py#L439-L503)
- converted ML model assets 有 manifests 與 content hashes；這是 runtime/model integrity，不是 song graph provenance。
- STRIDULATION 的 rebuild report 記錄 source/output hashes，但這是該 production 自己的 verification contract，不是 Setloom-wide material store。

文件也反覆提醒：cache hit、analysis report、event count 或 pipeline completion 都不能證明 musical correctness。這使 cache 明確留在 execution optimization／reproducibility 層，而不是 creative truth 層。[`docs/tooling.md` lines 168–196](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/docs/tooling.md#L168-L196)

## Observed: agent workflow 以「回答 musical question」組裝工具

Setloom 不要求 agent 先完成某張表或依序跑所有 commands。典型 loop 是：

1. 讀 current production source、brief 與 listening record。
2. 找出這一輪真正的 musical question。
3. 必要時用 `inspect`、`separate` 或 `transcribe` 取得 bounded evidence。
4. Agent 自己解釋 voices、gesture、articulation 與 sound；detector output 只是 candidate。
5. 修改 per-track Python／MIDI／controls／patch。
6. 執行 production-owned render，檢查完整 phrase／ensemble。
7. 交付可辨識 audition，將人類 verdict 綁定該 artifact，再 revision 或 promotion。

Skills 強化的是 decision discipline，而不是代替創作的 APIs。Expressive-arrangement skill 要求 agent 一起處理 notes、articulation、timbre、space，並將 editable notes／controls／routing 留在 song source。[`setloom-expressive-arrangement/SKILL.md` lines 8–34](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/.agents/skills/setloom-expressive-arrangement/SKILL.md#L8-L34) Reconstruction skill 則要求 primary agent 親自看 passage 與 plots，不可把 musical inference 委派給別的 agent 或相信 summary。[`setloom-reference-reconstruction/SKILL.md` lines 8–30](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/.agents/skills/setloom-reference-reconstruction/SKILL.md#L8-L30)

Ableton 是旁路 surface，不是核心 truth model。Agent 先 query live session／track state，再用回傳 indexes 修改；MIDI timing 必須放在 MIDI／host automation，不能把 MCP network calls 當 musical clock。公開文件也列出 bridge 當時缺少 device parameter、mixer/send、automation、general note replacement 與 export，因此它不是完整 production API。[`docs/daw-control.md` lines 3–27](https://github.com/appautomaton/setloom/blob/e56d2c247a1962241bef1a6cb1367ed7b0f9aea5/docs/daw-control.md#L3-L27)

## Inference: 對 Tactus 最有用的 architectural seams

以下是從上述 source 推出的設計判斷，不是 Setloom 自己聲稱已驗證的結論。

### 1. Python 應該是 control／creative plane，但 source boundary 要比 `.py` 寬

Tactus 可以維持 code-first，但 authoritative project 應容許：

```text
Python + declarative data + performed event data + assets + environment/tool identity
```

Agent 擅長用 Python／NumPy 寫生成與 DSP；但 performed MIDI、recorded control curves 或 learned／hand-edited arrays 有時就是作品本身，不該被迫重新包成 Python literals。真正的 contract 應該是「可被 code 重建、檢查與版本管理的 source bundle」，不是「所有內容皆為 executable code」。

### 2. 最值得 framework 接走的是 production mechanics，不是 arrangement policy

Setloom 的每首 `render.py` 都重做一部分 orchestration：output safety、scratch lifecycle、external executable lookup、asset validation、part rendering、measurement、reporting。這些是 Tactus 可以 deep-module 化的地方，因為它們跨作品重複，而且 correctness 比 taste 更重要。

相反地，track count、section development、voicing、ducking amount、instrument topology、mix balance 不該被預先固定成 universal workflow。Setloom source 對這條線畫得很清楚。

### 3. Arrangement Graph 必須由 concrete workflows 證明，而不能從 Setloom 成功倒推

Setloom 已證明沒有通用 IR 也能完成作品。若 Tactus 增加 compiled Arrangement Graph，它必須額外買到具體能力，例如：

- isolated audition without rerunning unrelated work；
- semantic diff of notes／tracks／routing；
- validated external-compute replay；
- dependency-aware incremental rebuild；
- precise provenance across generated materials。

如果 graph 只是把 per-song Python 轉成另一份 JSON 後再整首 render，它尚未證明比 Setloom 的 source bundle + entry point 更深。

### 4. Cache 應該是可丟棄的 acceleration layer

Setloom 最好的 cache pattern 是 transcription dossier：把所有 correctness-relevant inputs 明列，缺 output 或 identity 改變就失效；同時拒絕把 cached detection 當 musical truth。Tactus materialization 可以採同樣原則：cache 必須可驗證、可刪除、不可反過來成為作品唯一來源。

### 5. Agent tooling 應以 capability surface 組織，不要規定創作步驟

`inspect`、`transcribe`、`separate` 的價值在於讓 agent 回答問題，而不是強迫每首歌跑同一 pipeline。Tactus 的 commands 也應優先做 deep capabilities，例如 `render`, `audition`, `inspect`, `diff`, `verify`，而把「先寫鼓、再寫 bass、再 master」留給 project code、agent reasoning 與 skills。

### 6. Listening verdict 是另一種 provenance

Setloom 把「哪個 artifact 被聽過、被怎樣評價」當作 production continuity 的一部分，而不是讓最新 render 自動繼承接受狀態。Tactus 若只追 code／asset hashes，仍可能讓 agent 把 rejected render 當 current truth。最低限度應能把 audition identity 與 scoped feedback 對上。

## What Setloom does and does not validate

### Supported by this repository

- Agent 能以普通 Python／NumPy、MIDI 與 project-local data 完成多軌 synthesis、mix、mastering 與 reproducible rebuild。
- Creative policy 留在 project source、mechanics 留在 shared library，是可行且刻意維護的 boundary。
- 每首作品可以有不同 internal representation，只共享低階但可靠的 primitives。
- Source of truth 可以是 versioned editable bundle；rendered audio 是 derived／reviewed artifact，不是 authoring authority。

### Not established by this repository

- 一個 universal arrangement schema 足以表達這些 productions。
- Production-wide graph、content-addressed material store 或 incremental render 是必要的。
- Agent 能透過目前 CLI 或 Ableton bridge 完成所有 DAW operation。
- Hashes、reports 或 deterministic render 能替代 human listening verdict。

## Scope and risks

- 本次只使用官方 `appautomaton/setloom` repository 的 commit `e56d2c247a1962241bef1a6cb1367ed7b0f9aea5`；沒有依賴二手文章。
- Public repo 的 `local/` 內容被 Git ignore，因此 Ableton MCP implementation、proprietary assets 與某些 approved artifacts 無法從這個 snapshot 直接核查；Ableton capabilities 只能依官方 repo 自己保存的 docs／skills 描述。
- `main` 仍可能變動。所有外部引用均 pin 到該 commit，避免後續 schema 或 workflow drift 改寫本次證據。
