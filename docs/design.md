# Tactus 當前設計

本文件保存我們目前認為合適的做法，以及尚未定案的設計邊界。內容獨立、自足，直接隨新決策更新；歷史實驗不需要同步修改。這些選擇包括待實作的方向，不代表現有 runtime 已經全部支援。

## 創作介面：Functional Python 與少量執行邊界

Production 以普通 Python modules、functions、NumPy arrays 與資料結構組成。函式清楚表達輸入、輸出與處理順序，盡量避免共享 mutation，使音樂片段、訊號處理與混音容易重用和修改。Agent 可以直接呼叫既有套件，也可以撰寫作品自己的 DSP。

我們目前採用的分解方式是：選擇素材身分、產生或處理音訊、組合完成的訊號、交付作品宣告的 outputs。這讓 runtime 能在必要處提供可靠執行，又不接管 Agent 的分組、角色、routing 與音樂算法。

第一版執行介面採用 Python 檔案中的同步 `render(*, ...)` 函式。具名 keyword-only 參數及其預設值供候選試聽使用；回傳 `{"sample_rate": 整數, "outputs": {名稱: NumPy陣列}}`。Tactus 負責呼叫、音訊驗證與寫檔。這個約定讓同一個工具能執行不同作品，作品內部的結構仍由 Agent 決定。

Outputs 共用一個 sample rate，可有不同長度；可以是 mix、stems 或 clips，沒有必要的 output 名稱。交付格式先採用非空 mono／stereo、有限且介於 [-1, 1] 的實數音訊，經 float32 轉成 PCM24 WAV；不自動混音、正規化或重採樣。這是輸出邊界的約定，並不限制中間 DSP 的 headroom。

舊版 `build(project)`、`Project`／`Track`、arrangement 格式及其 CLI 已退役，不保留相容層。新版以 `render()` 和 `run` 為執行介面；結果可直接從回傳值、manifest 與 receipt 讀取，沒有另設 `inspect` 的需求。

**尚未定案：**targeted rendering 與更廣的交付型別。`select`、`render_audio`、`mix`、`render_all` 是實驗使用過的語彙，不是 public API。

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

作者仍決定 automation 的數值、邊界、插值方式與用途；helper 只負責正確展開。`place`、`repeat`、`scale_time`、`section_envelope` 等名稱目前用來描述候選能力。

**尚未定案：**seconds／samples placement 與總長度的正式介面、rounding 規則，以及哪些 tempo-map／local-clock 計算值得由 Tactus 共用。漸變 tempo、rubato、巢狀 clock 與跨 tempo 變化的事件長度仍需驗證。新版執行入口不要求 BPM／bars；尚未建立完整 clock class 系統。

## Pattern：選用的局部規律工具

Pattern functions 用於可命名、組合與重用的規律，例如 cycle、phase、Euclidean distribution、polymeter、rotation、reverse 與週期性 transformation。一次性的 fill、section 選擇與音樂例外留在 Python；例外本身形成作品要保留的週期時，才值得用 Pattern 表達。

目前方向是將局部 Pattern 展開成普通事件，再與手寫 Python 或其他 generator 產生的事件使用同樣的時間與 placement 能力。下游不必因事件來源不同而採用不同編排模型。這能保留規律的意義，並減少作品反覆手寫 cycle／phase 計算。

**尚未定案：**事件資料型別、Pattern 的正式函式集合與共用範圍。`realize(...) -> tuple[Event, ...]` 是已測過的候選邊界；它不要求整首作品使用 Event schema。Lazy／infinite Pattern、probability、seed 與 incremental realization 尚未收斂，也沒有採用 string mini-notation 的需求。

## 素材：版本化身分與內容儲存分開

作品保存固定的素材身分，runtime 依身分取得內容。素材 bytes 可以放在 Git 外的 content-addressed store；更換內容必須改變作品中被版本化的參照。素材遺失應回報無法取得，不能悄悄換成同一路徑下的新檔案。

匯入時可以從一般檔案路徑開始，但持久的創作依據應固定到內容。只在 build 時對可變路徑算 hash 並寫入 generated receipt，仍無法防止同一個 source revision 讀到不同素材。

目前做法：作品在 Python 中以具名常數寫入 inline digest，並用 `material("sha256:…")` 取得驗證過的檔案路徑。`tactus material add FILE...` 把檔案匯入本機 pool（`$TACTUS_POOL`，預設 `~/.local/share/tactus/pool`），並印出對應的 ref。身分是原始檔 bytes 的 SHA-256。解碼、擷取區段、sample rate 與 headroom 由作品自行處理。缺檔與內容損壞分別回報。Pool 的目錄結構與 tactus-daw 相容。外部執行檔與 native library 由作品在使用處以 `tool(...)` 宣告，receipt 記錄其路徑與 hash；目前只記錄，不以 hash 鎖定。

