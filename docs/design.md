# Tactus 當前設計

本文件保存我們目前認為合適的做法，以及尚未定案的設計邊界。內容獨立、自足，直接隨新決策更新；歷史實驗不需要同步修改。這些選擇包括待實作的方向，不代表現有 runtime 已經全部支援。

視覺樣式、design tokens、品牌資產與互動展示統一維護於 [design/](../design/README.md)。

## 創作介面：Functional Python 與少量執行邊界

作品是普通 Python；Tactus 只在執行邊界提供 `render()` 約定與 `run`。Production 以普通 Python modules、functions、NumPy arrays 與資料結構組成。函式清楚表達輸入、輸出與處理順序，盡量避免共享 mutation，讓音樂片段、訊號處理與混音容易重用和修改。Agent 可以直接呼叫既有套件，也可以撰寫作品自己的 DSP。

分解方式是：選擇素材身分、產生或處理音訊、組合完成的訊號、交付作品宣告的 outputs。Runtime 因此能在必要處提供可靠執行，又不接管 Agent 的分組、角色、routing 與音樂算法。

**`render` 約定：**作品的 Python 檔案提供同步 `render(*, ...)`。具名 keyword-only 參數及其預設值供候選試聽使用；回傳 `{"sample_rate": 整數, "outputs": {名稱: NumPy陣列}}`，可加上 `"takes": {名稱: NumPy陣列}` 保存這次生成的中間音訊，以及 `"map"` 描述時間結構（見時間地圖）。Tactus 負責呼叫、音訊驗證與寫檔。同一個工具因此能執行不同作品，作品內部結構仍由 Agent 決定。不合法的 dictionary 會指出 missing／unexpected fields，並提供正確形狀的範例。完整契約見 [runtime reference](../skills/references/runtime.md#the-render-contract)。

Outputs 共用一個 sample rate，可有不同長度；可以是 mix、stems 或 clips，沒有必要的 output 名稱。交付格式是非空 mono／stereo、有限的實數音訊，經 float32 轉成 PCM24 WAV；不自動混音、正規化或重採樣。這是輸出邊界的約定，不限制中間 DSP 的 headroom。超過 ±1 全幅不會被拒絕：寫檔前裁切到全幅，manifest 與 run 結果回報每個 output 的 `peak_dbfs`（裁切前的峰值）與 `clipped_samples`，由 Agent 判斷是否調整 gain。

舊版 `build(project)`、`Project`／`Track`、arrangement 格式及其 CLI 已退役，不保留相容層。結果直接從回傳值、manifest 與 receipt 讀取，不另設 `inspect`。

**執行層的內部分工：**`run.py` 協調 process、render 與交付；`_contracts.py` 集中錯誤格式、有限 JSON、atomic JSON 寫入與輸出音訊驗證；`_source.py` 集中 source／lock inventory、環境與套件來源。儲存、分析、export 與 init 直接使用共同契約，不反向依賴 runner。這個分工不改變公開 API、receipt 與 checkpoint 格式。

**已完成音訊的讀取：**`render_store` 擁有 published PCM 與 original arrays 的讀取與驗證，以具名結果交給 caller；analysis 不自行解析 manifest，excerpt 只負責選取與裁切。Analysis／excerpt 使用已發布 WAV，export 優先使用原始 arrays。來源 inventory 與 analysis／export attribution 的內部欄位由 TypedDict 定義，對外 JSON 格式不變。Excerpt 失敗時只清理本次呼叫成功建立的目錄，避免刪掉競爭程序的結果。

**延續已接受的 render：**`load_render(ref, outputs=...)` 以單一 tree ref 讀取已匯入 pool 的原始 checkpoint 中作品選定的 outputs（省略則全部），保留原始 dtype、shape、headroom；不重跑樂器、不 resample、不退回 published PCM，未選聲部及 WAV 不讀取也不驗證，`material(tree_ref)` 保留整個資料夾的驗證語意。保存沿用 `material add DIR`，沒有獨立的 save CLI 或作品模型。契約見 [runtime reference](../skills/references/runtime.md#reuse-saved-render-outputs)。

**執行環境選擇：**launcher 與 CLI 共用 project selection，依序採用明確 `--project`、父 launcher 傳遞的 work、可辨識的 uv `.venv` owner，最後才由 cwd 找最近的專案；單純 activate 不覆蓋 cwd 選擇，檔案參數仍以呼叫 cwd 解析。這避免 `uv run --project WORK` 保留 cwd 時跳回另一個 runtime。自訂／共享環境明確使用 `--project`，不靠自動猜測；`doctor` 顯示選擇結果。見 [環境選擇](../skills/references/project-commands.md#selecting-a-works-environment)。

**作品檢查設定：**`init` 在作品的 `pyproject.toml` 寫入可自行修改的本地 pytest／Ruff 預設：recursive checks 略過 runs、excerpts、pool、analyses、exports 與 Git 恢復用的 worktree，Ruff 規則屬於作品本身，不繼承外層 repo 的 lint policy。pytest／Ruff 不是 runtime dependencies；需要固定版本時加入作品的 dev group。舊作品手動合併設定，runtime lock 不隨之升級。見 [作品測試與 lint](../skills/references/project-commands.md#test-and-lint-a-work)。

**Devices：**`tactus.devices` 以普通函式提供大家認得的做音樂方式：`sampler`（把錄音當成有音高的樂器，含 root、起始位置與延音 loop）、`pads`（切片與 one-shot，含 choke）、`steps`（step sequencer，產生事件）。Device 跟音符事件有關；`dsp` 只處理音訊，`synth` 只產生聲音。每個 device 是一個自足的檔案，只依賴 NumPy 與 Tactus 公開模組，可以 import，也可以整份複製到作品裡改；輸入輸出是普通陣列、tuple 與 dict，事件時間一律是絕對秒數。Device 本身沒有音色：Tactus 提供 device，Agent 用素材與設定做出自己的 patch。理由是可見性：有說明與可抄實作的 Agent 才會把素材當樂器演奏，只給素材時它只用在鼓聲；手寫的慣例小工具也會寫錯而不自知。不屬於裝置的做法（resample 自己的輸出、loop 當底再變化、錄音與合成疊加）由 [techniques reference](../skills/references/techniques.md) 說明。不提供 device 類別、chain／rack、track 或 session 模型。契約見 [devices reference](../skills/references/devices.md)。

Pedalboard 內建效果（reverb、chorus 等）以 `fx.process` 套用到完整素材：保留 Tactus 的陣列排列、先 reset、可保留尾音。Tactus 不另寫 reverb。Float WAV 匯出不帶時間戳，同樣的音訊產生同樣的檔案；`tactus analyze --brief` 只印結果欄位。

**尚未定案：**是否提供單音的 root 音高估計；`devices` 這個名稱是否會被誤解成音訊硬體；是否增加琶音器、tracker、looper。targeted rendering 與更廣的交付型別。`select`、`render_audio`、`mix`、`render_all` 是實驗使用過的語彙，不是 public API。

## 時間表達：Temporal abstraction 有價值，但 clock 可選

Temporal abstraction 把 placement、repetition、時間變換與 automation 展開中反覆需要算對的運算集中處理，讓 production source 更直接表達音樂關係；Tactus 以選用的 `tactus.timing` 提供這些運算。它們也可以是作品內的 Python 函式。

時間工具不要求全曲 BPM。作品可以混用絕對時間、全曲 tempo map 與局部 clock，最後一致地解析到 output samples。需要保留的關係如下：

| 作者表達的關係 | 變更時間設定時的行為 |
| --- | --- |
| 事件跟隨全曲 beat position | 全曲 tempo 改變時，事件的絕對時間跟著改變。 |
| 事件跟隨獨立的局部 BPM | 該局部 BPM 只影響跟隨它的事件。 |
| 局部段落錨定在全曲某一拍 | 全曲 tempo 改變時，段落起點跟隨 anchor；段內時間仍依自己的 clock。 |
| 局部段落錨定在絕對秒數 | 全曲 tempo 改變時，段落起點保持固定。 |
| 事件直接使用絕對時間 | 不隨全曲或局部 BPM 改變。 |

作者決定 automation 的數值、邊界、插值方式與用途；helper 只負責正確展開。`repeat`、`scale_time`、`section_envelope` 等名稱只用來描述候選能力。

**`tactus.timing`：**提供 `Clock`（tempo/meter → seconds/frames，含 step／ramp／ramp-time／smooth tempo 變化）、`swing`、`Groove`、beat／seconds envelope、唯一的 rounding 規則 `frame_of`，以及 `add_at`、`markers`、`quantize`、`note_seconds` 等機械性 helper；同類的 `fx.fit_rms` 與 `tactus.load_audio` 也已提供。它只在 `import tactus.timing` 時使用，`render`／`run` 不要求它，作品可保留自己的時間算法或混用。Beats 一律是 0-based quarter note（音樂人數的「第 2 拍」是 `beat=1.0`）。對照 probe 中，這組 helper 消除了 0/1-based beat 誤算與 tempo 曲線近似的錯誤，也減少了程式碼量；probe 中沒人使用的 `db_to_gain`／`gain_to_db` 不提供。見 [runtime reference](../skills/references/runtime.md#musical-time-optional)。

**從拍點擬合固定速度：**`timing.fit_tempo(beats_s, bpm_range=..., step=1.0)` 把已採用的拍點秒數（`rhythm.beats`、其他 tracker 或手打拍）擬合成固定速度格線的候選。它處理給定的數字，不分析音訊，因此不同於範圍外的「groove 從音訊萃取」。每個在 `bpm_range` 內、是 `step` 整數倍的速度都試一次：相位取拍點相位最密集的容許窗，再以 inlier 中位數修正一次；候選依 inlier 比例排序，回傳 `TempoFit`（`bpm`、`origin_s`、`inliers`、`coverage`、`offset_ms`、`p95_ms`、`drift_ms_per_min`、`free_bpm`）。`bpm_range` 必填，因為速度範圍本身就是選擇。兩倍速的格線包含慢速格線的每一拍，inlier 永遠不會較少；`coverage`（有拍點的格點比例）讓「tracker 在 85」與「170 但每隔一格是空的」分得開，tracker 本身數成兩倍時兩者都接近 1，只能由作品依音樂判斷。理由是專輯作品的量測：先找最長穩定段再擬合的做法，在一首 405 拍只有 28 拍算穩定的歌上失敗，逐一嘗試整數 BPM 並計算落在格上的拍數，十一首都找回採用的速度或它的兩倍。

擬合結果就是一個 `Clock`，不另設格線型別。選哪個候選、強拍在哪一拍、目標速度、移調與伸縮引擎都留在作品；作品在 `render` 外決定後，把 `(bpm, 第 1 小節秒數, meter)` 寫成 source 常數，拍點報告保留為釘選素材。`timing.segment` 取出精確長度的 frame 範圍，超出音檔處補零；`timing.warp_markers` 產生讓來源小節線剛好落在目標小節線上的 `time_warp` pairs；`timing.fold` 只把 onset 折疊到拍或小節週期上回傳數字，強拍評分屬於作品。原點承襲 tracker 的放置偏差：qm-dsp 的拍點比專輯以 madmom 為來源的凍結格線早 11–19 ms，文件只記錄，不提供校正 API。

**時間位置的取整：**musical placement 與 excerpt 的秒數邊界共用 `timing.frame_of`，以 `floor(seconds * sample_rate + 0.5)` 取整；恰好半個 sample 時選較晚的 frame，excerpt 終點不包含在輸出內。舊版 excerpt 在部分半 sample 邊界的結果因此不同，已保存的 excerpt 不變。Analysis 視窗與 DSP 時長參數保留各自已記錄的離散化方式。

**時間地圖：**`render` 可以另外回傳 `"map"`，由產生音訊的同一份程式算出作品的時間結構，不另設一份手寫檔案。位置一律是某個 output 的整數 frames：`grid`（小節起點，小節編號與 `Clock` 一樣從 1 開始；`end` 可以超出 output，因為母帶常在最後一條小節線前結束）、作者命名的 `lanes`（spans 或 points，段落、記號、歌詞、大鼓都是同一種資料），以及 `segments`（播放器可以循環、進入或離開的片段，含 body 與尾音、可離開的位置 `joins`，可接的片段名稱或 tag 是選填）。Tactus 只檢查結構與參照（output 存在、frame 在範圍內、位置不倒退、join 目標存在），錯誤指出欄位路徑，不賦予任何 lane 名稱意義，也不判斷接起來好不好聽；依狀態而定的規則（時段、剛才放過什麼）留在作品。`run` 把正規化後的地圖存成 `map.json`，receipt、`render.json` 與 manifest 記錄同一個 hash，含地圖的 run 使用 manifest version 4；沒有地圖的 run 寫法不變。`Clock.grid(first, last, offset=)` 是唯一的 helper，經由 `frame_of` 產生 `grid`，自有時間算法的作品直接給 frame 清單。理由：五件互動作品與三支 MV 各自把 BPM 抄進 JavaScript、檢查腳本與畫面程式，光 MV 就有六處重算小節；改成以 frames 而非 clock 規格為契約，是因為同一捲帶子會混多個速度、3/4、32 kHz 與倒帶小節，clock 規格表達不了，也會讓「clock 可選」失效。《一卷帶子》驗證：36 個 loop 的長度與小節、帶子的 94 條小節線都由地圖提供，與原本的 `Grid` 算術一致（只有一條在 filter 接點上相差一個 frame 的重複線被去除）。見 [time map](../skills/references/runtime.md#the-time-map-optional)。

**尚未定案：**seconds／samples placement 與總長度的正式介面，以及哪些 tempo-map／local-clock 計算值得由 Tactus 共用超出 `tactus.timing` 現有範圍。漸變 tempo、rubato、巢狀 clock 與跨 tempo 變化的事件長度仍需驗證；MIDI 檔案讀入 tempo、groove 從音訊萃取，以及「全曲需要一個 clock」的要求，明確不在範圍內。Marker warp 與單一比例伸縮在真實母帶上的聽感差異尚未比較；以實際拍點（而非固定格線）修正母帶本身微小漂移的 marker map 仍是作品程式碼。

## Pattern：選用的局部規律工具

Tactus 不提供 Pattern 型別或必要的編排模型；週期規律以原生 Python 加 `tactus.timing` 表達，共用 `timing.euclid` 與 `timing.cycle` 兩個慣例。Step sequencing 以可選的 device（`devices.steps`）提供：它只把格子轉成普通的事件 tuple，目的是讓這種做法看得見，不是減少錯誤。

Pattern 指可命名、組合與重用的規律，例如 cycle、phase、Euclidean distribution、polymeter、rotation、reverse 與週期性 transformation。一次性的 fill、section 選擇與音樂例外留在 Python；例外本身形成作品要保留的週期時，才值得用 Pattern 表達。方向是把局部 Pattern 展開成普通事件，再與手寫 Python 或其他 generator 產生的事件使用同樣的時間與 placement 能力，下游不必因事件來源不同而採用不同編排模型。

`timing.euclid` 依 Tidal 的左旋慣例，`timing.cycle` 讓 figure 跨小節連續循環；兩者回傳 step 編號，不引入 pattern 型別。對照 probe 中，Pattern 模組只讓原始碼變短，沒有減少錯誤、token 或修改量；真正值得共用的是慣例本身，因為 Agent 各自重寫 Bjorklund 時會把旋轉方向做反。

**尚未定案：**重新開啟時要決定事件資料型別、Pattern 的正式函式集合與共用範圍。`realize(...) -> tuple[Event, ...]` 是已測過的候選邊界；它不要求整首作品使用 Event schema。Lazy／infinite Pattern、probability、seed 與 incremental realization 尚未收斂，也沒有採用 string mini-notation 的需求。

## 素材：版本化身分與內容儲存分開

作品保存固定的素材身分，runtime 依身分取得內容。素材 bytes 可以放在 Git 外的 content-addressed store；更換內容必須改變作品中被版本化的參照。素材遺失應回報無法取得，不能悄悄換成同一路徑下的新檔案。

匯入時可以從一般檔案路徑開始，但持久的創作依據固定到內容。只在 build 時對可變路徑算 hash 並寫入 generated receipt，無法防止同一個 source revision 讀到不同素材。

作品在 Python 中以具名常數寫入 inline digest，並用 `material("sha256:…")` 取得驗證過的檔案路徑。`tactus material add FILE...` 把檔案匯入本機 pool（`$TACTUS_POOL`，預設 `~/.local/share/tactus/pool`）並印出 ref。身分是原始檔 bytes 的 SHA-256。解碼、擷取區段、sample rate 與 headroom 由作品自行處理。缺檔與內容損壞分別回報。Pool 的目錄結構與 tactus-daw 相容。外部執行檔與 native library 由作品在使用處以 `tool(...)` 宣告，receipt 記錄其路徑與 hash；目前只記錄，不以 hash 鎖定。

資料夾（SFZ 樂器、VST3 bundle）以 `tree:sha256:` ref 固定。digest 是「排序後的相對路徑加上每個檔案 hash」這份清單的 hash；版本控制目錄（`.git` 等）不列入。`material()` 在 pool 內以 hardlink 還原整個資料夾並逐檔驗證，所以相對路徑可以直接使用。`tool(資料夾)` 對整個 bundle 計算身分，並回傳資料夾路徑，可直接交給 `pedalboard.load_plugin`。

**尚未定案：**解碼後音訊的身分、import gain／headroom 政策，以及 processor 身分不符時是否拒絕執行。

## 執行與重現：先可靠產出，再按需要重用計算

Python 執行後產生可保存的音訊材料與宣告 outputs；編排快照、receipt 與其他執行資料都是衍生物。Receipt 辨識這次執行的 source、素材、參數、dependencies 與 runtime／processor 身分，讓結果能追溯到輸入。已保存的 WAV 可以直接播放，也可透過 OutputStore 檢查內容 hash 與音訊 metadata；source rebuild 則重新執行 Python，受 randomness、外部輸入、套件與 processor state 影響。保存結果與重新製作的保證分開表達。

**`run`：**`tactus.run(source, out=..., params=...)` 與 `tactus run SOURCE --out NEW_DIRECTORY --params JSON` 每次使用新的 Python process，避開既有 bytecode cache，從 entry 所在資料夾解析 sibling imports 與相對素材路徑。作品的 log 走 stderr，CLI stdout 只交付一份 JSON 結果。已存在的輸出位置會被拒絕。`run` 先把原始 arrays、receipt 與 take refs 保存為 `render/` 和 `render.json`，再寫預設試聽 WAV；checkpoint 完成前的失敗會清除該次目錄，完成後的交付失敗則保留原始結果，只清除不完整的 WAV。

**Manifest 與 receipt：**`manifest.json` 保存 sample rate 與具名音訊的內容 hash、frames、channels，最後發布，作為完成標記；WAV 檔名為 `<name>-<sha256 前 8 碼>.wav`。`receipt.json`（format_version 4）記錄實際參數、source hash、最近一個 `uv.lock`（`dependency_lock`）、素材 refs、宣告的 tools、實際 import 的套件版本與來源（`package_sources`）、runtime 版本、實際執行環境（`environment`）、`@stage` 呼叫與是否 `--reuse`。欄位定義見 [run results](../skills/references/runtime.md#run-results)。舊作品借用 Tactus checkout 的環境執行時，`dependency_lock` 可能為 null，`environment.lock` 則指向 Tactus 的 lock。

Receipt 的 `source_files` 與 `dependency_lock` 記錄執行開始時的狀態，與 `source.patch`、take 的 source snapshot 一致。執行中有 `.py` 或該 lock 被修改時，完成的 run 照樣保留，改由 receipt 與結果的 `source_changed` 列出改動的檔案、開始與結束的 hash，以及這次執行是否 import 過它：沒有 import 的檔案（例如 scratch script）不影響音訊，`certain` 為 true；import 過的檔案若在 import 之前就被改，執行的是新內容，hash 比對無法分辨先後，所以標為不確定（`certain` 為 false），需要可追溯的音訊時重跑。這次執行寫入、key 用到改動檔案的 stage cache entry 會被移除，避免以開始時的 hash 重用可能來自新內容的結果。不從複製的 source 執行：作品的相對素材路徑與 cwd 都指向原資料夾。理由：長時間的 render 不應因為作者在等待時修改程式而整個作廢；receipt 仍如實說明哪些歸因可靠。未以 `material()` 取得的檔案、未宣告的執行檔、網路存取與隨機性不在紀錄範圍內。Runtime 不隔離任意 Python 的外部副作用。

**每個作品是自己的 uv project：**`tactus init DIR` 在不存在或空的資料夾建立 `pyproject.toml`（依賴 `tactus`，`[tool.uv.sources]` 釘住一個 Tactus 來源，`requires-python` 複製自正在執行的 Tactus）、`.gitignore` 與 `uv.lock`，不寫 `song.py`。來源預設是正在執行的 Tactus 自己的來源（讀自 PEP 610 `direct_url.json`）；editable checkout 只在乾淨且 `HEAD` 已在 remote 上時允許，否則失敗並提示先 push 或改用 `--tactus-path`。`--tactus-path PATH` 與 `--tactus URL@REV` 明確指定來源。作品因此能自行 `uv add` 套件，receipt 的 `dependency_lock` 就是作品自己的 `uv.lock`，環境不隨 Tactus checkout 移動。沒有 `pyproject.toml` 的舊作品維持原本的執行方式，不會被拒絕。見 [Creating a work](../skills/references/runtime.md#creating-a-work)。

**全域 CLI 與作品環境：**CLI 以 uv 全域安裝一次。在作品內，launcher 以 `uv run --project DIR --locked` 執行作品自己的 Tactus 版本與 dependencies；缺少或過期的 lock 會失敗，不退回全域版本。作品沒有自己的 `uv.lock` 時，若它是上層 uv workspace（`[tool.uv.workspace]` 的 `members`／`exclude`）的成員，就使用 workspace 根目錄的 lock 與 `.venv`，與 uv 自己的解析一致；不是成員就照樣失敗。錯誤訊息指出缺的是作品還是 workspace 的 lock。Receipt 的 `dependency_lock` 同樣記錄這份 workspace lock。`init` 與作品外的命令使用全域環境。

**獨立 export：**`tactus export wav|flac|stems RUN --out NEW_DIR` 讀取已驗證的原始 checkpoint，不呼叫 render，可在試聽交付失敗後重試，也能交付 FLOAT／DOUBLE WAV 保留 headroom；三者都可用 `--names` 只交付指定的 outputs。`run` 維持一次命令完成生成與預設 PCM24 試聽，代價是另存原始 arrays 的磁碟用量。沒有 checkpoint 的舊 run 使用已保存的 PCM，記為 `published-pcm`，不能恢復丟失的精度。`tactus prune RUN_DIR...` 在驗證已發佈的 PCM 後移除 checkpoint（先 `render.json` 再 `render/`），讓不再需要原始精度的 run 釋放空間並成為同樣的 `published-pcm` 狀態；takes、receipt 與 manifest 不動。Checkpoint 預設寫入：哪個候選會被採用事後才知道，先存再清永遠來得及，先不存則只能重跑而重跑不保證相同。`run` 的結果以 `render_bytes` 回報 checkpoint 佔用的大小；事先確定用完即丟的候選可用 `tactus run --no-checkpoint` 不寫入。每次 export 有自己的目錄與 `export.json`，失敗只清除該次新目錄。`take export` 負責單一演奏素材包的轉移。見 [export 契約](../skills/references/project-commands.md#export-a-completed-render) 與 [export 測試](../tests/test_export.py)。

**演奏檔案作為輸入：**玩出來的帶子、路線或步驟以 JSON 檔交給作品：`tactus run --param-file NAME=FILE`（可重複；Python 為 `run(param_files=...)`）以與 `--params` 相同的嚴格解析綁定到同名參數，同一名稱同時以兩種方式給出是 `invalid_request`。Receipt 的 `parameters` 照舊保存值，`parameter_files` 另記檔案路徑、sha256 與大小，原始 bytes 複製到 run 的 `parameters/NAME.json`，所以演奏隨 run 保存，也能從那份副本再 render 一次。Tactus 不定義演奏格式，因為每件作品的遊戲規則不同；作品在 `render` 開頭以 `tactus.InvalidParameters` 拒絕不合法的演奏，回報為 `invalid_parameters`（phase `bind`，exit 2），與 render 當中的崩潰（`execution_failed`）分開。目前不提供不 render 的 `--check`：《一卷帶子》的伺服器以這個錯誤回應 HTTP 400，往返約 2 秒（process 啟動與 import）。

**帶地圖的交付：**exporter 宣告 keyword-only `time_map`／`run_identity` 時，`deliver` 交給它驗證過的地圖與 run 身分（run、manifest／receipt／map hash、origin），兩者不會成為 CLI flag，沒有宣告的 exporter 照舊執行；`export.json` 的 `source.map` 記錄地圖 hash。內建 `web` 以明確指定的 codec（`wav`／`flac`／`aac`／`opus`，有損需指定 `--bitrate`，經 `tool("ffmpeg")`）寫出瀏覽器音訊與 `bundle.json`：長度（frames 與秒）、音量、波形輪廓、地圖（frames 與秒兩份）與 run 的 hash；它把寫出的檔案再解碼一次，回報 frame 數與位移差異但不拒絕，並註明是哪個 decoder 的結果。ffmpeg 會把 AAC 最後一個 packet 整個解出來，所以 AAC 先裁到 MP4 自己宣告的長度（sample table 減去 edit list 的 priming），也就是瀏覽器實際播放的長度，多出的記為 `padding_frames`：《一卷帶子》36 個 AAC 在 Chrome 的 `decodeAudioData` 長度全部等於原始 frames，偏移為 0。`srt` 把 spans lane 寫成字幕（最近的毫秒，恰好一半取較晚）。`curves --fps` 在每個畫面時間取 `level.rms_curve`／`peak_curve`（dBFS，靜音為 null）中心最近的分析視窗，不內插，因此 32 kHz／30 fps 不會累積誤差；同時給出 points lane 的逐格次數與 grid 的小節、相位與段落。重新取樣、正規化、混音、裁切，以及衰減、百分位正規化與平滑等畫面美學都不在交付裡。理由：每件作品的 `make_world.py` 都重寫同一套轉檔、雜湊與波形；《一卷帶子》改用 `export web` 後不再有 ffmpeg、雜湊與速度常數，36 個 AAC 與舊輸出逐 byte 相同。見 [帶地圖的交付](../skills/references/project-commands.md#delivering-with-the-map-web-srt-curves)。

**常駐的渲染服務：**互動作品要在下一段播放前才算出來時，`tactus serve SOURCE --out DIR`（選用的 `tactus[serve]`，FastAPI＋uvicorn；只做離線 render 的作品不需要）把作品載入一個常駐子行程一次，之後每個 `POST /render` 用與 `tactus run` 相同的 `params`／`param_files` 契約算一次，結果是 `DIR/<session>/NNNN/` 這樣的普通 run 資料夾，`export`、`prune`、`analyze` 照用。核心 `tactus.serve.Service` 是普通 Python，HTTP 只是薄的一層。作品在子行程裡、不在伺服器行程裡：`python_packages` 不會混進 FastAPI，重新載入就是換一個乾淨的行程，正在算的 NumPy 也只能靠結束行程取消；一個 worker 一次只算一個請求，因為 stage context 與輸入紀錄是行程全域狀態。Inventory、Git 紀錄與 take snapshot 每次載入在 import 前取一次；每個請求開始前重新比對作品的 `.py` 與 lock，有變就換新的載入（`reason: "source_changed"`），所以 receipt 的 `source_files` 一定是那次載入 import 的內容；請求算到一半被改，照 `source_changed` 記錄，載入時已 import 的檔案標 `imported_at_load` 並視為確定。Receipt 加上 `service`（session、請求編號、load id／時間／原因／pid）。同 `key` 的新請求取代還在排隊的舊請求（`superseded`，409），`/cancel` 結束正在算的請求（`cancelled`）；`InvalidParameters` 是 400，帶作品自己的訊息。只綁 loopback，拒絕非本機的 Host／Origin 與非 JSON 的 POST。磁碟：已發佈的 PCM 本身就會長大（Island 每步約 30 MB），`--retain N` 只留最新 N 個請求資料夾，舊的 receipt 移到 `retired/`；`session.jsonl` 記錄每次載入與請求。理由：Island 同一步冷啟動 `tactus run` 中位數 3.97 秒，服務 1.38 秒且音訊逐 byte 相同，單一片段約 0.17–0.24 秒；重新載入約 2 秒。見 [serve 契約](../skills/references/serve.md)。

**尚未定案：**join 的可接片段清單在沒有狀態時對播放器是否夠用；Island 每一步一份 receipt 的 session log 是否需要 Tactus 格式；演奏是否記錄它所根據的素材 bundle（`manifest_sha256`），並與 render 載入的素材比對；review 的 0-based 小節與地圖 1-based 小節的對齊；外部母帶經普通作品進入（第二個驗證案例，08〈憨膽〉MV）尚未實作。

**Opt-in 的 stage reuse：**`@stage` 標記 module-level 函式。不帶 `--reuse` 時是單純呼叫，沒有額外開銷；帶 `--reuse` 時，stage 的 source、它實際觸及的 source、dependencies、Python／Tactus 版本與參數的 canonical hash 全部相符才重用結果，並重播記錄的 materials／tools（tool 重新雜湊比對）。參數與結果只支援 NumPy array 與純值，其他型別照常執行，receipt 說明原因。「觸及的 source」從 stage 函式的 code 出發，沿它用到的名稱追到作品裡的函式、class 與 module（module 只追 code 用到的屬性），取這些檔案的 hash；觸及的純值（常數、array 與它們的 list／dict）在呼叫時一併雜湊，因此從別的檔案 import 的常數、`render` 在呼叫前改的 module global 都算在內。改 mixer 或 `song.py` 的編排不會讓沒觸及它們的 stage 重跑。無法歸因時保守處理，退回以 entry 資料夾所有 `.py` 為 key：函式內的 `import`、`getattr`／`exec`／`eval`／`__import__`／`globals`／`vars`／`importlib` 這類動態查找，或觸及的物件不是純值（Generator、外掛、自訂 class 的 instance）。Receipt 的 `stages` 以 `source` 列出 key 用到的檔案，`source_reason` 說明為何退回全部檔案。透過 method 改動的狀態只以呼叫時的值計入，物件屬性不追。理由：只改 mixer 卻讓所有 stretch 重跑，讓 reuse 在多檔作品裡失去作用；寧可多重跑也不錯誤重用。結果存在 `$TACTUS_POOL/stages/<key>/`，沒有 garbage collection。Cache 驗證格式版本與 SHA-256：entry 損壞回報 `cache_corrupt`，無法驗證的舊格式回報 `cache_incompatible`，都不自動重跑演奏。見 [stage reuse](../skills/references/runtime.md#reusing-unchanged-stages)。

Reuse 的價值主要是讓候選比較公平，而非速度：每次 render 都不同的外掛（如 OB-Xf）會讓候選混進隨機差異，對照 probe 中 reuse 讓 Agent 交出只改目標聲部的候選。實際等待 render 的時間占比小，速度本身尚不構成需求；checkpoint、region-only 計算與跨機器共用 cache 等實際 consumer 證明需求後再加入。Graph 可以支援執行與檢查，但不擴張成全曲創作模型。

**保存 take 是正式重現方式：**Tactus 使用原版樂器；原生修補只是原因調查與可行性證據，不是安裝或重現的前提。直接重跑 OB-Xf／SFZ 這類 generator 不保證相同輸出，因此要保留的演奏成為作品明確引用的 material，生成 source 與 receipt 一併保存；它不應只存在 cache，也不代表 generator 本身可重現。作品在同一次 `render` 回傳 `takes`，讓試聽成品與被保存的中間音訊來自同一個演奏。

候選存在 run 的 `takes/NAME/`，`audio.npy` 保留原始 numeric dtype、shape 與 headroom，附上生成 receipt、source／lock snapshot 與 source patch；含 takes 的 run 使用 manifest version 3，其他 run 維持 version 2。`tactus take save RUN NAME` 驗證候選並存入 material pool。採用由 source 裡的 ref 決定：`load_take(REF, sample_rate=...)` 讀回原始陣列，不執行 generator，也不要求安裝 provenance 裡的 tools；sample rate 不符或素材遺失／損壞會失敗。更改 MIDI 或 patch 時另開生成 run，選擇後才換 ref；舊 ref 可退回，source 不自動偵測或重新生成 pinned take。

`tactus take export REF --out DIR` 匯出音訊與 provenance，另一台電腦以 `tactus material add DIR` 匯入得到相同 ref；重新生成所需的 sample libraries、binaries 與 Python 環境需另外準備。Pool 是本機持久素材庫，需備份；stage cache 可刪，不能充當採用演奏的唯一保存處。固定成素材的演奏已在乾淨 pool／Python 環境、斷網的同主機 Linux 容器中重建出相同 WAV；這還不是通用的交接 CLI。見 [Saved takes](../skills/references/runtime.md#saved-takes) 與 [saved takes 測試](../tests/test_takes.py)。

**Agent 指引與 plugin：**指引由單一 [`tactus` plugin](../skills/README.md) 提供，manifest 放在 repo 根目錄的 `.claude-plugin/` 與 `.codex-plugin/`，兩個 marketplace 都指向根目錄。四個 skills 放在 `skills/`，共用契約由 `skills/references/` 維護，小型合成音源範例放在 `skills/examples/`；整個 skills 目錄的相對引用可獨立使用，runtime 另行安裝。

- `compose` 負責用 functional、modular Python 撰寫、執行與修訂作品，以 progressive disclosure 組織和閱讀 code：先看整體 form／signal flow，再進入相關模組契約與演算法。模組採 deep module 原則：小而清楚的 interface 承載完整能力，隱藏演算法與協調細節，保留 caller 要控制的音樂選擇；不只增加轉接層。套件清單與整合注意事項在共用 reference 按需查閱。
- `dsp` 負責使用、撰寫與驗證聲音源與 processor（sound design 與訊號處理）；`measure` 涵蓋使用與撰寫分析、驗證定義，以及註冊作品自己的 analyze 指令。Compose 在需要時連到這兩個 skills，把量測、time-stretch 與效果組合成作品自己的做法，不要求每首作品走同一流程。
- `version` 指導 Agent 用版本探索、比較、保留與重用創作方向，並負責 Git 操作紀律：確認作品實際被追蹤、初始 commit、候選採用與舊版本恢復。Compose 在開始作品與接受修訂時使用它。

`init` 要求 Git 可用並建立作品自己的 repository，即使作品位於外層 checkout；缺失或失敗明確報錯。Commit 由 Agent 在 source 準備好後直接操作 Git；renderer 只唯讀記錄，`doctor` 不檢查 Git。Git binary 與 ancestor HEAD 都不足以證明作品已保存；生成音訊在 Git 外保存，receipt 保留當次執行的原始身分。

素材切片與分軌交付以 [production reference](../skills/references/production.md) 提供可改寫的 authoring pattern：loop body／尾音分開，source 與 output 的格點各自明確；post-channel、pre-master 與最終 master 的關係由作品 source 宣告。不提供通用 sample/track API。內建 DSP、Pedalboard 與作品自寫函式都可自由使用；自寫分析不必先進 Tactus core。程式結構的紀律服務可理解、可修訂的音樂，不替 Agent 指定音樂形式。測試持續比對真實 manifest、receipt 與錯誤欄位。

**尚未定案：**source rebuild 的完整依賴與隨機性契約、超出現有 receipt 的歸因範圍。不能從素材 hash 相同推定所有重新執行都可重現。

## 作品的介面：交出時間、收進決定、接得起來

MV、互動作品與現場演出用到的功能是同一個介面的三個部分（原則見 [positioning](positioning.md#8-作品可以有介面座標是音樂的時間)），座標都是某個 output 的 frames：

| 部分 | 作品做的事 | Tactus 提供 |
|---|---|---|
| 交出時間 | `render` 回傳 `"map"`：grid、lanes、segments 與 `joins` | 驗證與 `map.json`（見時間地圖）；`export` 的 `web`／`srt`／`curves` 把同一份地圖轉成網頁、字幕與逐格曲線（見帶地圖的交付） |
| 收進決定 | 以參數或演奏檔案接受決定，不合法時丟 `InvalidParameters` | `--params`／`--param-file`，演奏隨 run 保存（見演奏檔案作為輸入）；要在播放中算下一段時用 `tactus serve`（見常駐的渲染服務） |
| 接得起來 | 在地圖宣告可循環、可離開的位置與可接的片段 | 結構與參照檢查已提供；逐一量測接點的 `join` 分析（不連續、交叉淡化、拍點相位）是待實作的方向，只回報數值 |

一首只交付聲音的作品三件都不需要；MV 通常只用第一件；互動作品三件都用。畫面、遊戲規則、狀態轉移與播放器 UI 留在作品或下游：Tactus 不知道「玩家剛才去過哪裡」，作品從演奏紀錄自己算。理由：五件互動作品與三支 MV 各自重寫同一套 `world.json`、速度常數、轉檔與接點檢查，《一卷帶子》改用地圖與 `export web` 後不再有自己的轉檔、雜湊與速度常數，Island 改用 `tactus serve` 後每步從 3.97 秒降到 1.38 秒，兩者聲音逐 byte 相同。

**尚未定案：**`join` 分析的介面；多份 receipt 組成的一場演奏是否需要 Tactus 的 session 格式；互動作品的 skill 是否獨立於 compose。

## 套件與工具邊界：自有算法與專門引擎

Tactus 以少數 base dependencies 涵蓋常用工作，其餘算法自有或由作品選裝。Base environment 包含 NumPy、SciPy、SoundFile、Numba、Pedalboard、pytimestretch、pyqmdsp 與 Mido，讓 production code 可以直接使用。Librosa 以 `tactus[librosa]` optional extra 提供，預設不安裝，內建分析也不呼叫它；作品以 `uv add "tactus[librosa]"` 選裝，開發比對用 `uv run --extra librosa pytest -m reference`；dev 額外安裝 pytest／Ruff。Global CLI 與作品環境分開，extra 不自動帶入新作品。Pyloudnorm 不在任何 dependency group；loudness 以保存的獨立參考答案、數學測試與 EBU 素材驗證。這是可用性上的產品選擇，不宣稱每個套件在數學上都不可取代，套件選定也不代表 runtime 已完成整合。

Python 要求 `>=3.12`，不預先限制未來的 minor version；實際可安裝範圍也受依賴套件支援影響。Checkout 的 `.python-version` 只選擇開發預設 3.12，作品可選擇 3.13 以共用其他套件的環境。Pedalboard 要求 `>=0.9.26`：此版包含 [Linux wheel CPU 相容性修正](https://github.com/spotify/pedalboard/releases/tag/v0.9.26)，以 AVX baseline 編譯，解決舊 cp313 wheel 在不支援 AVX-512 的 CPU 上崩潰的問題，因此不再用 Python 上限避開它。驗證方式見 [development](development.md)。

| 工作 | 目前做法 | 理由與邊界 |
| --- | --- | --- |
| Arrays 與 DSP | NumPy、SciPy | 支援普通 Python 的數值與訊號處理，保留 Agent 自寫算法的空間。 |
| 自有 stateful DSP | Python／Numba | 逐 sample／逐 frame 迴圈使用 private cached Numba kernel；驗證與 NumPy／SciPy 外層保留。Faust 可作為演算法參考，不要求另一套創作語言。 |
| Audio file I/O | SoundFile | 採用既有編解碼能力；Tactus 處理必要的資料與工具銜接。 |
| Loudness 與音訊分析 | 自有 NumPy／SciPy 算法 | 維護既有數值定義、API 與比對測試；librosa 選裝並可用於比對；pyloudnorm 的參考答案已固定為一般測試。 |
| 拍點與速度估計 | `pyqmdsp`（固定 Git revision `09b36d6`）+ `tactus.analysis.rhythm.beats` | 直接使用 qm-dsp，不依賴 Vamp。Tactus 只轉換 JSON 格式，空結果為 `bpm: null`；聲道平均、分幀、參數與時間換算由套件負責。只提供 beats，不提供 downbeats。 |
| 效果與 VST3 | Pedalboard + `tactus.fx` | `set_param` 依單位對到最近的合法值，`process_automated` 以分段處理 automation、tail 與延遲，`render_instrument` 以暖機消除起始雜訊並回傳 Tactus layout。曲線與音色由作品決定；盲聽中內建 reverb 勝過自寫。External sidechain 是已知缺口，不宣稱普遍 plugin 相容；部分 VST（如 OB-Xf）不可逐 sample 重現。 |
| Standard MIDI File 交換 | Mido | 例如 `sfizz_render` 需要 `.mid` 檔；沒有 MIDI 套件時 Agent 會各自手寫 SMF writer，因此預設安裝。Notes、controllers 與 transformations 仍由 Python 決定；Mido 不成為 composition model。 |
| Time stretch／pitch shift | `pytimestretch`（固定 Git revision `e43cc6d`，GPL-2.0-only） | 直接接受與回傳 NumPy，提供 Rubber Band 4.0（R3）與 Signalsmith 兩個 backend，由作品明確選擇；不自動限幅，headroom 由作品負責。不需要外部 `rubberband` 執行檔，也不另加 `tactus.stretch` 包裝。`extreme_stretch`（PaulStretch）是可選的創作處理：長度只是近似值，每個 process 內依呼叫順序固定亂數。此 revision 因 libpaulstretch 為 GPL-2.0-only，不能與 Pedalboard 的 GPLv3 一起對外發佈，目前只在內部使用。 |

**VST 延遲與連續處理：**`fx.process_automated` 先以靜音讓外掛穩定回報延遲並重設一次，之後連續處理所有區塊並補出緩衝中的音訊；起始延遲由 Pedalboard 補償。未修改的 LSP 1.2.35 Limiter 在 mono／stereo、44.1／48 kHz、兩個外掛串接與短區塊下，透明設定的輸出逐 sample 相同。Automation 若改變外掛回報的延遲會明確報錯；未回報的延遲與其他外掛需個別驗證。見 [延遲測試](../tests/test_fx_latency.py)。

**Marker warp：**`pytimestretch.time_warp` 接受 `(source_frame, output_frame)` 整數 pairs，包含 `(0, 0)` 與來源／輸出長度的終點。作品先在 `render` 外取得拍點，把採用的 map 固定成素材，再由一次連續的引擎呼叫完成伸縮。固定格線之間的小節線 map 由 `timing.warp_markers` 產生；引擎呼叫、移調與 backend 仍寫在作品裡，不提供 Tactus wrapper。見 [製作範例與驗證](../examples/beat-alignment/README.md)。

**內建 DSP：**`tactus.dsp` 以普通函式提供常用處理（`fx` 的同名入口轉向同一函式），VST host 與自訂 Python 路徑維持獨立可用。理由是減少跨作品重寫與重測：fresh-agent 實驗中 Agent 自寫 delay 時出現插值與 wet-only 錯誤。共同邊界如下，參數契約見 [DSP reference](../skills/references/dsp.md)：

- 所有函式保留 headroom、回傳新陣列、不修改輸入；控制曲線與參數切換不自動平滑。
- `gain`、`pan` 接受 scalar 或逐 frame 控制，`pan` 只把 mono 轉為等功率 stereo；`fade` 是整段素材的線性淡入淡出；`varispeed` 與 `fit_rms` 也由 `dsp` 實作；`fit_loudness` 是對 integrated LUFS 的對應版本，由作品在 `render` 內自行呼叫，預設只套用單一增益、超過 ceiling 就報錯，要限幅必須明確傳 `limit=True`；`run` 與 `export` 仍不做任何 normalize。
- 內建 DSP 中只有 `biquad` 提供跨呼叫 state：回傳 `(audio, state)`，state 由作品明確傳遞，固定參數下分塊與整段結果相同。
- 其餘效果（`duck`、`delay`、`lowpass`、`svf`、`ladder`、`saturate`、`crossover`、`crossfade_delay`、`spectral` 等）每次呼叫從零開始處理完整素材，不提供跨呼叫 state，不承諾分塊等價。`delay` 的時間變動會改變音高；`crossfade_delay` 以固定讀取位置的 crossfade 切換，可能干涉或抵消，不宣稱與 Faust `sdelay` 逐 sample 相同；`crossover` 相加幅頻平坦但相位改變；`saturate` 預設 8 倍 oversampling 以降低 aliasing，clip／fold 在 `oversample=1` 時與 SuperCollider `clip2`／`fold2` 數值相同。範例見 [dsp-components](../examples/dsp-components/README.md)，驗證見 [DSP 回歸測試](../tests/test_dsp_effects.py) 與 [響應與切換測試](../tests/test_dsp_components.py)。

**合成構件：**`tactus.synth` 提供產生聲音的構件（振盪器、必須指定 seed 的噪音、分段 envelope、modal 共振器、Karplus-Strong、顆粒），不是樂器或預設音色；完整樂器只以可改寫範例提供。盲聽中換成 SuperCollider／Csound／SignalFlow 沒有勝過 NumPy 基準，SC／Csound 還出現不報錯的失敗，而各作品又反覆手寫這些構件；因此不整合外部引擎，改依公開演算法自行實作（不讀取或複製其原始碼），以 Csound 作行為 oracle（`oracle` 測試標記，未安裝時略過）。與 oracle 的已知差異寫在契約中。`dsp.ladder`（非線性 Moog 模型）作為 `svf` 之外的另一種音色保留為創作選項，附 LGPL-2.1 聲明（[`LICENSE.csound`](../src/tactus/LICENSE.csound)）。見 [synth reference](../skills/references/synth.md)。

**Numba 與載入成本：**逐 sample 遞迴與顆粒疊加使用 private Numba kernel（`cache=True`、不開 fastmath）；固定 cutoff、oversampled `saturate` 與 `spectral` 維持 NumPy／SciPy 路徑，因為它們的成本不在 Python 迴圈。首次使用需要編譯，不能以穩態處理時間推論完整 CLI 啟動時間。`import tactus` 不立即載入 `tactus.analysis`，第一次存取或執行 `tactus analyze` 時才載入；`inputs` 只在需要重採樣時載入 `resample_poly`；使用 `dsp`／`synth` 的作品仍會在 worker 內載入 SciPy signal。見 [加速 reference](../skills/references/acceleration.md) 與 [Numba DSP 測試](../tests/test_dsp_numba.py)。

Audio handoff 明確處理 sample rate、channel layout、dtype 與 output encoding。改寫檔案的 sample-rate 標籤不等於 resampling；工具間的 layout 轉換必須保留 channel 身分。SoundFile 的 `(samples, channels)` layout 不自動決定所有工具或 Tactus 未來的內部表示。

自有 DSP 的有限實驗支持 Python／Numba 實作與 native／WASM 輸出的可行性，但尚未形成通用 export pipeline。驗證移植算法時要涵蓋時變參數、state 與 block boundaries；參考輸出本身也可能有錯，不能只因符合單一 golden 就宣稱正確。

**尚未定案：**外掛的動態／未回報延遲、external sidechain 與更廣泛的 plugin 相容性；自有 DSP 的可攜 state／buffer 約定與 native export 工具鏈；公開發佈前如何解決 pytimestretch（GPL-2.0-only）與 Pedalboard（GPLv3）的授權衝突。Rubber Band baseline 不代表所有素材與比例下的品質排名。只有真實需求暴露缺口時，才重新比較 Symusic／MusPy、Signalsmith 或自製 host；DawDreamer 保留為參考。

## 試聽：Offline、stateful、候選隔離

試聽採 offline 的「產生候選 → 聆聽或量測 → 比較 → 接受」循環。Stateful 表示處理具有記憶的效果器時保留正確上下文；候選隔離表示試聽不改正式 source，也不繼承其他候選的參數或 DSP state。這兩件事比單純加快 render 更直接影響比較是否可信。

試聽介面以明確宣告的參數為範圍。多個候選從同一份 immutable base 執行，receipt 辨識 base source、素材、候選參數、range／stems 與 runtime／plugin 身分。Range audition 需要正確的 pre-roll、latency 對齊與 tail 處理，不能只把輸出區間前的處理全部省略。

`run` 支援完整執行的參數候選，各次 process 與輸出目錄分開，Tactus 不修改 source。Receipt 記錄 Git `HEAD` 與未提交狀態、可還原實際 source 的 `source.patch`，以及 `render` 的執行時間。

**接受候選：**由作者或 Agent 自己完成：把參數值寫回 `render` 預設值、重跑，再用 Git commit。之前先比對候選 receipt 的 `git.commit` 與 `source_files` 是否仍是目前的 source；若 source 已經移動，聽者選中的版本已不存在，必須告知聽者，並在目前的 source 上重跑、取得重新確認。Tactus 不提供 `tactus accept` 之類的 guarded promotion，因為對照 probe 顯示清楚的指引就足以讓 fresh Agent 正確處理 source 移動。結構性的修改在 Git branch／worktree 上試，接受時用 Git 合併。

**區段試聽：**`tactus excerpt RUN_DIR --range START:END [--outputs a,b] --out NEW_DIR` 先驗證既有 run 的輸出，再剪下指定區段，不重新 render。即使作品用到每次 render 都不同的插件（如 OB-Xf），片段仍與聽者手上的那次候選 sample 完全一致；重新 render 再剪、或作品自行把 `render` 切成視窗，都會因外掛隨機性、處理狀態、loop 相位與整體 mix 處理而與成品不同，因此不提供 `run --range`。邊界硬切，不加 fade、pre-roll 或 tail。Excerpt 的 manifest 記錄 range、每個輸出的原始長度，以及來源 run 與其 manifest hash，不另外產生 receipt。公開名稱維持 `excerpt`，避免與 Python 內建 `slice` 混淆。

Excerpt 也能以 `--beat-grid beats.json --beats 9:17` 選擇已採用拍點：拍點編號從 1 開始、結尾不包含（9:17 是第 9 到第 17 個拍點之間的八拍），以成品起點為時間原點，不自動分析、推斷小節或外推缺失拍點；manifest 保存完整採用陣列、JSON 檔案 hash 與換算後的秒數／frames。自由擷取、重組或處理陣列由作品的 Python／NumPy 表達，需要 CLI 入口時使用自訂 export。只計算部分區段的加速版本，要等實測等待時間證明需要、並能證明輸出一致後再做。見 [Listening to part of a run](../skills/references/runtime.md#listening-to-part-of-a-run)。

**Git 與音檔的分工：**
- **Git 只保存 source**：`.py`、`uv.lock` 與 `sha256:` refs。
- **Render 的音檔不進 Git**：它們體積大、無法 diff 或 merge，而且屬於衍生物。
- **Run 輸出放在固定位置**：主 checkout 的 ignored `runs/`，或 repository 外。不要放在會被移除的 worktree 內。
- **聽者認可或聽過的版本要封存**：用 `tactus material add` 存入 pool。pool 與 manifest 使用同一個 SHA-256，commit 訊息引用的 hash 因此可以用 `material()` 取回。
- **Runtime 只唯讀地記錄 Git 狀態**：commit、branch、merge 由人或 Agent 直接使用 Git，Tactus 不包裝這些指令。
- **Pool 只在本機**：需要備份或分享時，再評估 Git LFS 或同步儲存，並且只放認可的版本。

**尚未定案：**state isolation 的實作、range／stem 的效率與延遲目標。Real-time transport 由 live input 或人類即時協作的實際需求再評估；cache 不是候選隔離成立的前提。

## 驗證與觀察：先定義技術契約，再提供判斷材料

Runtime 只檢查技術契約，分析只回報數值，音樂判斷留給 Agent 與人類。Runtime 檢查宣告的 shape、dtype、finite values、sample rate、時間關係與 output encoding 契約。音量是否需要限制等政策必須明確；mono 相容性、bass 是否置中或某個 reverb 比例，不能因 validator 的偏好而成為隱藏規則。

分析結果是音訊旁的可選觀察。短音訊可能無法量測 integrated LUFS，估計 tempo 也不代表作品採用該 BPM。用來做決定的分析（tempo、onset、切點、beat grid）在 `render` 之外執行一次，並把結果固定成素材或 source 常數：採用的結果本身就是被版本化的創作決定，分析套件升級也不會悄悄移動切點。跟隨訊號即時變化的處理（compressor、sidechain）屬於 DSP，留在 `render` 內。Tactus 提供可比較的 audio／stems／range，音樂判斷由 Agent 的聽覺工具與人類回饋完成。

**`tactus.analysis` 的結構：**分析按 category 組織，一個 category 是一個模組，以三層 `--help` 自我描述：`tactus analyze --help` 列出 category，`tactus analyze CATEGORY --help` 列出分析，`tactus analyze CATEGORY NAME --help` 給參數、欄位、單位與定義。每個分析是 `tactus.analysis.CATEGORIES[category].ANALYSES` 裡的一個函式，回傳 dict（可含 NumPy arrays）並帶 `revision` int；CLI 從這個結構自動產生子命令，沒有手寫的 per-analysis CLI。分析只回報數值，從不判斷通過或失敗，門檻由作品或 Agent 自己套。內建分析是可選工具，作品自己的 Python 與註冊分析仍是正式途徑。現有 category：

- `level`：`loudness`、`true_peak`、`sample_peak`、`rms`、`clipping`、`crest_factor`，以及 `momentary_loudness`、`short_term_loudness`、`loudness_range`、`rms_curve`、`peak_curve`、`crest_factor_curve`。
- `spectral`：`spectrum`、`band_levels`、`centroid`、`peaks`、`stft`、`bandwidth`、`rolloff`、`flatness`、`mel`、`chroma`、`mfcc`、`cqt`、`vqt`、`tuning`。
- `rhythm`：`beats`、`onset_strength`、`onsets`、`tempogram`。

數值定義、單位與限制由 [analysis 文件](analysis.md) 維護；以下只記錄設計邊界。

**分析資料的自我描述：**所有內建分析在既有回傳 dict 新增 `schema`，Python 與 CLI 共用同一份宣告；以獨立版本記錄資料形狀、軸與矩陣維度、單位、時間位置、實際視窗寬度和特殊值編碼。現有數值、欄位位置與分析 revision 保留，參數與座標由 schema 的欄位角色清單辨識，不要求下游猜測。時間以這次輸入起點為原點，不推定 render／原曲位置、小節或未宣告的語意。中心視窗、結尾視窗、補償後的 onset 格點與逐頻率 Q 視窗分別描述。`tactus.analysis.schema` 是內建與自訂分析共用的公開介面：用普通 dict 宣告資料，`attach` 複製 metadata 並檢查結構，`validate` 核對宣告與資料形狀，`coordinates` 解讀明確的 selector 與換算因子。檢查不代替演算法正確性驗證；自訂分析仍可不宣告，裸資料與未宣告的語意不會被猜測。既有 v1 格式保留，不另外建立跨工具套件或資料物件框架。基本分析圖片繼續提供；標記與跨工具診斷 workflow 由下游工具負責，schema 不依賴特定產品。契約及逐分析核對表見 [data schema](analysis.md#data-schema)。

**音量與動態：**演算法參考 pymixtool 的功能範圍，由 Tactus 以 NumPy／SciPy 實作，不依賴 pymixtool。Integrated LUFS 保留原 pyloudnorm 的濾波器與 gating 規則，LUFS 曲線使用 De Man K-weighting，兩者定義不同。各量不先混成 mono；零能量的 Python 表示依分析而異（例如 scalar RMS 為 `-inf`，level curves 為 `None`），CLI JSON 的非有限 scalar 轉為 null，確切編碼由 schema 宣告。LRA 依 EBU 定義，太短時回傳 null 或標示 provisional。Crest factor 不等於 PLR 或 LRA。見 [level curves](analysis.md#level-curves-and-loudness-range) 與 [level curves 測試](../tests/test_level_curves.py)。

**頻譜分布：**`bandwidth`／`rolloff`／`flatness` 沿用 Mel/MFCC 的時間格點；flatness 使用相對 floor，讓單純 gain 不改變數值；零 power frame 回傳 null。見 [dynamics and spectral distribution](analysis.md#dynamics-and-spectral-distribution) 與 [descriptor 測試](../tests/test_analysis_descriptors.py)。

**Onset 與特徵：**Mel、chroma、MFCC 與 onset 由 Tactus 以 NumPy／SciPy 維護，演算法對應 librosa 的非 NN 基準。`onset_strength`／`onsets` 採 SuperFlux 做法，以 `filterbank="mel" | "log"` 選擇前端（Mel 為預設，log 前端不是 CQT，兩者 strength 單位不同），不宣稱與原版 SuperFlux 應用程式完全相同；結果欄位維持 revision 1，Mel 事件時間不因前端選項改變。Onsets 是供選擇的候選點，不取代人工確認，也不提供 sample-accurate 切片。`chroma` 不推定調性／和弦，`mfcc` 不決定音色相似度。特徵在 Python 回傳 NumPy arrays，CLI 以既有 `--out` 附件機制保存，不另建檔案協定。聲道政策依 category：spectral 相加、rhythm 平均。見 [onsets and feature arrays](analysis.md#onsets-and-feature-arrays)、[owned analysis 測試](../tests/test_owned_analysis.py) 與 [SuperFlux 測試](../tests/test_superflux_frontends.py)。

**Q transforms、tempogram 與矩陣圖片：**CQT／VQT 是直接濾波器定義，不承諾與 librosa 逐值相同。Tempogram 保留半速／倍速候選，不推定唯一 BPM。DTW 不納入。`analysis.image(result, ...)` 從既有矩陣產生 SVG，不增加繪圖依賴，供所有矩陣分析共用；STFT 從 revision 2 起直接回傳陣列，取代舊的摘要與 Python `out=` 寫檔介面，CLI 需要 `--out`。不同分析的 dB 單位不同（Q 與 Mel 是特徵單位、非 dBFS），色階不能直接當成相同音量比較。Python 始終能取得完整矩陣。見 [STFT、Mel、Q transforms 與圖片](analysis.md#stft-mel-spectrogram-cqt-vqt-tempogram-and-images) 與 [Q-transform 測試](../tests/test_q_transforms.py)。

**拍點：**`tactus analyze rhythm beats FILE` 與 Python 使用同一函式，結果與直接呼叫 pyqmdsp 一致，並在驗證素材上接近原 Vamp 參考；這是特定素材的驗證，不保證所有音樂準確。有效音訊太短或全靜音時回傳空陣列與 `bpm: null`，不猜測小節或第一拍。採用後依 frozen-analysis 規則固定成素材或 source 常數。見 [拍點分析](analysis.md#beat-analysis)。

**沒有 `pitch` category：**現有 fundamental 與 f0 估計方法在未見素材上不可靠（帶有比 fundamental 更大聲低八度層的 SFZ bass 讓每種方法失準），在有更可靠的方法之前不提供。`spectral tuning` 是範圍窄得多的量測：整段訊號只回一個相對 A440 的偏差（cents）與集中程度，供 `chroma` 的 `tuning` 與重新調音使用；它不估計音高、調性或和弦。

**分析的計算路徑：**CQT／VQT 只在運算量大時改用 private cached Numba kernel，短輸入維持 SciPy FIR、不載入 compiler；STFT／Mel 保留原生 FFT 與 sparse projection，分批限制暫存記憶體。加速不更動分析的定義、時間格點或單位，呼叫結束恢復執行緒設定。見 [加速測試](../tests/test_analysis_acceleration.py)。

**作品自訂分析與交付：**常用或難實作的能力由 Tactus 內建；其他分析與交付由作品自己的 Python 定義，在 `pyproject.toml` 的 `[tool.tactus.analysis]`／`[tool.tactus.export]` 以 `module:function` 明確註冊，CLI 以 `tactus analyze category name`／`tactus export name` 呼叫，只 import 被選中的函式。函式仍可直接由 Python 使用；keyword-only 參數形成 typed flags，內建與自訂共用紀錄流程。紀錄包括輸入、callable、作品 source／config／lock、參數與實際環境，不追蹤任意外部 I/O，也不隔離 Python 副作用。見 [project commands](project-commands.md)。

**尚未定案：**共用 validation report 或 analysis report 的必要欄位與介面；stereo、DC 與 dropout 類分析是否提供；pitch（若日後有可行方法）併入 `tactus.analysis` 的形狀。以真實製作與修訂流程驗證需要，再決定哪些觀察值得標準化。
