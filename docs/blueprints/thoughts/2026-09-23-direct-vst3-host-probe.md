# Direct VST3 SDK host probe

本證據回到「Tactus 是否值得自建 VST3 host」的待決選擇；它不直接拍板換 backend。

使用 VST3 SDK `3.8.1_build_84`、LSP Sidechain Compressor Stereo `1.2.16`，在 Linux 以 48 kHz／128-frame block 建立一次性 C++ host + Python `ctypes` 入口。產品程式碼未改，沒有付費模型呼叫。

事前門檻：同一顆真實 compressor 必須完成參數讀寫、獨立 sidechain、跨 process state 還原、跨 block automation；少一項就是 partial。結果四項通過，但 automation 只驗證到 block 邊界，**未驗證 sample-accurate automation**。

參數可列出名稱、單位、normalized 值與顯示文字；設定後由新 process 讀回 `Sidechain type=1.0`、`Attack threshold=0.5`、`Ratio=0.5`。兩組 stereo 輸入分別接主聲音與控制聲音：有／無控制訊號的最大輸出差為 `0.07602`，主聲音為零時輸出為零。保存的 state 在新 Python process 還原後，與原輸出的最大逐 sample 差為 `0`。在第 `24064` 個 sample 所在 block 改 threshold，後段相對固定低 threshold 的最大差為 `0.07652`。三次重跑結果一致。

實作摩擦：`setProcessing(true)` 和 controller `getState` 回傳未實作，不能直接視為整顆 plugin 失敗；controller 參數改動必須先送到 processor 才能保存最新 component state；SDK 靜態庫沒有包含全部 host 範例所需原始檔；plugin 仍印出 `Non-existing client` 警告，來源未定位。這份 scratch host 只處理固定 stereo／128-frame／單顆 plugin，沒有 MIDI、sample-accurate automation、latency／tail、crash isolation、跨平台、任意 plugin 的相容性。

判斷：direct SDK 路線在這個受控範圍內可行；這次測到的是能力，不是「已能取代 Pedalboard」或工期。下一個決策應比較補 Pedalboard 原生 sidechain API 的成本，與擴大維護獨立 host 的成本。

Scratch evidence: `/tmp/tactus-direct-vst3-probe.vO02sr/` (`preregistration.md`, `host.cpp`, `probe.py`, `trial.py`, `build.sh`). Scratch 尚未封存，不能當成永久保存位置。