**尚未定案：**整個資料夾的素材身分（例如 SFZ 樂器與其 samples）、解碼後音訊的身分、import gain／headroom 政策，以及 processor 身分不符時是否拒絕執行。

## 執行與重現：先可靠產出，再按需要重用計算

Python 執行後產生可保存的音訊材料與宣告 outputs；編排快照、receipt 與其他執行資料都是衍生物。Receipt 用來辨識這次執行的 source、素材、參數、dependencies 與 runtime／processor 身分，讓結果能追溯到輸入。

第一版已提供 `tactus.run(source, out=..., params=...)` 與 `tactus run SOURCE --out NEW_DIRECTORY --params JSON`。每次呼叫使用新的 Python process，避開既有 bytecode cache，從 entry 所在資料夾解析 sibling imports 與相對素材路徑。作品的 log 走 stderr，CLI stdout 只交付一份 JSON 結果。已存在的輸出位置會被拒絕；可處理的執行失敗會清除該次新建的輸出。

Functional run 的 `manifest.json` 保存 sample rate 與具名音訊的內容 hash、frames、channels；WAV 由 OutputStore 直接寫在 `--out` 底下，檔名為 `<name>-<sha256 前 8 碼>.wav`，manifest 記錄完整 sha256。Manifest 最後發布，作為完成標記。`receipt.json`（format_version 2）保存以下內容：
- 實際參數（含預設值）
- entry 目錄下 Python source 的 hash
- 從 entry 目錄往上找到的最近一個 `uv.lock` 的路徑與 hash
- 解析過的素材 refs
- 宣告的 tools
- 實際 import 的第三方套件版本
- Python／Tactus／NumPy／SoundFile 版本

執行中觀察到 source 或該 lock 改變時會失敗。未以 `material()` 取得的檔案、未宣告的執行檔、網路存取與隨機性仍不在紀錄範圍內。Runtime 不隔離任意 Python 的外部副作用。

Agent 取得這些契約與 functional 寫作紀律的來源，是 repository 內的 `skills/tactus-authoring/SKILL.md`。測試會檢查它列出每個 manifest、receipt 與錯誤欄位。

已保存的 WAV 可以直接播放，也可透過 OutputStore 檢查內容 hash 與音訊 metadata。Source rebuild 則重新執行 Python，還受到 randomness、外部輸入、套件與 processor state 影響。保存結果與重新製作的保證要分開表達。

先確保完整執行與 replay 正確；selective caching、checkpoint 與更豐富的 graph metadata 等實際 consumer 證明需求後再加入。Graph 可以支援執行與檢查，但目前沒有把它擴張成全曲創作模型的計畫。

**尚未定案：**source rebuild 的完整依賴與隨機性契約、超出第一版 receipt 的歸因範圍，以及安全重用計算所需的 dependency tracking。不能從素材 hash 相同推定所有重新執行都可重現。

## 套件與工具邊界：直接採用既有能力

Base environment 選用 NumPy、SciPy、SoundFile、pyloudnorm 與 librosa，讓 production code 可以直接使用。這是可用性上的產品選擇，不宣稱每個套件在數學上都不可取代。套件選定也不代表正式 runtime 已完成整合。

| 工作 | 目前做法 | 理由與邊界 |
| --- | --- | --- |
| Arrays 與 DSP | NumPy、SciPy | 支援普通 Python 的數值與訊號處理，保留 Agent 自寫算法的空間。 |
| 自有 stateful DSP | 有需要時採用 Python／Numba | 保留 Python authoring，以 Faust 演算法作為參考與比對；不要求另一套創作語言。 |
| Audio file I/O | SoundFile | 採用既有編解碼能力；Tactus 處理必要的資料與工具銜接。 |
| Loudness 與音訊分析 | pyloudnorm、librosa | 提供現成量測與分析，避免每份作品重做；不因安裝套件而引入強制分析 schema。 |
| 效果與 VST3 | Pedalboard + 必要的小 helper | 先整合已有 host，補參數、assets、channels 與 scheduling 邊界。External sidechain 是已知缺口，不宣稱普遍 plugin 相容。 |
| Standard MIDI File 交換 | 有檔案交換需求時用 Mido | Notes、controllers 與 transformations 仍由 Python 決定；Mido 不成為 universal runtime dependency 或 composition model。 |
| Time stretch | Rubber Band 作為 baseline | 固定比例 stretching 目前可用作品內函式呼叫 backend，沒有足夠理由先加 core stretch helper。 |

Audio handoff 要明確處理 sample rate、channel layout、dtype 與 output encoding。改寫檔案的 sample-rate 標籤不等於 resampling；工具間的 layout 轉換也必須保留 channel 身分。SoundFile 使用的 `(samples, channels)` layout 不自動決定所有工具或 Tactus 未來的內部表示。

