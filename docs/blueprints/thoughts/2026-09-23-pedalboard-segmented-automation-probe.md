# Pedalboard segmented automation probe

本證據回到 Tactus 是否需要改用可傳 VST3 sample-offset automation 的 host；它不直接改變目前選型。

Linux／Python 3.12／Pedalboard 0.9.25／48 kHz。一次性 VST3 gain fixture 依參數事件的 sample offset 精確改變輸出，SDK validator 以 exit 0 完成，但提示 fixture 沒有 bypass 參數及一次 silence flag 不正確；產品程式碼未改，沒有付費模型呼叫。

在第 12345 個 sample 把 gain 從 `0.25` 改到 `0.8`，用同一顆 plugin 分兩次 `process(..., reset=False)`，輸出長度正確，與預期階梯的最大誤差為 `0`。對 2 Hz 曲線，10 ms 控制點（100 次呼叫）的最大連續曲線誤差為 `0.05003`，對指定的階梯值誤差約 `2.6e-8`，1 秒音訊處理時間中位數 `0.00059 s`；1 ms（1000 次呼叫）則為 `0.00492`、約 `2.9e-8`、`0.00482 s`。這些時間不含載入 plugin。

原定 mda Ambience 脈衝試驗沒有可測的尾音，因此 state continuity 未判定，不能把其兩次輸出相同算成成功。事前另立補充規則後改測 mda Delay：切在第 12345 和 32111 個 sample，尾音最大值 `0.38577`，分段與一次處理的最大逐 sample 差為 `0`。另作真實 mda Delay 參數曲線診斷：10 ms／1 ms 控制點的處理時間中位數分別約 `0.00065 s`／`0.00457 s`，輸出有限且非靜音。

判斷：原定三項試驗中兩項通過、一項因測試對象無尾音而未判定；補充試驗支持「目前可先用 Pedalboard + 分段排程 helper」處理離散切換及控制率曲線。**這不是 VST3 事件佇列內的 sample-accurate automation**；精確切點是靠拆開音訊並在兩次呼叫間改參數。重度 plugin、多顆 effect、商用 VST、latency／tail 及極快速曲線尚未驗證。

一次性資料保留在 `/tmp/tactus-pedalboard-automation.QbJWJX/` (`preregistration.md`, `followup-preregistration.md`, `automation_fixture.cpp`, `run_probe.py`, `real_plugin_diagnostic.py`)，未封存。
