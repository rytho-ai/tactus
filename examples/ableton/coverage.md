# Reference capability coverage

Reference: [bschoepke/ableton-live-mcp](https://github.com/bschoepke/ableton-live-mcp),
pinned to `89f3b4ef4663e33b40ee47bda75d16f9b0ade9a8` (MIT). The following inventory
accounts for its 38 registered tools. Tactus retains two MCP tools and exposes
ordinary native Python plus optional libraries/recipes instead of duplicating 38 RPCs.

The actual host used for acceptance is Live 11.3.43 / Python 3.7.3 / Max 8.5.8 on
macOS. Native evidence and version requirements are distinguished below; fixture tests
are not a claim of Live 12 or Windows acceptance.

| Reference capability | Tactus route and evidence |
| --- | --- |
| `live_ping`, `live_bridge_status`, `live_set_summary` | Two-tool status/execute; shared scoped native reads for MCP/co-work/lifecycle; real stdio summary/notes/device and offline status tests. |
| `live_eval`, `live_exec`, `live_batch` | Ordinary Python expressions, statements and multiple operations in `execute`; actual main-thread code, arguments, failures and grouped edits. |
| `live_get`, `live_set`, `live_call`, `live_children` | Native attributes/methods/children; full explicit JSON results rather than an RPC object vocabulary. |
| `live_observe`, `live_events` | Shared observed revision/property support, plus authored listener/callback storage. Actual note/parameter notifications and target cleanup; tempo event `[121.0]`, retrieval and detachment. Notifications remain incomplete edit hints. |
| `live_transport`, `live_undo` | Native transport observed in later calls and actual grouped gain/pan/MIDI Undo. Partial mutations remain on error; meter was not fully restored by Undo. |
| `live_browser_roots`, `live_browser_capabilities`, `live_browser_search` | Native browser roots/children/capability detection and authored traversal. Actual exact Max paths and VST3 vendor/device discovery. |
| `live_browser_load`, `live_load_device` | Native browser loading with explicit track/chain/selection guards; actual Max host/tap, Operator, Massive and Breaks Bridge VST3 load. |
| `live_browser_preview` | Actual sample-item preview/stop API calls with the preview bus muted/restored. Preview audio itself was not captured/listened to. |
| `live_device_parameters`, `live_parameter_set` | Native published parameters. Actual Max custom dial/frequency and VST Device On mutation/readback/Undo. Plugin-private controls require exposure/configuration. |
| `live_clip_notes`, `live_clip_add_notes`, `live_clip_update_notes` | Extended notes/IDs, explicit creation and selected-note vector edits. Actual outside-note preservation, stale rejection and Undo. |
| `live_clip_duplicate_to_arrangement` | Native Session-to-Arrangement duplication at an explicit beat, read back from the actual Set. |
| `live_clip_envelope`, `live_clip_velocity_envelope` | Native clip automation; authored velocity mapping. Actual step value `.25` and velocity-derived `.708661437` readback. |
| `live_clip_warp_markers` | Actual add/read/move/remove using native markers; 1.1→1.35 beat move verified. |
| `live_track_create_audio_clip` | Actual Arrangement and Session audio-file clip creation, placement and media readback. |
| `live_track_insert_device` | Conditional native method: absent on tested Live 11. Browser/selected-device insertion fallback verified; no false claim of the newer explicit-index API on Live 11. |
| `live_agent_m4l_device` | Optional `max.build/command`, all three adopted role builders, ordinary patch/JS files. Actual graph/audio, Max 8 `jweb`, page-to-DSP control and 330→440 Hz page reload verified. |
| `live_agent_m4l_cleanup` | Exact owned track/device IDs and chain guards, native device deletion/readback and own fixture-track removal. |
| `live_agent_audio_tap_setup`, `live_agent_audio_tap` | Optional `audio.build/command`; actual namespaced device/acknowledgments and stereo float32 capture at 44.1 kHz, used by receipted Tactus runs. |
| `live_visual_capture`, `live_max_console_capture` | Optional `visual` module; actual nonblank Live capture and Max console capture containing an authored probe marker. Other OS/backends have fixture coverage only. |
| `find_similar_sounds` | Optional read-only `similar.find`; supported reference-schema fixture ranks near/far and preserves DB bytes. Local Live 11 DB lacks `places.name`/`fe_values.hash` and reports the requirement. A compatible analyzed Live 12 database is conditional; no synthetic fallback result. |

The optional Max engine retains the upstream bounded status summaries/truncation flags;
these are not a complete accepted-state snapshot. Preserve the authored graph, values,
code and dependencies explicitly. The native Python bridge itself does not truncate
JSON results or blacklist API text. Tactus-generated Max wrappers use file commands;
UDP listeners and MIDI-note record triggers are not enabled implicitly.

Beyond the reference inventory, Tactus exercises three complete workflows: receipted
Live audio with a changed-input comparison and exact saved-array replay; a saved native
handoff reopened after export publication; and selected native MIDI/Max edits captured
as pinned bundles, rebuilt from writable copies and recorded into new receipted runs.
The original pool bundles were verified unchanged. This does not claim that every
third-party plugin can be frozen, that native regeneration is deterministic, or that
arbitrary graph edits maintain uninterrupted playback.

Adopted source/license/patch notes are in
`src/tactus/bridges/ableton_support/UPSTREAM.md`. Contract tests are
`tests/test_ableton_*.py`, adopted tests are `tests/ableton_reference/`, and the native
macOS folder-name regression is in `tests/test_tree.py`. The source distribution
includes examples/tests; installed plugin references do not depend on copying them.
