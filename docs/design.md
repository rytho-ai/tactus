# Tactus 當前設計

本文件保存我們目前認為合適的做法，以及尚未定案的設計邊界。內容獨立、自足，直接隨新決策更新；歷史實驗不需要同步修改。這些選擇包括待實作的方向，不代表現有 runtime 已經全部支援。

視覺樣式、design tokens、品牌資產與互動展示統一維護於 [design/](../design/README.md)。

## 創作介面：Functional Python 與少量執行邊界

Production 以普通 Python modules、functions、NumPy arrays 與資料結構組成。函式清楚表達輸入、輸出與處理順序，盡量避免共享 mutation，使音樂片段、訊號處理與混音容易重用和修改。Agent 可以直接呼叫既有套件，也可以撰寫作品自己的 DSP。

我們目前採用的分解方式是：選擇素材身分、產生或處理音訊、組合完成的訊號、交付作品宣告的 outputs。這讓 runtime 能在必要處提供可靠執行，又不接管 Agent 的分組、角色、routing 與音樂算法。

第一版執行介面採用 Python 檔案中的同步 `render(*, ...)` 函式。具名 keyword-only 參數及其預設值供候選試聽使用；回傳 `{"sample_rate": 整數, "outputs": {名稱: NumPy陣列}}`，可加上
`"takes": {名稱: NumPy陣列}` 保存這次生成的中間音訊。Tactus 負責呼叫、音訊驗證與寫檔。這個約定讓同一個工具能執行不同作品，作品內部的結構仍由 Agent 決定。

Outputs 共用一個 sample rate，可有不同長度；可以是 mix、stems 或 clips，沒有必要的 output 名稱。交付格式先採用非空 mono／stereo、有限的實數音訊，經 float32 轉成 PCM24 WAV；不自動混音、正規化或重採樣。這是輸出邊界的約定，並不限制中間 DSP 的 headroom。超過 ±1 全幅不會被拒絕：寫檔前裁切到全幅，manifest 與 run 結果回報每個 output 的 `peak_dbfs`（裁切前的峰值）與 `clipped_samples`，由 Agent 自行判斷要不要調整 gain。

舊版 `build(project)`、`Project`／`Track`、arrangement 格式及其 CLI 已退役，不保留相容層。新版以 `render()` 和 `run` 為執行介面；結果可直接從回傳值、manifest 與 receipt 讀取，沒有另設 `inspect` 的需求。

**尚未定案：**targeted rendering 與更廣的交付型別。`select`、`render_audio`、`mix`、`render_all` 是實驗使用過的語彙，不是 public API。

**執行層的共同契約（2026-09-30）：**`run.py` 協調 process、render 與交付；
`_contracts.py` 集中錯誤格式、有限 JSON、atomic JSON 寫入與輸出音訊驗證；
`_source.py` 集中 source／lock inventory、環境與套件來源。儲存、分析、export 與 init
直接使用共同契約，避免反向依賴 runner。既有公開 API、receipt 與 checkpoint 格式保留。

**已完成音訊的讀取：**`render_store` 統一擁有 published PCM 與 original arrays 的讀取與驗證，
以具名結果交給 caller；analysis 不再自行解析 manifest，excerpt 專注選取與裁切。
Analysis／excerpt 仍使用已發布 WAV，export 優先使用原始 arrays。來源 inventory 與
analysis／export attribution 的內部欄位由 TypedDict 定義；對外 JSON 格式保留。
Excerpt 失敗時只清理本次呼叫成功建立的目錄，避免刪掉競爭程序的結果。

## 時間表達：Temporal abstraction 有價值，但 clock 可選

我們目前認為 temporal abstraction 有價值：將 placement、repetition、時間變換與 automation 展開中反覆需要算對的運算集中處理，讓 production source 更直接表達音樂關係。這些工具可以是作品內的 Python 函式，也可以在重複需求成立後成為可選的共用 helper。

時間工具不要求全曲 BPM。作品可以混用絕對時間、全曲 tempo map 與局部 clock，最後一致地解析到 output samples。需要保留的關係如下：

| 作者表達的關係 | 變更時間設定時的行為 |
| --- | --- |
| 事件跟隨全曲 beat position | 全曲 tempo 改變時，事件的絕對時間跟著改變。 |
| 事件跟隨獨立的局部 BPM | 該局部 BPM 只影響跟隨它的事件。 |
| 局部段落錨定在全曲某一拍 | 全曲 tempo 改變時，段落起點跟隨 anchor；段內時間仍依自己的 clock。 |
| 局部段落錨定在絕對秒數 | 全曲 tempo 改變時，段落起點保持固定。 |
| 事件直接使用絕對時間 | 不隨全曲或局部 BPM 改變。 |

作者仍決定 automation 的數值、邊界、插值方式與用途；helper 只負責正確展開。`repeat`、`scale_time`、`section_envelope` 等名稱目前用來描述候選能力。

三輪 probe 比較了「不用 helper」「v2 設計」「v3 設計」三種寫法在共同音樂變換任務下的正確率：v3 零錯誤，另外兩者各錯 7 處（同樣的 token 量級），錯誤集中在 0/1-based beat 誤算與 tempo 曲線的近似寫法。基於這個證據，`tactus.timing`（來自 v3）已交付為選用模組：`Clock`（tempo/meter → seconds/frames，含 step／ramp／ramp-time／smooth 四種 tempo 變化）、`swing`、`Groove`、`envelope_beats`／`envelope_seconds`，以及唯一的 rounding 規則 `frame_of`。它是 `import tactus.timing` 才會用到的選用能力：`render`／`run` 不要求它，作品仍可保留自己的時間算法，或與它混用；beats 一律是 0-based quarter note（音樂人數的「第 2 拍」是 `beat=1.0`）。

機械性 helper 的兩組對照 probe（擺放 clip、marker、quantize、音符值換秒、RMS 貼齊）顯示：有 helper 的 Agent 少寫約三分之一程式碼、少用 21% token，錯誤沒有增加。已交付：`timing.add_at`（就地疊加，頭尾超出就切掉、不會繞回；取代會整份複製 buffer 的 `place`）、`timing.markers`、`timing.quantize`、`timing.note_seconds`、`fx.fit_rms`（平滑的 look-ahead 增益，貼齊目標 RMS 且不超過 ceiling，不像 `pedalboard.Limiter` 會削出平頂）與 `tactus.load_audio`（讀檔、聲道轉換、精確 resample、可選的起音前靜音裁切）。`db_to_gain`／`gain_to_db` 在 probe 中沒有 Agent 使用，未交付。

