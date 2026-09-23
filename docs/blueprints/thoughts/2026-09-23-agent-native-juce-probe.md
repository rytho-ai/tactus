# Agent-native JUCE capability probe

本證據回到 Tactus「Agent 能否直接維護 JUCE C++」的待決問題；它不直接決定 host 選型。

受測者是本次互動 Agent，環境為 JUCE 9.0.2／Linux。事前固定兩題：JUCE DSP compressor 必須呈現壓縮且不受 block 切法影響；JUCE host 必須載入 Dexed VST3、送 MIDI、保存 state 並在新 process 還原。兩題皆通過且各自首次編譯、首次功能測試就通過，依預定規則屬於「在此範圍表現強」。後續各補強一次驗證，並非修正功能失敗。

DSP 題使用 `juce::dsp::Compressor<float>`，低 threshold 的 RMS 為 `0.03195`，高 threshold 為 `0.35341`；完整 8192 samples 的單塊與不規則分塊輸出最大差為 `0`。Host 題用 JUCE headless hosting API 載入 Dexed；送 MIDI 的 RMS 為 `0.0403061`，不送 MIDI 的負對照約 `1.0e-8`；2238 個參數可枚舉，`Cutoff=0.42` 經 8360-byte state 保存後，在新 process 讀回仍為 `0.42`，輸出 RMS 相同。produce／restore 重跑三輪一致。

限制：Agent 事前已接觸上一輪 JUCE binding 的建置方式與基本 host API，因此不是無範例冷啟動測試；只測一個內建 DSP 類別與一顆免費 VST3 instrument。沒有測 external sidechain、sample-accurate automation、任意 plugin、crash recovery、多平台或 Python binding；相同 RMS 不代表逐 sample 音訊完全一致。這不能外推成所有 Agent 都會 JUCE，也不能證明自建 host 的長期維護成本低。

判斷：Agent 可以可靠完成這兩個有邊界的 native JUCE 任務；要支持 Tactus 以 JUCE 自建完整 host，仍需測更難的相容性與維護任務。產品程式碼未改，沒有付費模型 fan-out。一次性程式與事前規則保留在 `/tmp/tactus-juce-agent-probe.MyxiBp/`，未封存。
