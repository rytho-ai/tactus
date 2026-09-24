# Tactus 的產品責任

> 2026-09-24 · **Status: in force** · Tactus 的方向是通用、Python-first 的 Agent 音樂製作 runtime。Agent 決定音樂並運用自己的聽覺工具；Tactus 負責讓製作過程可靠執行、比較與追溯。這是產品定位，不宣稱目前的 prototype 已涵蓋所有音樂工作流。

## 通用創作媒介，不是強制的 DAW 模型

Ordinary Python、NumPy 函式與資料結構是一等公民。Agent 可以自行表達合成、取樣、MIDI、DSP、編曲與特殊做法；Tactus 不要求作品先轉成 Track／Bus／Session、Pattern 或一份可手動編輯的 Arrangement Graph。現有 [functional authoring 結論](2026-09-21-functional-audio-authoring-core.md) 與 [Pattern 邊界](2026-09-22-python-pattern-authoring-boundary.md) 分別記錄了這些選擇的實驗依據。取樣是目前研究 affordance 的案例，不是產品只服務的曲風或技法。

## 創作與聽覺由 Agent 負責，production mechanics 由 Tactus 負責

Agent 選素材、寫音樂邏輯、決定效果與參數，並可用 audio LLM、Phonon、數值分析或人類回饋判斷作品。Tactus 交付可比較的 audio／stems／range audition、明確的時間與素材身分、驗證結果及來源追溯；它不內建一個判斷哪版「比較有 groove」的音樂審美者。[Transactional audition](2026-09-23-transactional-audition.md) 記錄候選版本不污染正式 source 的設計，但正式 runtime 尚未完成這項契約。

Tactus 可以讓 Agent 看見 chopping、重觸發、切片重排等創作手法；這些 affordance 是可選的創作語彙，不是必須呼叫的 API。Agent 仍可直接用 Python 實作，或選用能降低真實摩擦的 helper。[盲聽紀錄](2026-09-24-sampling-affordance-fresh-agent-probe.md) 給了方向性訊號，未證明提示必然有效，也未證明 `chop` helper 是必要的。

## Source of truth 與目前的證據邊界

Production source、被版本化的素材身分與相依套件宣告承載可接受的創作決策；Git 記錄修訂。編譯後的 arrangement、material、receipt、cache 與 audition audio 是衍生結果，不是第二份要與 code 同步的作品。[素材身分 thought](2026-09-21-material-identity-in-source.md) 說明了這項不變條件及目前尚未實作的 pinned-identity authoring form。[時間 thought](2026-09-23-optional-clock-temporal-abstraction.md) 則區分可選的時間工具與非必需的全曲 BPM。

目前 Tactus 已能從一次 build 的 compiled materials 重播並輸出 mix／stems；它不保證任意 Python source 在不同環境重新執行會產生相同聲音。正式的 audition、效果器整合、free-time placement 與完整的素材身分固定仍是產品工作，不能從這份定位推定為已交付功能。