**尚未定案：**seconds／samples placement 與總長度的正式介面，以及哪些 tempo-map／local-clock 計算值得由 Tactus 共用超出 `tactus.timing` 現有範圍。漸變 tempo、rubato、巢狀 clock 與跨 tempo 變化的事件長度仍需驗證；MIDI 檔案讀入 tempo、groove 從音訊萃取，以及「全曲需要一個 clock」的要求，明確不在範圍內。

**時間位置的取整（2026-09-30）：**musical placement 與 excerpt 的秒數邊界共用
`timing.frame_of`，以 `floor(seconds * sample_rate + 0.5)` 取整；恰好半個 sample
時選較晚的 frame，excerpt 終點不包含在輸出內。這會改變舊版 excerpt 在部分半 sample
邊界的結果，既有已保存的 excerpt 不變。Analysis 視窗與 DSP 時長參數保留各自已記錄的
離散化方式，不因這次位置契約整理而改變演算法結果。

## Pattern：選用的局部規律工具

Pattern functions 用於可命名、組合與重用的規律，例如 cycle、phase、Euclidean distribution、polymeter、rotation、reverse 與週期性 transformation。一次性的 fill、section 選擇與音樂例外留在 Python；例外本身形成作品要保留的週期時，才值得用 Pattern 表達。

目前方向是將局部 Pattern 展開成普通事件，再與手寫 Python 或其他 generator 產生的事件使用同樣的時間與 placement 能力。下游不必因事件來源不同而採用不同編排模型。這能保留規律的意義，並減少作品反覆手寫 cycle／phase 計算。

2026-09-27 的兩組對照 probe（多聲部、層層疊加的週期規則、兩輪修改）顯示 Pattern 模組沒有減少錯誤、token 或修改量，只讓原始碼變短，因此目前不提供 Pattern 模組；這些規律以原生 Python 加 `tactus.timing` 表達。同日第二次 probe 改用 Agent 熟悉的寫法（NumPy 格子、Tidal/Strudel 風格的 mini-notation，均為自製、不用套件），也只看到「慣例」的價值：Agent 各自重寫 Bjorklund，其中一個把 Tidal 的旋轉方向做反。因此只交付 `timing.euclid`（照 Tidal 的左旋）與 `timing.cycle`（跨小節連續循環），兩者回傳 step 編號，不引入 pattern 型別。以下是重新開啟時要決定的事。

**尚未定案：**事件資料型別、Pattern 的正式函式集合與共用範圍。`realize(...) -> tuple[Event, ...]` 是已測過的候選邊界；它不要求整首作品使用 Event schema。Lazy／infinite Pattern、probability、seed 與 incremental realization 尚未收斂，也沒有採用 string mini-notation 的需求。

## 素材：版本化身分與內容儲存分開

作品保存固定的素材身分，runtime 依身分取得內容。素材 bytes 可以放在 Git 外的 content-addressed store；更換內容必須改變作品中被版本化的參照。素材遺失應回報無法取得，不能悄悄換成同一路徑下的新檔案。

匯入時可以從一般檔案路徑開始，但持久的創作依據應固定到內容。只在 build 時對可變路徑算 hash 並寫入 generated receipt，仍無法防止同一個 source revision 讀到不同素材。

目前做法：作品在 Python 中以具名常數寫入 inline digest，並用 `material("sha256:…")` 取得驗證過的檔案路徑。`tactus material add FILE...` 把檔案匯入本機 pool（`$TACTUS_POOL`，預設 `~/.local/share/tactus/pool`），並印出對應的 ref。身分是原始檔 bytes 的 SHA-256。解碼、擷取區段、sample rate 與 headroom 由作品自行處理。缺檔與內容損壞分別回報。Pool 的目錄結構與 tactus-daw 相容。外部執行檔與 native library 由作品在使用處以 `tool(...)` 宣告，receipt 記錄其路徑與 hash；目前只記錄，不以 hash 鎖定。

資料夾（SFZ 樂器、VST3 bundle）以 `tree:sha256:` ref 固定。digest 是「排序後的相對路徑加上每個檔案 hash」這份清單的 hash；版本控制目錄（`.git` 等）不列入。`material()` 會在 pool 內以 hardlink 還原整個資料夾並逐檔驗證，所以相對路徑可以直接使用。`tool(資料夾)` 對整個 bundle 計算身分，並回傳資料夾路徑，可直接交給 `pedalboard.load_plugin`。

**尚未定案：**解碼後音訊的身分、import gain／headroom 政策，以及 processor 身分不符時是否拒絕執行。

## 執行與重現：先可靠產出，再按需要重用計算

Python 執行後產生可保存的音訊材料與宣告 outputs；編排快照、receipt 與其他執行資料都是衍生物。Receipt 用來辨識這次執行的 source、素材、參數、dependencies 與 runtime／processor 身分，讓結果能追溯到輸入。

第一版已提供 `tactus.run(source, out=..., params=...)` 與 `tactus run SOURCE --out NEW_DIRECTORY --params JSON`。每次呼叫使用新的 Python process，避開既有 bytecode cache，從 entry 所在資料夾解析 sibling imports 與相對素材路徑。作品的 log 走 stderr，CLI stdout 只交付一份 JSON 結果。已存在的輸出位置會被拒絕。`run` 先把原始 arrays、receipt 與 take refs 保存為 `render/` 和 `render.json`，再寫預設試聽 WAV；checkpoint 完成前的失敗會清除該次目錄，完成後的交付失敗則保留原始結果，只清除不完整的 WAV。

Functional run 的 `manifest.json` 保存 sample rate 與具名音訊的內容 hash、frames、channels；WAV 由 OutputStore 直接寫在 `--out` 底下，檔名為 `<name>-<sha256 前 8 碼>.wav`，manifest 記錄完整 sha256。Manifest 最後發布，作為完成標記。`receipt.json`（format_version 4）保存以下內容：
- 實際參數（含預設值）
- entry 目錄下 Python source 的 hash
- 從 entry 目錄往上找到的最近一個 `uv.lock` 的路徑與 hash（`dependency_lock`）
- 解析過的素材 refs
- 宣告的 tools
- 實際 import 的第三方套件版本
- Python／Tactus／NumPy／SoundFile 版本
- `environment`：實際執行的 interpreter，`{prefix, lock}`——`prefix` 是 `sys.prefix`，`lock` 是該
  environment 所屬 project（`.venv` prefix 的上一層目錄）裡 `uv.lock` 的 `{path, sha256}`，沒有則為
  null。舊作品借用 Tactus checkout 的環境執行時，`dependency_lock` 可能為 null，
  `environment.lock` 則指向 Tactus 的 lock；新作品使用自己的 locked environment。
