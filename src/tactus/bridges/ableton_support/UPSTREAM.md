# Adopted Ableton support

Source: https://github.com/bschoepke/ableton-live-mcp
Revision: `89f3b4ef4663e33b40ee47bda75d16f9b0ade9a8`
License: MIT, copyright 2026 Ableton Live MCP contributors. See `_vendor/LICENSE`.
The Max JS and patch sources under `m4l/` use the same license.

Adopted modules: Max role/device/WebUI builder, cross-platform Ableton paths,
audio-tap builder/assets, Live similarity database query, and window/Max console capture.
Upstream MCP/socket server and native RPC wrappers are not embedded.

Local adaptations:

- Relative package imports; packaged Max sources resolve from this support directory.
- Writable default state is `~/.tactus/ableton`, configurable with
  `TACTUS_ABLETON_STATE_DIR`; generated files never default to site-packages.
- Generated host devices use the `TactusM4L_` prefix, avoiding the user's upstream
  `AgentM4L_` installation. Command/state paths use the independent state directory.
- Build-script imports are package-relative and do not modify `sys.path`.
- Adopted regression tests use package/asset paths and the Tactus prefix. Their
  original license is retained under `tests/ableton_reference/LICENSE`.

Project-owned wrappers and real-host lifecycle checks are maintained separately.
Do not infer real Live behavior from source-string tests or fake platform fixtures.

Additional local adaptations:

- `build_device(..., output_dir=...)` lets the public builder own an explicit new
  output folder. The legacy audio builder's default output is also under state/generated.
- Public builders remove the inherited UDP command input; the audio tap also removes
  MIDI-note recording triggers. Musical graphs remain ordinary authored Max code.
- Generated folders include the original MIT license alongside copied JS.
- Tap JS writes a correlated file acknowledgment and requests float32 recording.
  A patch loadbang is handled as polling wakeup, avoiding an invalid-JSON console error.
- WebUI reload clears the prior loaded-page flag before scheduling its new read.
  Previously an already-loaded panel skipped every requested reload read.
- Public command handling materializes top-level WebUI reload assets and accepts the
  upstream durable reload marker when a later WebUI event replaces the latest status.
- Similarity DB opening escapes paths as file URIs; incompatible/non-finite feature
  vectors are rejected. The public wrapper checks the actual required schema before
  querying, so an unsupported local database has a clear error.

The JS reload/loadbang and command-marker regressions were reproduced before their
fixes; real Max 8 page reload changed a running oscillator from 330 to 440 Hz, confirmed
in captured audio. These changes do not establish universal Max/plugin stability.