自有 DSP 的有限實驗支持 Python／Numba 實作與 native／WASM 輸出的可行性，但尚未形成產品的通用 export pipeline。驗證移植算法時要涵蓋時變參數、state 與 block boundaries；參考輸出本身也可能有錯，不能只因符合單一 golden 就宣稱正確。

**尚未定案：**Rubber Band 的正式 Python binding、部署方式與 R2／R3 預設；marker warp 的產品介面；效果鏈的 latency、tail、automation 與具體 plugin 相容性；自有 DSP 的可攜 state／buffer 約定與 native export 工具鏈。Rubber Band baseline 不代表所有素材與比例下的品質排名已定案。只有真實需求暴露缺口時，才重新比較 Symusic／MusPy、Signalsmith 或自製 host；DawDreamer 保留為參考。

## 試聽：Offline、stateful、候選隔離

先提供 offline 的「產生候選 → 聆聽或量測 → 比較 → 接受」循環。Stateful 表示處理具有記憶的效果器時保留正確上下文；候選隔離表示試聽不改正式 source，也不繼承其他候選的參數或 DSP state。這兩件事都比單純加快 render 更直接影響比較是否可信。

第一個試聽介面以明確宣告的參數為範圍。多個候選從同一份 immutable base 執行，receipt 辨識 base source、素材、候選參數、range／stems 與 runtime／plugin 身分。Range audition 需要正確的 pre-roll、latency 對齊與 tail 處理，不能只把輸出區間前的處理全部省略。

目前 `run` 支援完整執行的參數候選，各次 process 與輸出目錄分開，Tactus 不修改 source。每次執行的 receipt 會記錄：
- Git `HEAD` 與未提交狀態；
- 可還原實際 source 的 `source.patch`；
- `render` 的執行時間。

接受候選由作者或 Agent 自己完成：把參數值寫回 `render` 預設值、重跑，再用 Git commit。在那之前，先比對候選 receipt 的 `git.commit` 與 `source_files` 是否仍是目前的 source。若 source 已經移動，聽者選中的版本已不存在，必須告知聽者，並在目前的 source 上重跑、取得重新確認。尚未提供 range audition。

Git 與音檔的分工如下：
- **Git 只保存 source**：`.py`、`uv.lock` 與 `sha256:` refs。
- **Render 的音檔不進 Git**：它們體積大、無法 diff 或 merge，而且屬於衍生物。
- **Run 輸出放在固定位置**：主 checkout 的 ignored `runs/`，或 repository 外。不要放在會被移除的 worktree 內。
- **聽者認可或聽過的版本要封存**：用 `tactus material add` 存入 pool。pool 與 manifest 使用同一個 SHA-256，commit 訊息引用的 hash 因此可以用 `material()` 取回。
- **Runtime 只唯讀地記錄 Git 狀態**：commit、branch、merge 由人或 Agent 直接使用 Git，Tactus 不包裝這些指令。
- **Pool 只在本機**：需要備份或分享時，再評估 Git LFS 或同步儲存，並且只放認可的版本。

曾實作 guarded promotion（`tactus accept`：base 檢查、改寫 `render` 預設值、重跑驗證）。A/B probe 顯示，清楚的指引就能讓 fresh Agents 正確處理 source 移動的情況，因此這個功能暫存在 `shelved/tactus-accept` 分支，等出現實際錯誤時再啟用。結構性的修改在 Git branch／worktree 上試，接受時用 Git 合併。

**尚未定案：**正式 audition／promotion API、state isolation 的實作、range／stem 的效率與延遲目標。Real-time transport 由 live input 或人類即時協作的實際需求再評估；cache 不是候選隔離成立的前提。

## 驗證與觀察：先定義技術契約，再提供判斷材料

Runtime 檢查宣告的 shape、dtype、finite values、sample rate、時間關係與 output encoding 契約。音量是否需要限制等政策必須明確；mono 相容性、bass 是否置中或某個 reverb 比例，不能因 validator 的偏好而成為隱藏規則。

分析結果作為音訊旁的可選觀察交給 Agent。短音訊可能無法量測 integrated LUFS，估計 tempo 也不代表作品採用該 BPM。用來做決定的分析（tempo、onset、切點、beat grid）在 `render` 之外執行一次，並把結果固定成素材或 source 常數。這樣做有兩個效果：採用的結果本身就是被版本化的創作決定；分析套件升級也不會悄悄移動切點。跟隨訊號即時變化的處理（compressor、sidechain）屬於 DSP，仍留在 `render` 內。Tactus 提供可比較的 audio／stems／range，音樂判斷由 Agent 的聽覺工具與人類回饋完成。

**尚未定案：**共用 validation report 或 analysis report 的必要欄位與介面。以真實製作與修訂流程驗證需要，再決定哪些觀察值得標準化。