- `package_sources`：`python_packages` 裡每個非 index 安裝的套件，依其安裝 metadata（PEP 610
  `direct_url.json`）記錄來源——VCS 安裝為 `{url, vcs, commit}`；目錄安裝（例如 editable 的 Tactus
  本身）為 `{url, editable}`，若該目錄同時是 Git checkout 再加上 `git: {commit, dirty}`（沿用
  `revision.py` 讀 Git 的方式）；封存安裝為 `{url, hash}`。Index 安裝（版本已被 lock 釘住）省略。
- `stages`：每次 `@stage` 呼叫一筆，依呼叫順序記錄 `{name, key, reused, seconds, reason}`
- `reuse`：這次執行是否要求 `--reuse`

執行中觀察到 source 或該 lock 改變時會失敗。未以 `material()` 取得的檔案、未宣告的執行檔、網路存取與隨機性仍不在紀錄範圍內。Runtime 不隔離任意 Python 的外部副作用。

**每個作品都是自己的 uv project（`tactus init`）：** 在此之前，作品借用 Tactus 自己的環境
（`uv run --project <tactus>`）執行——作品不能自行加套件，receipt 的 `dependency_lock` 恆為
null，且環境會隨 Tactus checkout 移動而改變。`tactus init DIR` 建立一個新資料夾（必須不存在或
是空的），內含 `pyproject.toml`（`name` 取自資料夾名稱、`requires-python` 複製自*正在執行*的
Tactus 自己的 metadata、`dependencies = ["tactus"]`、`[tool.uv.sources]` 釘住一個 Tactus 來源）與
`.gitignore`（`runs/`、`.venv/`、`__pycache__/`），然後執行 `uv lock`。它不寫 `song.py`；作品的
內容仍是 Agent 的。來源預設是正在執行的 Tactus 自己的來源，讀自它自己的 PEP 610
`direct_url.json`（與 `package_sources` 共用同一份解析邏輯）：Git 安裝就用同一個 URL 與
commit；editable checkout 則用該 checkout 的 `origin` remote URL 與 `HEAD`，但只在該 checkout
乾淨且 `HEAD` 已經在 remote 上時才允許，否則 `init` 會失敗並提示先 push 或改用
`--tactus-path`。`--tactus-path PATH` 明確釘住一個 editable 本地路徑；`--tactus URL@REV` 明確釘
住一個來源。全域以 uv 安裝 CLI 一次，之後在作品內直接以 `tactus run song.py --out DIR` 執行，receipt 的
`dependency_lock` 就是作品自己的 `uv.lock`（同時鎖住 Tactus 與其他每個套件）；`uv add PACKAGE`
只替該作品加套件。沒有 `pyproject.toml` 的舊作品維持原本的執行方式，不會被拒絕。

**全域 CLI 與作品環境：** console launcher 尋找目前或父目錄最近的 `pyproject.toml`，
在作品內使用 `uv run --project DIR --locked -- python -m tactus.cli`，讓作品自己的 Tactus
版本與 dependencies 生效；缺少或過期的 lock 會失敗，不退回全域版本。`init` 使用全域安裝；
作品外使用全域環境。`tactus --project DIR ...` 可明確選擇作品，路徑參數仍相對於呼叫位置。

