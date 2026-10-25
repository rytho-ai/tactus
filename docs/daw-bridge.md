# Connect Tactus to REAPER or Ableton Live

Tactus can work with an open REAPER project or Ableton Live Set through each DAW's native API. Install the bundled bridge, activate it inside the DAW, and connect your coding agent. One `tactus-mcp` connection can serve both DAWs; either one can be used on its own.

The bridge passes requests through local files between Tactus and a script running inside the DAW. MCP supplies tools to an existing agent conversation; it does not start another chat app. Tactus does not continuously mirror projects between DAWs. The agent chooses when to inspect, edit, capture, or hand off material.

## Install and connect

First [install Tactus from this repository](../README.md#install) and install the Codex CLI if you want automatic Codex registration. From the checkout, add the optional MCP dependency to the CLI installation and register the connection:

```bash
uv tool install --python 3.12 --force '.[mcp]'
tactus connect --host codex
```

The second command copies the bundled `TactusMCP.lua` script into REAPER's detected resource directory and the `TactusMCP` Remote Script into Live's detected User Library. It reports unavailable locations and prints the remaining steps for installed DAWs. You do not need to download scripts separately. If you use Tactus from the checkout's environment instead of a global CLI, run `uv sync --extra mcp` and `uv run tactus connect --host codex`.

Use `tactus connect` without `--host codex` when you only want the DAW scripts or will configure another MCP host yourself. For manual MCP configuration, run the installed `tactus-mcp` executable without a DAW argument and use the [host configuration example](../skills/references/reaper.md#connect-an-existing-conversation-through-mcp). The Python bridge APIs work without the MCP extra.

## Activate the bridge in each DAW

| DAW | Activate inside the DAW | After updating Tactus |
|---|---|---|
| REAPER | Open **Actions**, choose **ReaScript: Load**, select the printed `TactusMCP.lua` path, then run that Action. Keep the Action running while Tactus works with REAPER; run it again after restarting REAPER. On macOS, while REAPER is closed, `open -a REAPER "<printed path>"` launches REAPER and runs the script in one step. | Rerun `tactus connect`, then stop and rerun the Action. |
| Ableton Live | Restart Live. In **Settings → MIDI** (or **Preferences → Link/Tempo/MIDI**), choose **TactusMCP** in an unused Control Surface slot. Input and Output can stay **None**. | Rerun `tactus connect`, then restart Live. |

`tactus connect` does not launch either DAW or change a project or Control Surface selection. It backs up installed bridge files before replacing different versions. If you previously used `TactusBridge` in Live or an older Tactus Action in REAPER, follow the [Live migration notes](../skills/references/ableton.md#install-once) or [REAPER migration notes](../skills/references/reaper.md#connect-an-existing-conversation-through-mcp) after the new bridge is active.

## Check the connection

```bash
tactus connect --check --host codex
```

This reports the script installation, Live's active Control Surface, and the Codex MCP entry without changing settings. A script can be installed while its DAW is still inactive. Reload MCP connections or start a new Codex session after registering `tactus-mcp`, then ask the agent to call `tactus_connections`. It lists running bridge processes and their current REAPER project tabs or Live Set. Use `reaper_status` or `ableton_status` to read the intended project before editing it.

You can leave either DAW closed. The other connection still works, and a newly started bridge becomes available through the same MCP server. When multiple REAPER instances are open, the agent should choose the reported `connection_id` and `project_id`; these IDs describe the current session, not permanent project names.

## Custom locations and other agent hosts

If Tactus cannot find a DAW's standard folder, pass the actual locations to the installer:

```bash
tactus connect --host codex --reaper-path "/path/to/REAPER resources" --live-library "/path/to/Ableton/User Library"
```

`--reaper-path` names the REAPER **resource directory**, not its `Scripts` subfolder. `--live-library` names Live's **User Library**, not `Remote Scripts/TactusMCP`. Use the same options with `--check` to inspect those locations first. For a manually configured `tactus-mcp` server, the runtime options are different: `--reaper-path` still names the REAPER resource directory, while `--live-path` names the installed `TactusMCP` directory.

`--host codex` registers Codex automatically. Other coding-agent hosts need a manual MCP entry pointing to the installed `tactus-mcp` executable or to the Python environment that has `tactus[mcp]`. See the [MCP configuration example](../skills/references/reaper.md#connect-an-existing-conversation-through-mcp).

## Choose a workflow

- **Use a DAW as a Tactus instrument:** write ordinary Python that calls the [REAPER bridge](../skills/references/reaper.md) or [Ableton bridge](../skills/references/ableton.md) and keep the musical decisions in the work.
- **Hand a finished work to a DAW:** render and accept the Tactus work, then use the [REAPER lifecycle example](../examples/reaper/README.md) or [Ableton handoff example](../examples/ableton/README.md) to create native project material.
- **Make music together in an open project:** let the agent inspect the current selection, make a scoped edit through the native API, and audition it in the DAW. The [DAW skill](../skills/daw/SKILL.md) routes these requests to the relevant host guide.

Native scripts run with the DAW's normal scripting access. Use bridge edits on projects you trust, keep normal project backups, and verify the current target before a write. The detailed guides explain each DAW's supported state, Undo behavior, and handoff limits.
