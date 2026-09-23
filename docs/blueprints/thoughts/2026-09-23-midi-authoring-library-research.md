# MIDI authoring libraries: MusPy and adjacent options

> 2026-09-23 · 官方文件／原始碼查證；這是候選工具的能力盤點，不是 Agent 實作比較，也不是 Tactus API 決策。

## 問題

前兩輪比較了直接編輯 Mido messages，和在 Python 裡維護 task-local 音符事件、最後用 Mido 輸出。是否已有現成 library 能提供更好編輯的 note-level model，同時保留 Tactus 需要的 tempo、踏板與 pitch bend？這裡檢查 MusPy、pretty_midi、Symusic；尚未讓 Agent 實際完成同一題。

## MusPy：musical-time note model，加上研究用工具箱

MusPy 的核心 `Music` 具有 `resolution`、`tempos`、`time_signatures`、`tracks`；每個 `Track` 有 `notes`，`Note` 直接存開始時間、長度、音高和力度，不必自行配對 note-on/off。時間是 metrical steps；讀 MIDI 時 `resolution` 取該檔 PPQ。`Note`／`Track` 支援 `transpose()`、`adjust_time()`、`clip()` 等操作。它也提供 symbolic music 的表示法轉換、資料集與分析功能。[Music model](https://muspy.readthedocs.io/en/latest/classes/music.html) · [Track / transformations](https://muspy.readthedocs.io/en/latest/classes/track.html) · [Timing](https://muspy.readthedocs.io/en/latest/timing.html) · [Project README](https://github.com/salu133445/muspy)

`read_midi()`／`write_midi()` 可選 Mido 或 pretty_midi backend，預設 Mido；`write_midi()` 並不是「不需要 Mido」的路線，而是在 MusPy model 之下使用 Mido 作輸出。MusPy 也有 JSON/YAML 保存與 MusicXML 等格式接口。[MIDI I/O](https://muspy.readthedocs.io/en/latest/io/midi.html) · [Output interfaces](https://muspy.readthedocs.io/en/stable/doc/outputs.html)

對完整 MIDI 表演有一個必須實測／注意的邊界：官方 `from_mido()` 原始碼把 `control_change` 收進 `Track.annotations` 的 `control_change` group，但 `to_mido_track()` 只輸出 track name、program change 與 notes，沒有遍歷 `track.annotations`；`from_mido()` 的分支也沒有處理 pitchwheel。**從這段原始碼推得**，以預設 Mido backend 做 `MIDI → MusPy → MIDI`，不能假定 CC64 踏板或 pitch bend 無損保留。pretty_midi backend 的 `from_pretty_midi_instrument()`／`to_pretty_midi_instrument()` 同樣只映射 notes，不能視為補救。[MusPy MIDI input source](https://muspy.readthedocs.io/en/latest/_modules/muspy/inputs/midi.html) · [MusPy MIDI output source](https://muspy.readthedocs.io/en/latest/_modules/muspy/outputs/midi.html)

另一個 backend 差異：MusPy 官方標明 `to_pretty_midi()` 不支援輸出 tempo changes，因此變速作品若要檢查 MusPy 輸出，須明確指定或確認 backend；Mido backend 的原始碼則會寫出 `music.tempos`。[MusPy pretty_midi interface](https://muspy.readthedocs.io/en/latest/io/pretty_midi.html) · [Mido output source](https://muspy.readthedocs.io/en/latest/_modules/muspy/outputs/midi.html)

## pretty_midi：以秒為編輯單位的 note / CC / bend model

`PrettyMIDI` 裝 `Instrument`；後者分別有 `notes`、`control_changes`、`pitch_bends`。`Note(start, end)` 的時間是絕對秒數；CC 與 bend 也以秒數表示。可以直接改這些物件再 `write()`；官方範例展示從零生成音符、修改 pitch，並可取 piano roll 或合成簡單波形。對以秒／audio 為主的修改很直接，但它的表演物件不是以 bar/beat 或 tick 為原生座標。[pretty_midi overview](https://craffel.github.io/pretty-midi/) · [Instrument API](https://craffel.github.io/pretty-midi/instrument.html) · [Event containers](https://craffel.github.io/pretty-midi/containers.html)

## Symusic：tick／quarter／second 可轉換的 note / CC / bend model

`Score` 有全域 tempo、meter、key、markers 及 tracks；`Track` 有 notes、controls、pitch bends、pedals。整份 `Score` 可在 tick、quarter、second 三種時間單位間轉換，並提供 `shift_pitch`、`shift_time`、`clip`、排序等修改方法。它可讀／寫 MIDI，事件列表亦提供 NumPy 視圖／資料接口。官方文件說其核心為 C++、Python 透過 nanobind；這是工具本身的實作特徵，尚不是 Tactus 實測速度結論。[Score model](https://symusic.readthedocs.io/en/stable/concepts/score.html) · [Track model](https://symusic.readthedocs.io/en/stable/concepts/track.html) · [Events](https://symusic.readthedocs.io/en/stable/concepts/events.html) · [Project README](https://github.com/Yikai-Liao/symusic)

## 可核對的差異與下一步邊界

| 工具 | 編輯時的時間座標 | Note 以外的表演資料 | MIDI I/O |
| --- | --- | --- | --- |
| Mido | MIDI messages 的 delta ticks | 原始 message 層可直接表達 CC／bend | 原生讀寫；前輪已實測 |
| MusPy | metrical steps + PPQ／tempo | CC 在 Mido 匯入時成 annotation，但預設輸出路徑沒有重建；bend 未映射 | 預設透過 Mido backend |
| pretty_midi | 絕對秒數 | `Instrument` 明確有 CC／bend lists | 直接 `write()` |
| Symusic | tick／quarter／second，可整份轉換 | `Track` 明確有 CC／bend／pedal lists | `Score` 讀入、`dump_midi()` 輸出 |

表格只列官方 API／原始碼能確認的形狀；**不表示**哪個 library 比 task-local Python 事件更易讓 Agent 維護，或任一 library 對任意 `.mid` 都是 lossless。尚須用同一段含變速、重疊音、CC64 和 pitch bend 的表演，分別做「只改一節、保存其他事件、輸出再讀回」的實作比較；尤其要確認輸入／輸出的事件保真與 Agent 首次完成率。Git 中的權威 source 仍應另外決定，不能因 library 能 `save()` 就默認二進位 `.mid` 是權威來源。

MusPy、pretty_midi、Symusic 的 GitHub 專案均標示 MIT license；這裡沒有對版本更新頻率或長期維護作判斷。[MusPy license](https://github.com/salu133445/muspy/blob/main/LICENSE) · [pretty_midi repository](https://github.com/craffel/pretty-midi) · [Symusic license](https://github.com/Yikai-Liao/symusic/blob/main/LICENSE)