**獨立 export：** `tactus export wav|flac|stems RUN --out NEW_DIR` 讀取已驗證的原始 checkpoint，
不呼叫 render，可在試聽交付失敗後重試，也能交付 FLOAT／DOUBLE WAV 保留 headroom。
`run` 維持一次命令完成生成與預設 PCM24 試聽；另存原始 arrays 會增加磁碟用量。
舊 run 沒有 checkpoint 時使用已保存的 PCM，明確記為 `published-pcm`，不能恢復先前丟失的精度。
每次 export 有自己的目錄與 `export.json`；失敗只清除該次新目錄。`take export` 則持續負責
單一演奏素材包的轉移。完整介面見 [export 契約](../skills/references/project-commands.md#export-a-completed-render)，
回歸驗證見 [export 測試](../tests/test_export.py)。

**Opt-in 的 stage reuse（`--reuse`）：** `from tactus import stage`，`@stage` 標記 module-level 函式。不帶 `--reuse` 時是單純呼叫，沒有額外開銷。帶 `--reuse` 時，一次呼叫只在下列全部相符才視為命中：stage 的 qualified name 與 source file、`source_files`、`dependency_lock`（或無 lock 時已安裝套件的名稱與版本）、Python／Tactus 版本，以及呼叫參數的 canonical hash（僅支援 NumPy array、`None`、bool/int/float/str/bytes、`Path`，以及它們的 list/tuple/dict；其他型別的參數或回傳值都視為不可重用／不可儲存，receipt 說明原因）。命中時重播該次呼叫記錄的 materials／tools（tool 會重新雜湊比對，因為它的路徑可能換了東西；material 不會，因為它是 content-addressed）。結果只存 NumPy array 與上述純值，存在 `$TACTUS_POOL/stages/<key>/`，v1 沒有 garbage collection。巢狀 stage 呼叫在外層命中時整段被跳過。

Stage cache 現在以格式版本與 SHA-256 驗證 metadata／array bytes。尚無 entry 才視為一般 miss；
既有 entry 損壞回報 `cache_corrupt`，無法驗證的舊格式回報 `cache_incompatible`，不自動重跑該
演奏。恢復時明確選擇還原 cache 或重新生成，操作與聲音差異見
[stage reuse](../skills/references/runtime.md#reusing-unchanged-stages)。

Agent 的指引由 [`tactus` plugin](../skills/README.md) 提供。`compose` 負責用 functional、modular Python 撰寫、執行與修訂作品，並以 progressive disclosure 組織和閱讀 code：先看整體 form／signal flow，再進入相關模組契約與演算法。模組採 deep module 原則：小而清楚的 interface 承載完整能力，隱藏演算法與協調細節，同時保留 caller 要控制的音樂選擇；不能只增加轉接層。套件清單與整合注意事項在共用 reference 按需查閱。`dsp` 負責使用、撰寫與驗證 processor；`measure` 同時涵蓋使用與撰寫分析、驗證定義，以及註冊作品自己的 analyze 指令。Compose 在需要時連到另外兩個 skills，把量測、time-stretch 與效果組合成作品自己的做法；不要求每首作品都走過同一流程。

單一產品的 plugin manifest 放在 repo 根目錄的 `.claude-plugin/` 與 `.codex-plugin/`，
`version` 指導 Agent 使用版本探索、比較、保留與重用創作方向，並負責 Git 操作紀律：確認作品實際被追蹤、初始 commit、候選採用與舊版本恢復。Compose 在開始作品與接受修訂時使用它。`init` 要求 Git 可用並建立作品自己的 repository，即使作品位於外層 checkout；缺失或失敗會明確報錯。Commit 由 Agent 在 source 準備好後直接操作 Git；renderer 維持唯讀記錄，`doctor` 不檢查 Git。Git binary 與 ancestor HEAD 都不足以證明作品已保存；生成音訊在 Git 外保存，receipt 保留當次執行的原始身分（2026-09-30）。

素材切片與分軌交付以 [production reference](../skills/references/production.md) 保存可改寫的 authoring pattern：loop body／尾音分開，source 與 output 的格點各自明確；post-channel、pre-master 與最終 master 的關係由作品 source 宣告。這不新增通用 sample/track API。Render 回傳格式維持原契約；不合法的 dictionary 會指出 missing／unexpected fields，並提供正確形狀的範例。

兩個 marketplace 都指向根目錄。四個 skills 放在 `skills/`，共用契約由
`skills/references/` 維護，小型合成音源範例放在 `skills/examples/`；整個 skills 目錄的
相對引用可獨立使用，runtime 另行安裝。測試持續比對真實 manifest、receipt 與錯誤欄位。
內建 DSP、Pedalboard 與作品自寫函式都可自由使用；自寫分析不必先進 Tactus core。
程式結構的紀律服務可理解、可修訂的音樂，而不替 Agent 指定音樂形式。

已保存的 WAV 可以直接播放，也可透過 OutputStore 檢查內容 hash 與音訊 metadata。Source rebuild 則重新執行 Python，還受到 randomness、外部輸入、套件與 processor state 影響。保存結果與重新製作的保證要分開表達。

選擇性重用（`@stage`／`--reuse`，見上）已交付。它的價值主要是讓比較公平，而不是速度：OB-Xf 這類每次 render 都不同的外掛會讓候選之間混進隨機差異；有 reuse 時 3/3 的 fresh Agent 交出「只有 bass 變」的候選，沒有時 0/3（見 thoughts `2026-09-26-stage-reuse-probe.md`）。實際 session 等 render 的時間只占 1～10%，所以速度本身還不構成需求；checkpoint、region-only 計算與跨機器共用 cache 仍等實際 consumer 證明需求後再加入。Graph 可以支援執行與檢查，但目前沒有把它擴張成全曲創作模型的計畫。

**乾淨環境交接的已驗證邊界：**2026-09-28 的完整作品實驗，直接重跑 OB-Xf／SFZ
未通過重現門檻。把主機基準的 pads、bass pre-gain arrays 固定成素材後，全新 pool／Python
環境在斷網容器內重建的六個 WAV 全部相同；單改 bass gain 時其他四軌不變。
因此需要保留的演奏可以成為作品明確引用的 material，生成 source 與 receipt 一併保存；
它不應只存在 cache，也不能宣稱這證明 generator 本身可重現。這是同主機 Linux 的驗收，
尚未形成通用交接 CLI；原始交接實驗保留在本機 experiments 工作區。

**保存 take 是正式重現方式（2026-09-29）：** Paul 決定使用原版樂器。原生修補實驗保留為
原因調查與可行性證據，不作為安裝或重現的前提。作品要保留某次演奏時，在同一次 `render`
回傳 `takes` mapping，讓試聽成品與被保存的中間音訊來自同一個演奏。

候選先保存在 run 的 `takes/NAME/`；`audio.npy` 保留原始 numeric dtype、shape 與 headroom，
不裁切、不重採樣、不轉 PCM24。`take.json` 記錄 sample rate 與檔案身分，並附上生成 receipt、
執行前的 Python source／nearest lock snapshot，以及既有的 source patch。含 takes 的 run 使用
manifest version 3，增加 `{name: tree_ref}` 的 `takes`；其他 run 維持 version 2。

`tactus take save RUN NAME` 驗證候選並存入 material pool。採用由 source 裡的 ref 決定：
`load_take(REF, sample_rate=...)` 讀回原始陣列，後續音量、效果、placement 仍是普通 Python。
它記錄這個 material，不執行 generator，也不要求安裝 provenance 裡的 tools。Sample rate
不符或素材遺失／損壞會失敗。更改 MIDI 或 patch 時，另開生成 run，選擇後才換 ref；舊 ref
可退回，source 不會自動偵測或重新生成 pinned take。

`tactus take export REF --out DIR` 匯出音訊與 provenance；另一台電腦以 `tactus material add DIR`
匯入，得到相同 ref。這個 bundle 足以讀回演奏；重新生成所需的 sample libraries、binaries 與
Python 環境仍需另外準備。Pool 是本機持久素材庫，需備份；stage cache 可刪，不能充當採用
演奏的唯一保存處。完整契約見 [Saved takes](../skills/references/runtime.md#saved-takes)，
回歸驗證見 [saved takes 測試](../tests/test_takes.py)。

**尚未定案：**source rebuild 的完整依賴與隨機性契約、超出第一版 receipt 的歸因範圍。不能從素材 hash 相同推定所有重新執行都可重現。

## 套件與工具邊界：自有算法與專門引擎

Base environment 選用 NumPy、SciPy、SoundFile，讓 production code 可以直接使用。Librosa 以 `tactus[librosa]` optional extra 提供，預設安裝不包含它；內建分析也不呼叫它。需要的作品以 `uv add "tactus[librosa]"` 選裝，開發比對用 `uv run --extra librosa pytest -m reference`；dev 額外安裝 pytest／Ruff。Global CLI 與作品環境分開，extra 不自動帶入新作品。Pyloudnorm 已從所有 dependency groups 移除，loudness 改以保存的獨立參考答案、數學測試與 EBU 素材驗證。Pedalboard、pytimestretch、pyqmdsp 與 Mido 也是 base dependency。Python 限制在 3.12（`requires-python = ">=3.12,<3.13"`）：Pedalboard 0.9.24 與 0.9.25 的 cp313 Linux wheel 內含未經 CPU 檢查的 AVX-512 指令（在模組初始化時執行 `vinserti64x2`），在不支援 AVX-512 的 CPU（例如 i5-13600K）上會以 illegal instruction 崩潰；0.9.23 的 cp313 與 0.9.25 的 cp312 都正常，3.12 的全新環境也完整通過。上游已在 2026-09-23 合併修正（spotify/pedalboard PR #511），但尚未發佈新版；等包含該修正的版本發佈並在這台機器驗證後再放寬。這是可用性上的產品選擇，不宣稱每個套件在數學上都不可取代。套件選定也不代表正式 runtime 已完成整合。

| 工作 | 目前做法 | 理由與邊界 |
| --- | --- | --- |
| Arrays 與 DSP | NumPy、SciPy | 支援普通 Python 的數值與訊號處理，保留 Agent 自寫算法的空間。 |
| 自有 stateful DSP | Python／Numba | Duck envelope、小數 delay 與逐 frame SVF 的迴圈使用 cached Numba kernel；驗證與 NumPy／SciPy 外層保留。Faust 可作為演算法參考，不要求另一套創作語言。 |
| Audio file I/O | SoundFile | 採用既有編解碼能力；Tactus 處理必要的資料與工具銜接。 |
| Loudness 與音訊分析 | 自有 NumPy／SciPy 算法 | 維護既有數值定義、API 與比對測試；librosa 以 optional extra 選裝，亦可用於比對；pyloudnorm 的參考答案已固定為一般測試，不再需要安裝套件。 |
| 拍點與速度估計 | `pyqmdsp`（base dependency，固定 Git revision `09b36d6`）+ `tactus.analysis.rhythm.beats` | 直接使用 qm-dsp，不依賴 Vamp。Tactus 只轉換 JSON 格式，沿用原型的空結果 `bpm: null`；聲道平均、分幀、參數與時間換算都由套件負責。只提供 beats，不提供 downbeats。 |
| 效果與 VST3 | Pedalboard（base dependency）+ `tactus.fx` | `set_param` 依單位對到最近的合法值，`process_automated` 以分段處理 automation、tail 與延遲，`render_instrument` 以暖機消除起始雜訊並回傳 Tactus layout。曲線與音色由作品決定。盲聽中內建 reverb 勝過自寫。External sidechain 是已知缺口，不宣稱普遍 plugin 相容；部分 VST（如 OB-Xf）不可逐 sample 重現。 |
| Standard MIDI File 交換 | Mido（base dependency） | 例如 `sfizz_render` 需要 `.mid` 檔；三次完整歌曲 dogfood 的 Agent 都因為沒有 MIDI 套件而各自手寫 SMF writer，因此改為預設安裝。Notes、controllers 與 transformations 仍由 Python 決定；Mido 不成為 composition model。 |
| Time stretch／pitch shift | `pytimestretch`（base dependency，固定 git revision `e43cc6d`，GPL-2.0-only） | 直接接受與回傳 NumPy，提供 Rubber Band 4.0（R3）與 Signalsmith 兩個 backend，由作品明確選擇；不自動限幅，headroom 由作品負責。取代 `pyrubberband` 加系統 `rubberband` 的做法，因此不再需要外部執行檔。整首長短與節拍、音高控制測試通過，Paul 試聽未發現問題。不另加 `tactus.stretch` 包裝。`extreme_stretch`（PaulStretch）是可選的創作處理：長度只是近似值，每個 process 內依呼叫順序固定亂數。這個 revision 因為 libpaulstretch 而改成 GPL-2.0-only，和 Pedalboard 的 GPLv3 不能一起對外發佈；目前只在內部使用，公開發佈前必須解決（見 plan 的 Future）。 |

**VST 固定延遲與連續處理（2026-09-29）：** `fx.process_automated` 先以靜音讓外掛
穩定回報延遲，再明確重設一次；正式區塊全部以 `reset=False` 連續處理，最後補出
緩衝中的音訊。起始延遲由 Pedalboard 補償，不再手動位移。未修改的 LSP 1.2.35
Limiter 已驗證 mono／stereo、44.1／48 kHz、兩個外掛串接與短區塊，透明設定下
輸出逐 sample 相同。Automation 若改變外掛回報的延遲會明確報錯；未回報的延遲
與其他外掛仍需個別驗證。串流與邊界的回歸驗證見 [延遲測試](../tests/test_fx_latency.py)；
真實外掛的原始量測保留在本機 experiments 工作區。

**Marker warp 的實際製作驗證與採用（2026-09-29）：** 已安裝的 `pytimestretch.time_warp` 接受
`(source_frame, output_frame)` 整數 pairs，包含 `(0, 0)` 與來源／輸出長度的終點。
作品先在 `render` 外取得拍點，把採用的 map 固定成素材，再由一次連續的引擎呼叫完成伸縮。
Brahms 真人弦樂片段的試作中，實際音訊對應的平均格線偏差由固定伸縮的 600.49 ms 降到
逐拍對齊的 7.79 ms；兩版鼓完全相同、沒有輸出削頂。Paul 已同意直接採用既有的
`runs/final/warp` 候選與凍結拍點，這份作品的驗收完成。數字表示選定來源位置的
對齊改善，不代表拍點正確率或通用音質結論。目前普通作品函式已足夠，尚無新增 Tactus wrapper 的證據。
詳見 [製作範例與驗證](../examples/beat-alignment/README.md)。

**內建 DSP（2026-09-29）：** `tactus.dsp` 提供普通函式 `gain`、`fade`、`pan`、
`biquad`，並實作 `varispeed`／`fit_rms`；`fx` 的同名入口延遲載入並轉向同一函式。前四項使用 NumPy／SciPy、保留
headroom，回傳新 float64 陣列，不修改輸入。Gain/pan 支援 scalar 或逐 frame 控制；
fade 是整段素材的線性淡入淡出；pan 只把 mono 轉為等功率 stereo。
Biquad 支援 lowpass、highpass、peak、low_shelf、high_shelf，回傳 `(audio, state)`；
state 是 `(2, channels)` 的 direct-form-II-transposed 記憶值，由作品明確接續。
`None` 從零開始；空 block 保留 state；尾音由作品明確送入零訊號取得。
固定參數下分塊與整段結果相同；參數切換沒有自動平滑，不保證無雜音。
這些函式直接在 `render` 使用，VST host 與自訂 Python 路徑維持獨立可用。

另提供四個每次呼叫從零開始、處理完整素材的效果：`duck` 用外部 detector 的跨 channel
最大峰值產生共同 gain，能回傳曲線供其他聲部重用；`delay` 支援逐 frame 小數延遲，
只回傳 wet，尾音長度由呼叫端指定；`lowpass` 支援逐 frame cutoff；`saturate` 用
tanh 與預設 8 倍 oversampling，支援逐 frame drive／dry-wet。這四項不提供跨呼叫
state，不承諾分塊等價；delay 時間變動會改變音高，控制曲線不會自動平滑。
完整參數契約由 [DSP reference](../skills/references/dsp.md) 維護。
整合理由是減少跨作品重寫與重測；先前 fresh-agent 實驗觀察到 delay 插值與 wet-only 錯誤，
但沒有量測節省的時間或 token。這些邊界已納入 [DSP 回歸測試](../tests/test_dsp_effects.py)。

這三個逐 sample 迴圈已抽成 private Numba kernel，使用 `cache=True`、不開 fastmath。
Numba 因實測加速而成為 runtime dependency；analysis 的 librosa 仍是
選用參考，pyloudnorm 已移除。公開 API 與 whole-clip 行為相同；首次使用需要編譯，新 process 可載入
磁碟快取，不能把穩態處理時間當作完整 CLI 啟動時間。固定 cutoff 與 saturation
維持 NumPy／SciPy 路徑。數值一致性驗證見 [Numba DSP 測試](../tests/test_dsp_numba.py)。

**頻譜分析加速（2026-09-29）：** CQT／VQT 達十億次估計 filter tap 運算、且
packed filters 不超過 64 MiB 時，採用 private cached Numba kernel，最多八個執行緒；
短輸入維持 SciPy FIR，不載入 compiler。STFT 分批運算以限制暫存記憶體；
STFT／Mel 保留原生 FFT，較大矩陣使用四個
worker；Mel 保留 sparse projection。Numba 不開 fastmath，不更動分析的定義、時間格點
或單位，呼叫結束恢復執行緒設定。首次編譯與快取載入分開記錄，不能以 warm timing
推論每次 CLI 都同樣快。數值一致性與選路的回歸驗證見
[加速測試](../tests/test_analysis_acceleration.py)。

**分頻與 delay 切換（2026-09-29）：** Paul 試聽接受後，整合 `crossover` 與
`crossfade_delay`。前者以 SciPy 提供固定 cutoff 的雙路 LR4，回傳 low／high；
相加幅頻平坦但相位改變。後者以 Numba 實作兩個固定小數讀取位置的線性
crossfade，回傳 wet-only，保留 feedback 與指定尾音；過渡途中不追逐每個控制值，
完成後採用最新要求。既有 `delay` 維持會改變音高的移動讀取位置行為。
兩者每次呼叫重設，不提供 streaming state。Crossfade 可能干涉或抵消；新增介面
明定起始位置與過渡端點，不宣稱與 Faust `sdelay` 逐 sample 相同。見
[可執行範例](../examples/dsp-components/README.md) 與
[響應與切換測試](../tests/test_dsp_components.py)。

Audio handoff 要明確處理 sample rate、channel layout、dtype 與 output encoding。改寫檔案的 sample-rate 標籤不等於 resampling；工具間的 layout 轉換也必須保留 channel 身分。SoundFile 使用的 `(samples, channels)` layout 不自動決定所有工具或 Tactus 未來的內部表示。

自有 DSP 的有限實驗支持 Python／Numba 實作與 native／WASM 輸出的可行性，但尚未形成產品的通用 export pipeline。驗證移植算法時要涵蓋時變參數、state 與 block boundaries；參考輸出本身也可能有錯，不能只因符合單一 golden 就宣稱正確。

**尚未定案：**是否有跨作品共用 marker-map authoring helper 的必要；外掛的動態／未回報延遲、external sidechain 與更廣泛的 plugin 相容性；自有 DSP 的可攜 state／buffer 約定與 native export 工具鏈。Rubber Band baseline 不代表所有素材與比例下的品質排名已定案。只有真實需求暴露缺口時，才重新比較 Symusic／MusPy、Signalsmith 或自製 host；DawDreamer 保留為參考。

## 試聽：Offline、stateful、候選隔離

先提供 offline 的「產生候選 → 聆聽或量測 → 比較 → 接受」循環。Stateful 表示處理具有記憶的效果器時保留正確上下文；候選隔離表示試聽不改正式 source，也不繼承其他候選的參數或 DSP state。這兩件事都比單純加快 render 更直接影響比較是否可信。

第一個試聽介面以明確宣告的參數為範圍。多個候選從同一份 immutable base 執行，receipt 辨識 base source、素材、候選參數、range／stems 與 runtime／plugin 身分。Range audition 需要正確的 pre-roll、latency 對齊與 tail 處理，不能只把輸出區間前的處理全部省略。

目前 `run` 支援完整執行的參數候選，各次 process 與輸出目錄分開，Tactus 不修改 source。每次執行的 receipt 會記錄：
- Git `HEAD` 與未提交狀態；
- 可還原實際 source 的 `source.patch`；
- `render` 的執行時間。

接受候選由作者或 Agent 自己完成：把參數值寫回 `render` 預設值、重跑，再用 Git commit。在那之前，先比對候選 receipt 的 `git.commit` 與 `source_files` 是否仍是目前的 source。若 source 已經移動，聽者選中的版本已不存在，必須告知聽者，並在目前的 source 上重跑、取得重新確認。

區段試聽：`tactus excerpt RUN_DIR --range START:END [--outputs a,b] --out NEW_DIR` 以秒指定區段，先驗證既有 run 的輸出，再從中剪下該段，不重新 render。因此即使作品用到每次 render 都不同的插件（例如 OB-Xf），片段仍與聽者手上的那次候選 sample 完全一致；邊界硬切，不加 fade、pre-roll 或 tail。excerpt 的 manifest 記錄 range、每個輸出的原始長度，以及來源 run 與其 manifest hash，不另外產生 receipt。先前的 `run --range` 會重新 render 再剪；完整歌曲 dogfood 2 顯示，這種做法下 OB-Xf 作品的預覽與候選相關係數只有 0.42，因此已由 excerpt 取代。作品自行把 `render` 切成視窗的做法會因處理狀態、loop 相位與整體 mix 處理而與成品不同，完整歌曲 dogfood 已實際觀察到這個問題。只計算部分區段的加速版本延後，要等實測等待時間證明有需要，並能證明輸出一致後再做。

Git 與音檔的分工如下：
- **Git 只保存 source**：`.py`、`uv.lock` 與 `sha256:` refs。
- **Render 的音檔不進 Git**：它們體積大、無法 diff 或 merge，而且屬於衍生物。
- **Run 輸出放在固定位置**：主 checkout 的 ignored `runs/`，或 repository 外。不要放在會被移除的 worktree 內。
- **聽者認可或聽過的版本要封存**：用 `tactus material add` 存入 pool。pool 與 manifest 使用同一個 SHA-256，commit 訊息引用的 hash 因此可以用 `material()` 取回。
- **Runtime 只唯讀地記錄 Git 狀態**：commit、branch、merge 由人或 Agent 直接使用 Git，Tactus 不包裝這些指令。
- **Pool 只在本機**：需要備份或分享時，再評估 Git LFS 或同步儲存，並且只放認可的版本。

曾實作 guarded promotion（`tactus accept`：base 檢查、改寫 `render` 預設值、重跑驗證）。A/B probe 顯示，清楚的指引就能讓 fresh Agents 正確處理 source 移動的情況，因此不採用；2026-09-26 第三回合 probe 再次 3/3 通過後，暫存的分支已刪除（見 thoughts `2026-09-26-delete-tactus-accept.md`）。結構性的修改在 Git branch／worktree 上試，接受時用 Git 合併。

**尚未定案：**state isolation 的實作、range／stem 的效率與延遲目標。Real-time transport 由 live input 或人類即時協作的實際需求再評估；cache 不是候選隔離成立的前提。

## 驗證與觀察：先定義技術契約，再提供判斷材料

Runtime 檢查宣告的 shape、dtype、finite values、sample rate、時間關係與 output encoding 契約。音量是否需要限制等政策必須明確；mono 相容性、bass 是否置中或某個 reverb 比例，不能因 validator 的偏好而成為隱藏規則。

分析結果作為音訊旁的可選觀察交給 Agent。短音訊可能無法量測 integrated LUFS，估計 tempo 也不代表作品採用該 BPM。用來做決定的分析（tempo、onset、切點、beat grid）在 `render` 之外執行一次，並把結果固定成素材或 source 常數。這樣做有兩個效果：採用的結果本身就是被版本化的創作決定；分析套件升級也不會悄悄移動切點。跟隨訊號即時變化的處理（compressor、sidechain）屬於 DSP，仍留在 `render` 內。Tactus 提供可比較的 audio／stems／range，音樂判斷由 Agent 的聽覺工具與人類回饋完成。

`tactus.analysis` 按分類（category）組織，一個 category 是一個模組，用 progressive disclosure 的
三層 `--help` 自我描述：`tactus analyze --help` 列出 category，`tactus analyze CATEGORY --help`
列出該 category 的分析，`tactus analyze CATEGORY NAME --help` 給參數、欄位、單位與定義。已出貨三個
category：`level`（整段音量 `loudness`、`true_peak`、`sample_peak`、`rms`、`clipping`，
以及 `momentary_loudness`、`short_term_loudness`、`loudness_range`、`rms_curve`、`peak_curve`）、
`spectral`（`spectrum`、`band_levels`、`centroid`、`peaks`、`stft`，以及自有的
`mel`、`chroma`、`mfcc` 特徵），以及 `rhythm`（`beats` 的拍點／速度估計、
`onset_strength` 曲線與 `onsets` 起音候選點）。每個分析都是 `tactus.analysis.CATEGORIES[category].ANALYSES` 裡的一個函式，回傳
dict（可含 NumPy arrays），帶一個 `revision` int；CLI 從這個結構自動產生子命令，沒有手寫的 per-analysis CLI
程式碼。這些都只回報數值，從不判斷通過或失敗——門檻由 work 或 Agent 自己套。

**音量曲線與 LRA（2026-09-29）：** 參考 pymixtool 的功能範圍，演算法直接由 Tactus
以 NumPy／SciPy 實作，不依賴 pymixtool。新 LUFS 曲線用 De Man K-weighting 係數；
Integrated LUFS 也已改成自有實作，保留原 pyloudnorm 的 RBJ 濾波器、區塊取整、
尾端分母與 gating 規則；與曲線的 De Man 濾波器定義仍不同。
Momentary／short-term 分別使用 400 ms／3 s 完整時間窗，時間戳標在窗的結尾，
預設 hop 為 10 ms／100 ms。LUFS 加總加權聲道能量、RMS 平均聲道能量、peak 取所有
聲道最大值，都不先混成 mono。曲線不補零，不足一窗回傳空值列，零能量用 null 表達。
LRA 獨立在輸入尾端補 1.5 s 靜音，依 EBU 定義計算閘控後的響度分布；
原音訊短於 3 s 或沒有有效區塊時回傳 null，短於 60 s 標成 provisional。
這些是量測值，沒有自動混音、品質評分或門檻裁決。驗證見
[level curves 測試](../tests/test_level_curves.py)。

**動態與頻譜分布（2026-09-29）：** 新增 `level.crest_factor`／`crest_factor_curve`、
`spectral.bandwidth`／`rolloff`／`flatness`，都是自有 NumPy／SciPy 計算，沿用函式與
自動產生 CLI 的同一份 registry。Crest 使用跨聲道最大 sample peak 除以全樣本 RMS；
曲線採完整視窗與窗末時間，沒有 downmix。它不等於 true peak 減 LUFS 的 PLR，也不等於 LRA。
三項頻譜描述沿用 Mel/MFCC 的 centered Hann 與 frame-center 時間，聲道相加；bandwidth
是 power 加權的頻率標準差，rolloff 是累積 power 達指定比例的第一個 bin，flatness 是
power 的幾何／算術平均比。Flatness 先按各 frame 的 peak power 設相對 floor，避免絕對
floor 讓單純 gain 改變數值。靜音與聲道抵消後的零 power frame 回傳 null。
全部回傳 JSON lists/scalars，不是品質判斷。數值定義見 [analysis 文件](analysis.md#dynamics-and-spectral-distribution)，
回歸驗證見 [descriptor 測試](../tests/test_analysis_descriptors.py)。既有 stereo／DC／dropout 延後決定不變。

**沒有 `pitch` category**：先前的本機頻率驗證顯示 `fundamental` 在未見素材上
只有 47.5% 落在 ±50 cents 內——兩個 SFZ bass patch 帶有比 fundamental 更大聲的低八度層，讓每種方法
（harmonic-sum、librosa pyin/yin、autocorrelation）都失準；`f0_over_time` 的表現更差（62%，FM tone 上
只有 7%）。在有更可靠的 pitch 估計方法之前，這部分不出貨。

**自有特徵與 onset（2026-09-29）：** 初版以 librosa 建立非 NN 基準，後續改由 Tactus
以 NumPy／SciPy 維護相同的 Mel、chroma、MFCC 與 onset 算法。
`onset_strength`／`onsets` 採官方範例的 Mel-based SuperFlux 做法，公開 framing、
threshold、間隔與 backtracking 參數，並記錄實際 hop 與頻率上界。先前 2 ms 精準起音
契約失敗的結論仍成立；這次提供可供選擇的候選點，不宣稱取代人工確認或達成 sample-accurate 切片。
`chroma` 是十二音級特徵，不推定調性／和弦；`mfcc` 是 log-Mel 的 DCT 特徵，不決定音色相似度。
三種 spectral 特徵在 Python 回傳 feature-by-time NumPy arrays，CLI 用既有 `--out`
附件機制保存，不另建檔案協定。新特徵有各自單位，不沿用舊 spectral 的 full-scale-sine dB 定義。
聲道政策延續分類：spectral 相加、rhythm 平均；時間窗與 padding 都在函式／CLI help 說明。
內建分析是可選工具，作品自己的 Python 與註冊分析仍是正式途徑。
使用限制見 [analysis 文件](analysis.md#onsets-and-feature-arrays)，
自有實作的比對見 [owned analysis 測試](../tests/test_owned_analysis.py)；效能探測保留在本機 experiments 工作區。
沒有事件時開啟 backtrack 回傳空清單，修正原先上游會拋錯的邊界情形。

**SuperFlux 雙前端（2026-09-29）：** `onset_strength`／`onsets` 新增
`filterbank="mel" | "log"`，Mel 維持預設。Mel 使用 `n_mels` 控制的 Slaney power／dB；
log 使用 `bands_per_octave`（預設 24）控制的 A440 對齊三角頻帶、magnitude 與
`log10(1+x)`。另一種密度參數不參與計算，但兩者皆驗證為正整數。Log 的 `fmin` 必須大於
零；頻帶邊界取到 FFT bins 並去重，保留範圍內的中心、排除 Nyquist；解析度不足以建立
任何頻帶時報錯。這不是 CQT，兩版 strength 單位也不同。
兩者沿用 Tactus 的 centered periodic Hann、整數 hop、lag 補償與 peak picking，
不宣稱與原版 SuperFlux 應用程式完全相同。既有結果欄位與 revision 1 保留，CLI params
記錄選擇的前端；既有 Mel 事件時間須保持一致。共同的稀疏頻帶投影與分塊 FFT 減少
計算與暫存配置。前端與參考濾波器的比對見
[SuperFlux 測試](../tests/test_superflux_frontends.py)。


**Q transforms、tempogram 與矩陣圖片（2026-09-29）：** 內建 `spectral.cqt`、
`spectral.vqt` 與 `rhythm.tempogram`，由 NumPy／SciPy 計算，DTW 不納入。
CQT／VQT 共用幾何頻率格與可變長度 Hann 濾波器；VQT 的 gamma 增加頻寬並縮短低頻
時間窗，gamma=0 與 CQT 相同。spectral 聲道相加、置中的零填補、明確整數 hop；
回傳 magnitude、頻率／時間軸、各頻帶的窗長與解析後的 gamma。
這是直接濾波器定義，幅度正規化與 librosa 的遞迴重採樣近似版本不同，不承諾逐值相同。
Tempogram 由現有 Mel SuperFlux onset strength 做局部線性自相關，除以零 lag 能量，
回傳正整數 lag 對應的 BPM／時間矩陣；rhythm 聲道平均。保留半速／倍速候選，不推定唯一 BPM。

`analysis.image(result, ...)` 從既有矩陣產生帶座標與色階的 SVG，內嵌 PNG heatmap，
不增加繪圖依賴。新三項及既有 Mel／chroma／MFCC 共用這個呈現層。
STFT 也共用此呈現層；revision 2 改成直接回傳 `times_s`、`freqs_hz`、`level_db`
陣列，取代舊的摘要／Python `out=` 寫檔介面。CLI 與其他矩陣分析一致，需要 `--out`。
原本的 full-scale sine dB 定義保留；短素材補零以維持指定 FFT 格點。
STFT 圖片預設 −80..0 dB，靜音的 `-inf` 僅在顯示時落到色階底端；時間縮減先在
linear power 平均再轉回 dB。Mel spectrogram 沿用 `spectral.mel`，數值為 power，
圖片才轉成 feature power dB；與 STFT 的 dB 參考不同，兩者色階不能直接當成相同音量。
CLI `--out DIR --image` 同時保存數值、圖片與 artifact hashes；`--image-min/max`
控制顯示範圍並與分析 params 分開記錄。Python 始終能直接取得完整矩陣。
圖片最多 1200 個時間欄，先取數值區塊平均再轉色彩；列等距呈現並標示實際中心頻率／BPM，
STFT 的 Hz 軸為線性，其他分析保留原本的頻帶／lag 間距。Q magnitude 的 dB 與
Mel power 的 dB 都是特徵單位、非 dBFS。
規格與限制見 [analysis 文件](analysis.md#stft-mel-spectrogram-cqt-vqt-tempogram-and-images)，
數值與訊號驗證見 [Q-transform 測試](../tests/test_q_transforms.py)。

**Beat tracking 已整合**：`tactus analyze rhythm beats FILE` 與 Python 使用同一函式。
72 個驗證音檔經 CLI 的三個結果欄位與直接呼叫 pyqmdsp 完全一致；對原 Vamp 參考的平均
F-measure 差 0.000492，小於 0.005 門檻。這是特定素材的驗證，不保證所有音樂準確。
約 7.45 秒以下的有效音訊或全靜音會回傳空陣列與 `bpm: null`，不猜測小節或第一拍。
分析結果採用後仍依 frozen-analysis 規則固定成素材或 source 常數。使用契約見
[拍點分析](analysis.md#beat-analysis)；原始 corpus 比對保留在本機 experiments 工作區。

**作品自訂分析與交付：** 常用或難實作的能力由 Tactus 內建；其他分析與交付邏輯由作品
自己的 Python 定義，在 `pyproject.toml` 明確註冊：`[tool.tactus.analysis]` 的 `category.name`
對應 `module:function`，`[tool.tactus.export]` 的 name 對應相同形式。CLI 以
`tactus analyze category name`／`tactus export name` 呼叫，只 import 被選中的函式。
函式仍可直接由 Python 使用；keyword-only 參數形成 typed flags，內建與自訂共用紀錄流程。
分析回傳 dict，NumPy arrays 隨 `--out` 成為附件；export 接受具名 arrays 與 out 目錄，
回傳 JSON dict。紀錄包括輸入、callable、作品 source／config／lock、參數與實際環境，
不追蹤任意外部 I/O，也不隔離 Python 副作用。契約與操作見 [project commands](project-commands.md)。

**尚未定案：**共用 validation report 或 analysis report 的必要欄位與介面；
pitch（若日後有可行方法）併入 `tactus.analysis` 的形狀。以真實製作與修訂流程驗證需要，再決定哪些觀察
值得標準化。
