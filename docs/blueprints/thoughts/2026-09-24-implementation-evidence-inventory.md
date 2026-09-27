# Tactus 完整實作盤點與清單

> 2026-09-24 · 依 Paul 要求重新盤點。程式基準：`9feccdd`。
> 範圍：新版 repo 原有的全部 45 份 thoughts、舊 repo 轉向起點的 6 份
> 2026-09-15／16 thoughts、現行 source／examples、實作計畫的完成紀錄、兩次
> real-source dogfood，以及本機 Faust／Numba probe 的封存說明與介面草稿。
> 這是有日期的證據盤點，不是新的優先序看板或 API 承諾；目前狀態仍由 `../plan.md` 維護。

## 結論

主要尚待實作的責任有八項：**時間工具、素材 ID 與載入、transactional audition、
Git 整合、stateful 區段試聽、效果器整合、執行追溯，以及讓 Agent 具備 functional 寫作能力**
（A8 為同日依 Paul 要求補入）。另外兩條已有依據的製作路徑是
**MIDI／連續樂器演奏**與 **time stretch 的環境及介面整合**；其中已有作品內實作，
不表示要從零另建引擎。

Pattern、自有 DSP、觀察／比較工具、創作手法 guidance 也不能漏掉，但其產品化範圍應依需求決定。
「實驗通過」不等於「每個實驗函式都必須變成 core API」。

本次對話已確認近期專注歌曲／arrangement 製作，暫不規劃 session／live 或更廣的輸出形式。
這個範圍不要求新增 mandatory Arrangement、Track 或全曲 BPM。

## 閱讀方式與總清單

本清單回答「已有證據支持哪些工作、還缺什麼」，編號用於查找，不表示開工順序。
`[x]` 表示在本次盤點基準已交付；`[ ]` 表示尚未完成。C 類清單只有在具體需求成立後才啟動，
不必全部勾完才能交付第一版。需要決定的介面列在各項正文，範例名稱不是已核准的 API。
這是 2026-09-24 的快照；後續執行在 [現有看板](../plan.md) 連到對應實作計畫，
保留本次盤點作為當時的理由與範圍。

