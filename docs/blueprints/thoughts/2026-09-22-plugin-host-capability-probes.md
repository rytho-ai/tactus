# Plugin host 三項能力驗證

## 結論

Pedalboard + helper 仍適合作為 Tactus 的主要 effect／VST 路徑，但不能宣稱它已涵蓋 external sidechain。

本輪找到三種不同層次的問題：

- **參數操作：** Pedalboard 已能正確處理測試中的實際單位與選項，不需要為此自建 binding。另有一個連續／離散參數標記錯誤，測試中的 helper 可以修正。
- **跨 session 還原：** 三種 host 都能還原這次的 sampler 設定與聲音；素材遺失時，三種都可能無例外地輸出靜音。需要的是明確的素材依賴檢查，換成 JUCE binding 並沒有自動解決。
- **External sidechain：** Pedalboard 的公開處理路徑碰到實際限制；薄 JUCE binding 成功。這支持補足特定 native bus API，但仍不足以直接決定自行維護整個 host。

本報告提供下一個選型決策的證據，不自動改變已拍板的主要 backend。

## 測試範圍與方法

比較 Pedalboard 0.9.25、DawDreamer 0.9.0，以及本輪擴充的 JUCE 9.0.2 一次性 binding。環境為 Linux、48 kHz、128-sample block。

使用：

- 真實的 mda Ambience VST3。
- 本機 DrumCraker 1.3.4 sampler，搭配自行產生的合法 WAV、kit XML 與 MIDI map。
- 可檢查 DSP 與參數定義的受控 VST3 fixture。它包含 nonlinear frequency、dB gain、選項參數，以及獨立主輸入／sidechain 輸入。

事前固定判定標準。主要條件重複三次；聲音最大逐 sample 誤差容許值為 `2e-5`，normalized 參數誤差為 `1e-5`。失敗紀錄保留，補充測試另列，沒有事後放寬門檻。

這不是 live Agent 寫 code 的評測，也不是商用 plugin 相容性普查。

## Probe 1：Agent 能否依實際意義操作參數？

測試要求：

- frequency 設為 `1 kHz`，不是猜一個 0–1 的數字。
- gain 設為 `-6 dB`。
- mode 設為 `Invert`。
- 處理音訊、保存、重新載入，確認數值與聲音。

另以 mda Ambience 的 Output `-6 dB`、Mix `0` 驗證真實 plugin。

### 結果

| 路徑 | 設定與聲音 | 還原 |
|---|---|---|
| Pedalboard 公開 API | 全部指定目標通過；音訊誤差 0 | 通過 |
| DawDreamer + 初版顯示值搜尋 helper | fixture 通過；mda 未達嚴格門檻 | 兩顆測試 plugin 的 `load_state` 拋出無 editor 例外，即使聲音已還原 |
| DawDreamer + 修正版 helper | 補測的數值目標通過；mda 音訊誤差 0 | 不因此消除上述載入例外 |
| 薄 JUCE binding | 全部指定目標通過；音訊誤差 0 | 通過 |

DawDreamer 初版 helper 找到的是「顯示為 -6.00」區間的邊界，不是中心。修正搜尋方法後通過，這是 helper 問題，不是 DSP 能力不足；它也不代表所有 plugin 的文字轉換都可以如此搜尋。

另發現 Pedalboard 將 fixture 的連續 Gain、Frequency 回報為 `is_discrete=True`，但 `num_steps` 仍是連續參數使用的 `2147483647`。依這個值推導、並保留原始欄位供檢查的 helper，在 fixture 與 mda 的 21 個檢查全部通過。這是有範圍的修正，不是完整 metadata 已被證明可靠。

**判斷：這組結果支持參數 helper／針對性修正，不支持為一般參數操作另建 host。**

## Probe 2：新 process 能否還原並繼續創作？

使用 DrumCraker 載入外部 sample，將人性化隨機變化關掉。初始音量 `-6 dB`，保存後關閉 producer process；新 process 還原，再只把音量改為 `-12 dB`。

檢查其他參數不變、原聲音可重現，以及修改後的音量比例正確。初始 kit 透過 plugin 自己的 state 格式建立；這不是通用的「載入任意 sampler 素材」API。

### 素材仍存在

三種 host 各三輪全部成功：

- 還原前後音訊誤差：`0`。
- 修改音量後，與預期音量比例的最大誤差：`1.49e-8`。
- 其餘受檢參數變動：`0`。

