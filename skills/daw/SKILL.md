---
name: daw
description: Work with REAPER or Ableton Live through Tactus bridges. Use for reading the open project or selection, editing MIDI and effects, discovering or loading devices, Max for Live and hosted VST operations, using a DAW as an instrument/effect package, handing Tactus results to a DAW, or co-working while the person edits in the DAW. Applies to short conversational requests such as checking what is selected or changing the selected clip; a new Tactus render is only needed when producing deliverable audio.
---

# Work with a DAW

Use the host's native API to express the requested music. Tactus shares connection,
completion, target checks and repeated execution mechanics; you choose notes, sounds,
effects, routing, automation and arrangement. The helpers are conveniences, not a list
of allowed creative operations.

## Choose the host and purpose

Use the host and connection already established in the conversation. If both hosts
are available, resolve the intended one from the request; ask only when it is unclear.
Read the relevant reference before calling its bridge:

- **REAPER:** [REAPER bridge](../references/reaper.md). Host Python sends ordinary Lua
  to `reaper.*`; `resource_path` is REAPER's resource directory. Read the connection
  section if unavailable. Borrow audio through **Use REAPER to make audio**, inspect
  or edit through **Co-work in the live project** / **Quick parameter edits**, and
  deliver through **Hand completed audio to REAPER** or **Capture and rebuild accepted state**.
  For private sound libraries, read [Plugin presets and private libraries](../references/reaper.md#plugin-presets-and-private-libraries).
- **Ableton Live:** [Ableton bridge](../references/ableton.md). Host Python sends native
  Python to Live's embedded interpreter; `bridge_path` is the installed `TactusMCP`
  directory. Read **Install once** if unavailable. Use **Shared reads and observed changes**,
  **Max for Live and VST**, and **Audio, handoff and accepted native work** as needed.
  Embedded Python and Max API availability depend on the actual installed versions.

These purposes can be combined; they are not mandatory stages:

| Request | Path |
|---|---|
| Use the DAW as an instrument/effect package in a Tactus work | Author the native instrument, MIDI, FX and routing; use the host's shared render/capture mechanism to return audio to the work. Choose the performance window, tails and any alignment yourself. Follow [compose](../compose/SKILL.md) for the work and audio delivery. |
| Continue a Tactus result in the DAW | Start from the accepted saved run or accepted native state. Use the host's export/capture/rebuild path and verify the delivered project and media reopen. Printed stems preserve sound; editable MIDI, automation and device state require explicit native data/state. Do not imply arbitrary Python can be inverted into an editable session. |
| Talk with the person while they work in the DAW | Read the current target, make the requested scoped change and return native readback. Audition in the open host; capture/render only when adopting or delivering the result. |

## Read, change and continue the conversation

- Start with fresh project identity and the selection or explicit target relevant to
  the request. Reuse known connection details and parameter descriptions. Request only
  needed notes/device detail; a full project snapshot is for lifecycle work. Report
  what the API actually exposes: Live's detail clip/selected note IDs do not establish
  an unavailable Arrangement time selection.
- For supported MIDI or parameter edits, use the shared selection/device helpers in
  the host reference. They check current targets and observed values before writing.
  For broader native operations, author equivalent checks for the relevant scope;
  use the actual units and identities exposed by that host. REAPER FX helper values
  are normalized 0..1; Live device helper values use each parameter's native scale.
- Generate music/data and do long computation in host Python, then pass explicit
  arguments into short native calls. Batch related chosen values and use the edit's
  compact actual readback for the next step. Group an edit with native Undo where
  supported, without spanning a human action or asynchronous settling interval.
- On stale state, inspect again and reconsider the change against the new state.
  On native error or timeout, inspect actual state and any late reply before deciding
  what to do next. A timeout does not cancel a running edit, and Undo is not automatic
  rollback. Do not blindly retry an operation whose completion is unknown.
- Discover actual installed devices and exposed parameters when needed. Max patches,
  VST choices and native routing remain authored. A browser item is not proof its
  private UI is API-accessible, its dependencies are installed or its audio was tested.

A read or short edit needs no new work, recording, capture or render. Keep the person's
open project and unsaved work intact. Live has one active Set: native handoff/rebuild
requires the dedicated workspace and recovery procedure in its reference. REAPER's
private-tab workflows have different boundaries; follow the relevant host's contract.

## Adopt or deliver a result

The open DAW project is external input. When the work adopts GUI edits, preserve the
needed native project/media, explicit MIDI/FX data or chosen audio, pin it as material
and update source/refs through [compose](../compose/SKILL.md) and
[version](../version/SKILL.md). Rebuild from writable copies outside the material pool.
Declare required host/plugin tools and dependencies; project capture cannot discover
every plugin-private asset. Pin accepted audio when exact replay matters.

Deliver audio only from a `tactus run` directory with its receipt. Native edit replies,
an audition and a saved DAW project are not render receipts. An existing accepted run
can be exported without composing or rendering it again. Report native verification
separately from what you actually listened to.