| 編號 | 能力 | 盤點時的狀態 | 剩餘工作的性質 |
| --- | --- | --- | --- |
| [A1](#a1) | Temporal abstraction | 實驗支持；正式 helper 未交付 | 最小介面設計、實作、既有作品採用 |
| [A2](#a2) | 音檔／素材 ID 與載入 | 輸出 store 已有；輸入靠作品自行處理 | 固定引用、resolver、驗證與搬移 |
| [A3](#a3) | Transactional audition | 參數候選已有基礎 | Immutable base、接受流程、衝突處理 |
| [A4](#a4) | Git 原生整合 | 已確認產品方向；runtime 未整合 | 版本歸因、隔離探索、修訂銜接；介面未定 |
| [A5](#a5) | Stateful 區段試聽 | 實驗支持；正式介面未交付 | 區段／output 選擇、上下文、latency／tail 正確性 |
| [A6](#a6) | Pedalboard helpers | Backend 方向已定；正式整合未交付 | 參數、資料銜接、state、automation 排程 |
| [A7](#a7) | 執行追溯與環境重建 | 基本 receipt 已有 | 宣告外部輸入與 processor、環境和聆聽歸因 |
| [A8](#a8) | Agent 的 functional authoring 能力 | 實驗中以 fixture 規則提供；產品未交付 | Agent 可讀的寫作紀律與執行契約、範例、fresh-Agent 驗收 |
| [B1](#b1) | MIDI／連續樂器演奏 | 作品內路徑與實驗已有 | 接入 runner、素材與追溯；按需求抽取 adapter |
| [B2](#b2) | Time stretch／marker warp | 固定比例已可用；marker 有實驗 | 可重建環境；marker adapter 按歌曲需求決定 |
| [C1](#c1) | Pattern helpers | 有限實驗支持可用性 | 第二個實際 consumer 出現時抽取 |
| [C2](#c2) | 自有 DSP／Numba | 有移植、AOT／WASM 實驗 | 自有 processor 有需要時產品化 |
| [C3](#c3) | 分析與比較交付 | 分析套件已有；臨時 A/B page 已使用 | 按重複需求整理觀察及試聽 consumer |
| [C4](#c4) | 創作手法 guidance／examples | 產品方向；效果證據仍有限 | 可選說明與範例，實際使用後評估 |

各項依據見正文及文末的 [完整查核索引](#evidence-index)；[已完成基礎與延後項目](#completed-and-deferred)
另列，避免把所有曾研究的方向都當成待辦。

## 如何判讀歷史證據

- [產品原則](../../positioning.md) 與 [當前設計](../../design.md) 是目前的判斷依據。
- `render(*, ...)`／`run` 已取代實驗中的 `render_all` 等入口名稱；早期名稱不是待補 API。
- [prototype retirement](../plans/2026-09-24-retire-arrangement-prototype.md) 已移除
  Project／Track、compiled arrangement 與 build／inspect／render／diff commands。
  歷史文件寫「目前支援」時，要依當時的程式理解，不能視為現在仍存在。
- 早期「假 BPM 才能 render」的缺口，已由接受普通音訊 arrays 的入口消除；時間 helper 仍未實作。
- `pyloudnorm`／`librosa` 的 optional 建議已被 Paul 後來的 default-dependency 決定取代，且已安裝與鎖定。
- Git 整合是本次對話加入的產品方向。既有 probe 支持 Git 保存歷史與重建；它們沒有驗證
  一套新的 Tactus Git commands。介面需分開設計。
- 本次重讀保存的結論與可用程式，沒有重新執行所有實驗，也未逐一稽核所有 `/tmp` 原始 trial。
  舊 repo 更早的 DAW backlog 不自動繼承為新版需求。

## A. 主要實作責任

<a id="a1"></a>

### A1. Temporal abstraction：共用時間運算

**工作：**把重複的 placement、repetition、時間縮放、段落 automation 與 sample rounding
收成可選工具。作品決定位置、曲線、例外與 clock；工具負責算對。確切函式與資料型別仍待計畫。

**證據：**functional trials 重複手寫 section control；Hybrid 六種 arrangement 修改通過；
舊 Setloom tempo-ramp probe 實際發現只讀第一個 tempo 的靜默錯誤，必須讓 notes、CC、pulse、
automation 與曲長使用同一換算。這已足以支持進入最小實作，無須重做價值探索。

**邊界：**mixed-clock probe 證明 Python 足以表達混合時間，沒有證明強制 clock class 必要。
Setloom 測的是以 0.25 beat 步進近似的 ramp；不是任意連續 tempo、rubato 或巢狀 clock 的完整驗證。
MIDI endpoint-warp helper 的獨立 Agent 比較未顯示可靠度優勢，不應把它自動併入第一版。

**現況與驗收：**`src/tactus/` 無 temporal module。先讓已存在的作品採用最小 helper，
用既有修改案例驗收邊界、取整與修改範圍；不要求另一輪大型作品實驗。

**實作清單：**

- [ ] 從既有案例選定第一批共用運算及採用它們的作品函式。
- [ ] 定義時間單位、區段端點、取整、越界及輸入 mutation 的明確規則。
- [ ] 實作最小工具，保留普通 Python 與不使用全曲 BPM 的途徑。
- [ ] 將實際作品接上工具，驗收搬移、重複、變化、時間縮放及 automation 邊界。
- [ ] 對採用的 clock 換算驗證修改影響範圍：跟隨 beat 的內容移動，絕對時間內容保持固定。

<a id="a2"></a>

### A2. 音檔／素材 ID、載入與搬移

**工作：**從本機檔案取得固定的內容身分，讓 source 或 tracked lock 明確引用；依 ID 找回與
驗證內容。缺檔、錯誤內容需明確失敗。換 sample 必須形成 source／lock 的 Git diff。
素材 bytes 可以留在 Git 外；搬移作品後可重新提供相同素材，無須改創作身分。

**證據：**material-identity thought；Python＋Git clean clone 缺素材；Setloom 的 machine-local
sample paths 擋住 render；sampler 缺素材的 18 次測試全部靜音但未報錯，明確清單全部找出缺檔。

**現況：**`MaterialStore.add/read` 已針對交付的 PCM24 WAV 做 hash 儲存與驗證；
`examples/real-chop-flip/materials.py` 自行固定輸入音檔與 `.npy` 的 hash。尚無通用的
輸入素材匯入／固定引用／resolver 流程。舊 `Project.file/asset_region` 已退役。

**需明訂：**原始檔 bytes 的 ID、解碼／轉換後的素材 ID、音檔區段與處理參數的關係。
目前輸出 ID 是編碼後 WAV bytes 的 SHA-256，不能宣稱不同編碼但聽起來相同的檔案共用 ID。
音檔以外的 beat-grid、MIDI、patch、control arrays 與已宣告 sampler assets 也會改變聲音，
要容許固定這些輸入。Plugin opaque state 不代表其外部依賴已完整保存。

讀取音檔時還需明訂區段 bounds、sample rate／channel layout，以及有效但超過 full scale 的
decoded input 如何交給作者處理。需要不同 rate 時明確 resample，不改標籤冒充轉換，也不默默
normalize。Bounded read 可直接復用 SoundFile；是否新增共用 adapter 依採用端決定。

**驗收：**換路徑不換內容仍能取得同一素材；改內容須明確更新身分；缺檔／損壞可診斷。
雲端同步、通用素材庫搜尋與 garbage collection 不屬於第一個必要範圍。

**實作清單：**

- [ ] 選定 inline digest 或 tracked lock 的固定引用方式，定義原始檔與衍生音訊的身分。
- [ ] 提供取得素材 ID、依 ID 解析內容與完整性驗證的最小流程。
- [x] 將非音訊 sidecar 與明確宣告的 instrument／plugin assets 納入同一輸入身分機制。（2026-09-27 補記：`material()` 可釘任何檔案、`tree:` ref 釘資料夾、`tool()` 釘外部執行檔與插件；real-chop-flip 以此釘住 beat grid。）
- [ ] 接上既有作品的素材讀取，明訂 rate、channels、區段與 headroom 處理。
- [ ] 驗收同內容換路徑、內容遭替換、素材遺失／損壞及另一目錄重建。
- [ ] 驗收更換素材會留下 tracked identity 的 Git diff。

<a id="a3"></a>

### A3. Transactional audition：候選與接受

**工作：**固定同一份 base，產生隔離候選，將參數與 outputs 對上；捨棄不改正式 source；
接受時檢查 base 與目標尚未變更，再形成一次明確修訂並重建確認。

**現況：**`run(params=...)` 已提供每次新 process、新輸出目錄、有效參數紀錄，以及
執行前後的有限 source inventory 比對。這不是 immutable source snapshot，也沒有 promotion API。
實際聆聽保留 A 時，source 原本就等於 A，未曾驗收正式 promotion。

**驗收：**兩候選從同一 base 出發；丟棄不留 source 修改；接受後重建符合候選；
base 已被人或其他 Agent 修改時報衝突。先限明確參數；任意 Python 結構修改需獨立 snapshot／worktree 策略。

**實作清單：**

- [ ] 定義 base snapshot 包含的 source、資料與素材參照，並明確記錄未包含的外部輸入。
- [ ] 讓同批參數候選使用同一 base，各自保存有效參數及結果。
- [ ] 提供明確接受操作：檢查 base 與目標、修改一次、重建核對；限定可支援的參數形式。
- [ ] 驗收兩候選不互相繼承參數／state，丟棄不修改正式 source。
- [ ] 驗收接受後輸出符合候選，以及 stale base／目標已變更時拒絕覆蓋。

<a id="a4"></a>

### A4. Git 原生整合

**工作：**把實際執行的 source snapshot、Git base、未提交的 source 差異與候選連起來；
結構性實驗可使用 worktree；可檢視 diff、接受修訂，並在明確操作下 commit 或回到歷史版本。

**證據：**9/15、9/16 probes 已使用 branch、commit、clone、回復及新 process 重建；
本次 Paul 要求納入 Git 支援。現在 runtime 不記錄 Git revision，也不提供這些候選整合。

**邊界：**commit hash 不能代表含未提交修改的實際 source；snapshot 清單仍須定義。
不需要另建 history DAG／op-log，不假設音樂變更能自動語意合併，也不要求一般 render 前先 commit。
直接用 Git、薄 adapter 或少量 CLI 的分界未定；不因列入方向而包裝每個 Git command。
不採用 GitPython（2026-09-24 Paul 拍板）：它的 porcelain 操作本身即呼叫系統 `git`，worktree 無
正式 API，專案處於 maintenance mode，且安全公告集中在轉發 CLI options 的注入；所需的 HEAD、
dirty paths、worktree、diff 與 commit 操作直接以 list 參數呼叫 `git`（路徑前加 `--`）即可。

**實作清單：**

- [ ] 選定 Git 整合的最小介面，以及與 A3 共用的 source snapshot 身分。
- [ ] 記錄 commit 與實際未提交 source 的差異，避免把 HEAD 當作實際執行版本。
- [ ] 為結構性探索決定 worktree／snapshot 隔離方式及候選保留、清除流程。
- [ ] 將 diff、接受修訂及明確 commit 操作接到同一候選身分；render 不自動 commit。
- [ ] 驗收已有未提交修改、並行修改、版本回復與新目錄重建；不得覆蓋無關改動。

<a id="a5"></a>

### A5. Stateful range／output audition

**工作：**讓指定區段／具名 output 的試聽保留前置 DSP state、latency 對齊與尾音政策，
候選間不互相污染。使用者要聽副歌時，不能丟失前面累積的 delay／reverb。

**證據：**stateful audition experiments 及 Pedalboard chain probe 已測到冷啟動區段錯誤、
dirty state 污染、截尾與 latency 差異；從開頭重建後裁切可對上完整輸出。

**現況與驗收：**目前只有完整 arrays 的執行。第一版可先完整 render 再選區段，
以 full-render 對應 samples 作驗收。具名 output 是作者的結果，不推定所有 stems 可相加還原 mix。
只算需要的區段／聲部是後續效率工作；checkpoint 不應成為正確性的前提。

**實作清單：**

- [ ] 定義區段單位、起訖端點、具名 output 選擇與尾音交付政策。
- [ ] 以完整執行後裁切或從安全起點重建 state 的方式提供第一版。
- [ ] 記錄實際返回區段與其在完整作品中的位置。
- [ ] 使用有可測尾音及 latency 的案例，比對 audition 與完整輸出的相應 samples。
- [ ] 驗收連續候選的 state 隔離，並記錄實際等待時間，作為之後是否優化的依據。

<a id="a6"></a>

### A6. Pedalboard helpers 與效果器執行

**工作：**整合已選 backend，集中處理 parameter inspection／validation、必要的 metadata 修正、
channel layout、明確 assets、設定保存／還原、分段 automation、state continuity、latency 與 tail。
按實際 consumer 分步加入，不先承諾 universal chain schema。

**證據：**參數與 cross-process restore probes；segmented automation 的精確切點與 delay continuity；
latency／tail／state probe。創作選擇、處理順序、曲線與 routing 留給 Agent。

**現況：**新 runtime 未整合 Pedalboard；real-chop-flip 使用作品內 SciPy effects。
Pedalboard 也不在目前 base dependency declarations 中。

**邊界與驗收：**用實際選定插件驗證 handoff、fresh instance、參數切換及區段正確性。
分段改值不是 VST3 單次呼叫內的 sample-offset automation queue；plugin 設定保存不是完整 DSP checkpoint。
External sidechain 是已證實的能力缺口，待歌曲真的需要時比較窄 native extension；不先重建整套 host。

**實作清單：**

- [ ] 決定 Pedalboard 的 dependency 安裝範圍及已驗證的 Python／平台環境。
- [ ] 實作實際插件需要的參數讀寫／驗證與 channel-layout 銜接。
- [ ] 串接 A2 的明確資產檢查，保存及還原選定插件的設定。
- [ ] 實作保留 state 的分段 automation 與明確 reset 生命週期。
- [ ] 對支援的處理路徑明訂 latency 對齊與 tail 處理，銜接 A5。
- [ ] 驗收實際插件的 fresh-process 還原、automation、聲道身分及缺資產失敗。

<a id="a7"></a>

### A7. 執行追溯與環境重建

**工作：**提供作者可宣告的輸入／processor／環境歸因方式，把 output、參數、source、素材、
lock、外部 executable／plugin 身分連在同次紀錄裡。保存聆聽 verdict 時，指向確切 artifact，
不要讓後來的 render 自動繼承接受狀態。

**證據：**real-source warp 與本次 dogfood 都必須手動補 Rubber Band 等版本；舊 sidecar
dogfood 曾漏掉影響剪輯位置的 `.npy`；Setloom 研究指出 non-Python controls 也是 source。

**現況：**receipt 只 inventory entry 目錄下 `.py` 與該目錄 `uv.lock`，並記錄
Python／Tactus／NumPy／SoundFile。Nested example 的 root lock 可能因此未記入；外部 imports、
素材、SciPy、processor 等不會自動完整追蹤。五個 base packages 已有 repo lock，不能混稱缺依賴管理。

**驗收：**至少把已知真實製作的 sidecar、素材、processor、有效 lock 與所選音訊對上；
重現缺依賴時給出可採取行動的診斷。Seed／randomness 由 source 明確控制；固定單一 seed
不保證插入一個事件後其他隨機結果不變。是否提供局部 random stream helper 仍待需求。
不承諾推斷任意 Python 的全部依賴或跨平台 bit-exact rebuild。

**實作清單：**

- [ ] 定義作者宣告外部輸入、processor 與有效 dependency lock 的最小方式。
- [ ] 擴充 receipt，引用 A2 素材身分與 A3／A4 實際 source 基準。
- [ ] 記錄 production 使用的外部 executable／plugin 版本、設定身分與明確 randomness inputs。
- [ ] 為缺失依賴、工具與素材提供可採取行動的診斷，完成選定作品的環境重建說明。
- [ ] 保存候選、輸出與有範圍的聆聽 verdict 對應；新 render 不自動繼承接受狀態。
- [ ] 用真實來源、sidecar、Rubber Band 或插件核對 receipt，再到另一目錄驗證重建流程。

<a id="a8"></a>

### A8. Agent 的 functional authoring 能力

> 2026-09-24 同日補入，依 Paul 要求；原盤點未列此項。

**工作：**讓第一次接手的 Agent 不靠實驗 fixture 的提示，也能用 functional 方式寫作品：
函式明確表達輸入、輸出與處理順序，不修改傳入的 arrays 或共享狀態，階段有可辨識的名稱，
最後由 `render(*, ...)` 回傳宣告的 outputs。同時讓 Agent 能自行查到 `render`／`run` 的執行
契約（參數綁定、輸出限制、manifest／receipt 欄位、錯誤結構），不必讀 `run.py` 才能使用。

**證據：**[Functional authoring](2026-09-21-functional-audio-authoring-core.md) Evidence 1：
48-track production 中 imperative Python 因重複計算與處理順序失敗，加入 functional discipline
後 first-pass 通過；已觀察到的失敗來自 mutation、stage naming 與 nonlinear processing order。
同一份文件記錄兩個時間型 trials 出現 `+=`／slice assignment，違反 fixture 規則但未造成錯誤。
這些紀律在實驗中由 fixture 提供；產品目前沒有等價的 Agent 可讀來源。

**現況：**[`docs/design.md`](../../design.md) 以一句話描述 functional 分解；`README.md` 與
`examples/functional/README.md` 說明 CLI 與 JSON 結果，但沒有寫作紀律、沒有 manifest／receipt
schema。`AGENTS.md` 只指向產品文件。`examples/phonon-ballad/` 仍是獨立 CLI，不是可模仿的
functional 範例。

**邊界：**這是寫作紀律與可發現性，不是新的 authoring API 或強制 style checker。
依 [產品原則](../../positioning.md) 第 3 條，Agent 自寫 NumPy 是正常創作；函式內對自己建立的
array 做 `+=` 不應被當成錯誤，要守的是不修改輸入與共享狀態。Runtime 是否另加檢查（例如輸入
arrays 唯讀）需要實際錯誤證據才啟動。承載形式（作品目錄的 `AGENTS.md` 範本、Agent skill、
套件內文件或 `tactus` CLI 說明）未定；與 C4 的創作手法 guidance 分開，這裡不教音樂手法。

**驗收：**Fresh Agent 只拿到產品提供的說明，從零完成並修改一首含多階段處理的作品；
記錄 first-pass 成功、輸入 mutation、處理順序與重複計算錯誤，與實驗中的 fixture 條件比較。
技術通過不代替聆聽判斷。

**實作清單：**

- [ ] 選定 Agent 取得寫作紀律與執行契約的承載形式及放置位置。
- [ ] 寫出 functional 寫作紀律：輸入不變、明確資料流、階段命名、處理順序、render 邊界。
- [ ] 文件化 `render`／`run` 契約與 manifest／receipt 欄位，並與 `run.py` 保持同一來源。
- [ ] 提供至少一個採用真實素材、多階段處理的 functional 範例，並納入 regression 驗收。
- [ ] 以 fresh-Agent trials 比較有無說明的結果，決定是否需要 runtime 檢查。

## B. 已有依據、需要接入製作流程的能力

<a id="b1"></a>

### B1. MIDI 交換與連續樂器演奏

這裡有兩個不同接縫：

- **事件／檔案：**Python 決定 notes、timing、velocity、CC、bend；需要 Standard MIDI File
  時採用 Mido。保留 untouched events、release velocity、channel 及同 tick ordering 的明確政策。
- **事件／聲音：**保留整段 performance，送到 sampled instrument／VST；驗證 pedal、velocity、
  note overlap、tail 與 state。早期鋼琴盲聽支持 SFZ 作為免費 baseline，不支持逐音固定力度 bounce。

`examples/phonon-ballad/song.py` 已有作品內 MIDI writer 與 `sfizz_render` 整段演奏路徑，
但它是獨立 Python CLI，未接目前的 functional run contract；相關 instrument/sample 環境亦非
通用、可搬移的正式整合。這是復用與銜接工作，不是缺少全部發聲能力。

優先用既有演奏接上素材／receipt／run，再判斷哪些 adapter 值得共用。Mido 不必成為每首作品
的必要依賴；不新增 universal Note／Score／Track model。商用 piano 與所有 VST 相容性延後。

**整合清單：**

- [ ] 選定既有 MIDI／SFZ 作品作為採用端，補齊其素材與 renderer 身分。
- [ ] 將完整演奏接到 functional `run` 的音訊交付流程。
- [ ] 需要 MIDI 檔案交換時接 Mido，明訂受支援事件與 preservation 政策。
- [ ] 驗收 notes、velocity、CC／pedal、bend、同 tick ordering 及未修改事件的保留。
- [ ] 驗收連續 instrument render 與尾音，交付可聽版本；依重複需求抽出共用 adapter。

<a id="b2"></a>

### B2. Time stretch／marker warp 的整合

固定比例 Rubber Band 已在 real-chop-flip 使用作品內 Python 成功執行；必要性 probe 未支持
新增 core `stretch_to_duration()`。目前仍需決定可重建的 production dependency 安裝方式與
processor 身分紀錄；現有 `pyrubberband`＋system executable 只是本機可用環境。

Marker warp 已有行為證據，binding、R2／R3、temporary encoding 與 output length 均影響結果。
若歌曲需要 marker-based warp，再決定正式 adapter、map 驗證與長度政策；不承諾瞬態 sample-accurate。
沒有理由為完成歌曲 runtime 同時引入多個 stretch engines 或另開通用 OpenMIRLab package。

**整合清單：**

- [x] 以作品內 Python 呼叫 Rubber Band 完成固定比例的真實素材製作。
- [ ] 定義這條 production 路徑的可重建安裝方式，將 wrapper／engine 身分接入 A7。
- [ ] 若歌曲需要 marker warp，再選定 binding、engine 設定、map 與長度錯誤政策。
- [ ] 對正式採用的 marker 路徑驗證輸出長度、transient 偏差、聲道與聆聽結果。

## C. 保留方向，按具體需求產品化

| 項目 | 已有證據與可做內容 | 現在不應推論的事 |
| --- | --- | --- |
| Pattern helpers | Euclidean、rotation、polymeter、週期變換可以局部函式表達；將重複數學集中，有第二個實際 consumer 時抽取 | 三題皆通過不等於可靠度提高；不需整套 Pattern subsystem、全曲 Event schema 或 mini-notation |
| 自有 DSP／Numba | 有 state 的 filters、synthesis、reverb 移植及 AOT／WASM 已有有限 parity 證據；需要自有 processor 時可採用並延續 block／時變參數驗收 | 封存 ABI 有 48 kHz、pointer width、LLVM 等限制；尚非產品 export pipeline，不立即移植整個 Faust library |
| 分析與比較交付 | 基本測量可直接用已裝套件；實際 dogfood 重做 A/B page 與聆聽 artifact 對照，值得整理可重用 consumer | 不必重建 `inspect`；player 可在 runtime 外；LUFS matching 不是自動修改 master，analysis 不是 taste judge |
| 創作手法 guidance／examples | Sampling affordance 顯示可以讓 chopping、retrigger、ending variation 等手法更容易被想到 | 兩次 replicate 未達嚴格 incremental 勝出規則；先以可選說明／範例承載，不把 `chop/play_slices` 升成必要 API |

以下是條件成立後的工作清單；勾選前須先確認正文所列需求成立。

<a id="c1"></a>

### C1. Pattern helpers

- [ ] 找到第二個實際 consumer，選定它們共同需要的規律運算。
- [ ] 實作可選的局部 helper，保留一次性例外由 Python 直接表達。
- [ ] 驗收 cycle／phase／週期變換次序，確認採用後確實減少重複或錯誤。

<a id="c2"></a>

### C2. 自有 DSP／Numba

- [ ] 從實際需要自有實作的 processor 開始，定義 state、buffer、parameters 與 sample-rate 範圍。
- [ ] 移入相應 kernel 及時變參數／block-boundary 驗收，核對 reference 本身的正確性。
- [ ] 若 consumer 需要 native／WASM export，再處理 ABI、pointer width、state sizing 與工具鏈。

<a id="c3"></a>

### C3. 分析與比較交付

- [ ] 從重複的試聽交付需求決定 consumer 放置位置及必要觀察項目。
- [ ] 將候選 ID、區段、播放位置、原始音訊與 playback-only level matching 清楚對應。
- [ ] 對分析輸出保留單位、範圍、設定與不可用原因；驗收不改正式音訊及不混淆聆聽版本。

<a id="c4"></a>

### C4. 創作手法 guidance／examples

- [ ] 選擇可選的手法說明與小範例，交代適用情境及可調的創作選擇。
- [ ] 讓普通 Python 與可選 helper 都能完成範例，不強制單一創作路徑。
- [ ] 在實際製作中評估是否改善有用的探索；把 guidance 效果與 helper 效果分開記錄。

<a id="completed-and-deferred"></a>

## D. 已完成，以及目前不列入實作的方向

**已完成的基礎：**Functional `render()`／`run`、參數綁定、fresh process、named outputs、
mono／stereo PCM24 delivery、基本驗證、錯誤結果、既有輸出保護、completion manifest、有限 receipt、
輸出 hash 儲存／驗證、五個 base dependencies，以及舊相容介面退役。
最近一次完成紀錄是 53 tests、Ruff、build 與 9 個 installed CLI checks；本次文件盤點未重跑它們。

**已完成清單：**

- [x] Functional Python `render(*, ...)` 與 `tactus.run`／`tactus run`。
- [x] 明確參數綁定、有效預設值記錄、新 process 與既有 bytecode cache 隔離。
- [x] 具名 mono／stereo 輸出、PCM24 delivery、shape／finite／full-scale 檢查。
- [x] 新輸出位置保護、可處理失敗的清理、completion manifest 與結構化錯誤。
- [x] 有限 source／lock／runtime receipt，以及輸出內容 hash 儲存與讀取驗證。
- [x] NumPy、SciPy、SoundFile、pyloudnorm、librosa 的 base dependencies 與 lock。
- [x] 實際八小節製作、參數候選、原版重跑與 plain-Python 音訊比對。
- [x] 舊 Project／Track 與僅為相容保留的 CLI／範例／測試退役。

**不作為目前工作：**

- Mandatory Project／Track／Session／Arrangement schema、另一套 source-of-truth graph。
- 自訂 authoring language、history DAG／op-log、通用 AST editor、自動音樂語意合併。
- 復活 build／inspect／render／diff 舊 commands 或相容層。
- Selective cache／checkpoint：先有正確 audition，再由實測等待與依賴失效需求啟動。
- 完整 JUCE／direct-SDK host、全面 commercial VST coverage、external sidechain native extension：具體插件需求才啟動。
- Session view、live transport、streaming、多人 editor、更廣輸出型別：本輪 scope 外。
- Mandatory Symusic／MusPy、自己的 MIDI parser、Audio LLM／transcription／separation core、PyTorch differentiable DSP。
  現有證據未支持將這些當成新版的必要能力。

另需保留**產品驗收**：Agent 是否能接手、修改真實歌曲並正確交付可聽候選；這是驗收工作，
不應另算一個 subsystem，也不能拿 WAV hash／數值通過代替音樂判斷。

<a id="evidence-index"></a>

## 全部 thought 的查核索引

以下列出本次重讀的 45 份新版 thoughts。代號對應上方責任；「邊界」表示保留限制或排除舊方向。

| 文件 | 本次判讀／去向 |
| --- | --- |
| [Plain Python＋Git beatmaking](2026-09-16-plain-python-git-beatmaking-probe.md) | A2、A4、A7；Python 足以製作，素材與環境是實際摩擦 |
| [Sampled piano renderer](2026-09-16-sampled-piano-renderer-probe.md) | B1；SFZ、連續演奏與聆聽驗收 |
| [Functional authoring](2026-09-21-functional-audio-authoring-core.md) | A1、A8；普通 Python，functional discipline 的失敗與修正證據；早期入口名稱已更新 |
| [Material identity](2026-09-21-material-identity-in-source.md) | A2；固定素材身分仍待正式介面 |
| [Production graph probe](2026-09-21-production-graph-first-probe.md) | A7、D；部分用途成立，不支持強制 graph 或已完成 caching |
| [Setloom research](2026-09-21-setloom-tooling-research.md) | A2、A7、C；source bundle、artifact verdict；不照搬其 CLI |
| [Stateful audition](2026-09-21-stateful-audition-first.md) | A5；checkpoint payoff 有條件 |
| [Plugin host capabilities](2026-09-22-plugin-host-capability-probes.md) | A2、A6；缺檔、參數與 sidechain 邊界 |
| [Python／Pattern boundary](2026-09-22-python-pattern-authoring-boundary.md) | A1、C；時間 helper 與可選 Pattern |
| [Agent-native JUCE](2026-09-23-agent-native-juce-probe.md) | A6 邊界；能寫 native 不代表需要另建 host |
| [Analysis core dependencies](2026-09-23-analysis-core-dependencies.md) | 已完成；取代 optional 建議 |
| [Analysis dependency necessity](2026-09-23-analysis-dependency-necessity-probe.md) | C；保留量測限制，套件決策已被更新 |
| [Beat／free-time boundary](2026-09-23-beat-and-free-time-boundary-probe.md) | 假 BPM 缺口已消除；A1 尚未交付 |
| [CPU analysis](2026-09-23-cpu-basic-audio-analysis-probe.md) | C；observations、不可用 LUFS 與 timing candidates |
| [Direct VST3 SDK](2026-09-23-direct-vst3-host-probe.md) | A6 邊界；特定 native 能力可行，非 backend 替換決策 |
| [Effect hosting boundary](2026-09-23-effect-hosting-boundary.md) | A6；Pedalboard 方向已收斂 |
| [Faust／Numba](2026-09-23-faust-vs-numba-dsp-probe.md) | C；自有 DSP 與 export 是後續產品化範圍 |
| [Imported MIDI preservation](2026-09-23-imported-midi-preservation-probe.md) | B1；Mido sufficiency、raw event fidelity |
| [Independent Agent MIDI](2026-09-23-independent-agent-midi-authoring-probes.md) | A1、B1 邊界；helper／Symusic 無可靠度優勢證據 |
| [Advanced librosa](2026-09-23-librosa-advanced-analysis-probe.md) | C；可用分析，依賴已拍板 |
| [MIDI boundary](2026-09-23-midi-authoring-boundary.md) | B1；Python 表達、Mido 交換 |
| [MIDI library probe](2026-09-23-midi-authoring-libraries-probe.md) | B1；候選比較已由後續決策收斂 |
| [MIDI library research](2026-09-23-midi-authoring-library-research.md) | B1；preservation 注意事項，不重開選型 |
| [Mido-native／Python events](2026-09-23-mido-native-vs-python-events-probe.md) | B1；保留表示自由與同 tick ordering 政策 |
| [Mixed clocks](2026-09-23-mixed-clocks-vs-python-probe.md) | A1；Python 能表達，不要求 clock class |
| [MusPy code reading](2026-09-23-muspy-code-reading.md) | B1；endpoint、配對與 round-trip 風險 |
| [Optional clock](2026-09-23-optional-clock-temporal-abstraction.md) | A1；時間工具可用，全曲 clock 可選 |
| [Pedalboard latency／tail／state](2026-09-23-pedalboard-latency-tail-state-probe.md) | A5、A6；需正式整合與驗收 |
| [Pedalboard automation](2026-09-23-pedalboard-segmented-automation-probe.md) | A6；分段排程的可行性與限制 |
| [Phonon-ballad MIDI maintenance](2026-09-23-phonon-ballad-midi-maintenance-probe.md) | B1；完整作品修改已測，不需再做同類選型 |
| [Python／NumPy／Mido](2026-09-23-python-numpy-vs-mido-probe.md) | B1；採現成 file I/O，避免自製通用 codec |
| [Rubber Band marker warp](2026-09-23-rubber-band-marker-warp-probe.md) | B2；binding／encoding／engine 精度差異 |
| [SoundFile boundary](2026-09-23-soundfile-audio-io-boundary.md) | 已採用；A2、A6 的 rate／layout／encoding handoff 仍需驗收 |
| [Symusic batch indexing](2026-09-23-symusic-batch-indexing-probe.md) | D；目前 corpus 節省時間不足以推動新依賴 |
| [Product succession](2026-09-23-tactus-product-succession.md) | 已完成；其 format-v1 相容敘述又被 retirement 更新 |
| [Stretch alternatives](2026-09-23-time-stretch-competitors-research.md) | B2 邊界；保留候選，不一次整合所有 engines |
| [Transactional audition](2026-09-23-transactional-audition.md) | A3；隔離 base、promotion 與衝突 |
| [Two-repo boundary](2026-09-23-two-repo-workstream-boundary.md) | 已被 succession 取代 |
| [Entry format necessity](2026-09-24-entry-output-format-necessity-probe.md) | 音樂本身不需要格式；後續選定共用 caller 並已實作 |
| [Fixed-ratio helper necessity](2026-09-24-fixed-ratio-stretch-helper-necessity-probe.md) | B2；未支持新增 core helper |
| [OpenMIRLab stretch survey](2026-09-24-openmirlab-time-stretch-candidates.md) | B2 邊界；不是新版 Tactus 必做 package |
| [Product responsibility](2026-09-24-product-responsibility.md) | 原則方向；當時 build／replay 現況已過時 |
| [Real-source warp](2026-09-24-real-source-warp-boundary-probe.md) | A2、A7、B2；headroom 與 external processor 歸因 |
| [Sampling affordance](2026-09-24-sampling-affordance-fresh-agent-probe.md) | C；guidance 與 helper 的價值分開，嚴格勝出結論未成立 |
| [Stretch listening](2026-09-24-time-stretch-algorithm-listening-probe.md) | B2；保留 Rubber Band，不宣稱 R2／R3 或通用品質排名 |

### 舊 repo 的六份轉向起點

這些檔案仍在 sibling `tactus-daw`，只作歷史證據，不繼承其舊產品介面。

| 文件 | 本次判讀／去向 |
| --- | --- |
| [Clean Agent workflow](../../../../tactus-daw/docs/blueprints/thoughts/2026-09-15-clean-agent-workflow-comparison-probe.md) | Python＋Git 能完成受測修改；特化需逐項證明，不能以 Agent 自寫 NumPy 判失敗 |
| [Python／RCP／Git](../../../../tactus-daw/docs/blueprints/thoughts/2026-09-15-python-rcp-git-probe.md) | A4；clone、revision、文字衝突；不支持再建 history store |
| [Python music runtime](../../../../tactus-daw/docs/blueprints/thoughts/2026-09-15-tactus-as-python-music-runtime.md) | A2、A3、A7；早期 facade、stable event IDs 不自動成為新版 schema |
| [Specialization substitution](../../../../tactus-daw/docs/blueprints/thoughts/2026-09-15-tactus-specialization-substitution-probe.md) | A4、A7；Git、seed locality、tails；無 universal replacement 結論 |
| [Music needs its frame](../../../../tactus-daw/docs/blueprints/thoughts/2026-09-16-music-needs-its-frame.md) | A5；audio state 不能當獨立 video frame；入口選擇已由新版收斂 |
| [Setloom local abstraction](../../../../tactus-daw/docs/blueprints/thoughts/2026-09-16-setloom-production-local-abstraction-boundary.md) | A1、A2；tempo ramp 的實際換算需求與素材搬移缺口 |

### 程式與實際使用的交叉核對

- [`run.py`](../../../src/tactus/run.py)、[`material.py`](../../../src/tactus/material.py)、
  [`cli.py`](../../../src/tactus/cli.py)、[`pyproject.toml`](../../../pyproject.toml)。
- [Functional entry 完成紀錄](../plans/2026-09-24-functional-production-entry.md)、
  [foundation](../plans/2026-09-24-implementation-foundation.md)、
  [prototype retirement](../plans/2026-09-24-retire-arrangement-prototype.md)。
- [Real-media 舊實作](../plans/2026-09-16-real-media-inputs.md) 的功能已退役；
  其 sidecar／bounded read 問題仍能用於 A2 的新介面，不搬回 Project API。
- [`real-chop-flip`](../../../examples/real-chop-flip/README.md) 與
  [`phonon-ballad`](../../../examples/phonon-ballad/README.md) 的實際 source。
- 本機 ignored `dogfood/2026-09-16-real-chop-flip/report.md` 與
  `dogfood/2026-09-24-functional-production/report.md`；後者的 final report 為同次紀錄副本。
- 本機 ignored `probes/2026-09-23-faust-vs-numba-dsp/` 的 README、harness interface 與
  `aot2/CONVENTION.md`；不是已交付的 Tactus DSP library。

## 下一份實作計畫應回答的問題

每項開工前只處理剩餘的實作決策：最小 public surface、直接採用它的作品／consumer、
與現有 `run`／素材／receipt 的銜接，以及承接哪些既有案例作 regression 驗收。
不把本表當作一次實作全部項目的授權，也不重新研究已收斂的 library 選型。