DrumCraker 的 DawDreamer native state 路徑本輪成功，不能把前述無 editor plugin 的失敗擴大成「DawDreamer 都不能還原」。

另測明確初始設定重建，以及 DawDreamer engine serialization 對照。包含缺檔條件，共完成 48 個 child-process 工作。

### 素材遺失

分別暫時移走 scratch sample 與 kit XML，以新 process、獨立 cache 測試：

- 三種 host、兩種缺檔、各三次，共 **18 次全部輸出靜音**。
- 沒有 Python 例外，也沒有擷取到 stdout／stderr 警告。
- 已知的明確素材清單，**18 次全部找出缺檔**。

所有暫時移走的測試素材都已還原，hash 核對一致。

**判斷：保存 plugin state 不等於保存整個 production 的依賴。Tactus 應明確記錄素材並在還原前檢查；這次沒有證據顯示自建 binding 能自動發現 opaque state 裡的全部依賴。**

## Probe 3：真正獨立的 external sidechain

建立 stereo 主聲音與 stereo 控制聲音，讓控制聲音只影響衰減、不進入輸出。

四種條件：有控制訊號、控制訊號為零、主聲音為零、交換兩個輸入。另檢查關閉 aux 與不支援的 channel layout。

這顆 fixture 是有精確公式的 gain ducker，**不是具 attack／release state 的完整 compressor**。因此結果證明的是 VST bus routing，不是所有 compressor 的聲音與相容性。

### 結果

| 條件 | Pedalboard | DawDreamer | 薄 JUCE binding |
|---|---|---|---|
| sidechain 預設關閉，需要後來啟用 | 無可用公開輸入路徑 | 本輪失敗：額外訊號未接入 | 通過 |
| sidechain 預設已開啟 | 同樣失敗 | 通過 | 通過 |
| 三聲道不支援配置 | 明確拒絕 | 警告後仍產生兩聲道輸出 | 明確拒絕 |

Pedalboard 將合併的四聲道資料視為四聲道主輸入／輸出並拒絕；只傳主聲音則沒有 sidechain 效果，不能算替代方案。

DawDreamer 在預設關閉的版本，`enable_all_buses()` 回傳成功，但公開 channel count 仍是 2，graph 報告略過額外連線。預設開啟版本的四種音訊條件各重複三次，全部通過。

薄 binding 在兩種版本都通過；最大聲音誤差 `1.19e-7`，主聲音為零時輸出也為零。

### 失敗與補測紀錄

原始 fixture 在 DawDreamer 預設關閉的條件下發生 native crash。追蹤指向 fixture DSP；加入空指標防護後，觀察到啟用中的 aux 收到空的 sample pointers，且聲音缺少 sidechain 效果。因此沒有把 crash 直接算成 DawDreamer 的一般穩定性缺陷。

原始、防護版、預設開啟版 fixture 均通過 SDK validator：各 `47 passed / 0 failed`。這增加 fixture 的基本可信度，不代表完整 plugin 規格與所有 host 行為都已驗證。

**判斷：這是具體的 native bus 能力缺口；在已測 Pedalboard 公開 API 上，純 Python 資料整理 helper 不足以完成。**

## 對 Tactus 的影響

維持 Pedalboard + helper 為主要路徑，但明確標記 external sidechain 尚未涵蓋。

現在有理由評估「補 Pedalboard 的 native bus API」或「很小的 JUCE extension」。還沒有量測兩者的維護成本，也沒有測真實目標 compressor，因此不直接升級成自行維護完整 host 的決策。

DawDreamer 繼續作為 reference；本輪證明它確實能處理一種 sidechain 配置，也暴露另一種配置的限制。

已支持的 helper 責任包括參數轉換與驗證、明確素材清單、缺檔拒絕、routing 前的 channel 檢查。創作上的 plugin 選擇、參數、曲線與 routing 意圖仍由 Agent 決定。

尚未驗證：商用 compressor、stateful sidechain DSP、latency compensation、transport、完整 DSP checkpoint、跨平台相容性，以及 Agent 使用這些介面的長期可靠度。

## 證據位置

本輪 scratch：`/tmp/tactus-host-capabilities.LDftKn/`。

主要檔案：`preregistration.md`、`contracts.md`、`results13-isolated.json`、`results2.json`、`side-variant-logs.json`、`metadata-helper-results.json`、`dd-helper-supplement.json`、`summary.json`。

三組 frozen manifest 核對無變更。產品程式碼未修改，沒有付費 Agent 評測呼叫。Scratch 證據尚未封存，不能當成永久保存位置。
