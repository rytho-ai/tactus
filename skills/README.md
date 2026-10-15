# Tactus plugin

**Produce music with code. Built for agents.**

Arrange, render, analyze, and refine.

Seven composable skills for making music with the separately installed Tactus Python runtime:

| Skill | Responsibility |
|---|---|
| [compose](compose/SKILL.md) | Develop and maintain a work as functional, modular code, choosing among synthesis, recorded material and devices; render, listen and revise. |
| [resources](resources/SKILL.md) | Find and download usable audio files, verify free access and use conditions, and preserve provenance for the work. |
| [dsp](dsp/SKILL.md) | Use or build sound sources, processors and controls, validate their behavior and accelerate measured bottlenecks. |
| [measure](measure/SKILL.md) | Use or write analyses, check joins and loop wraps, evaluate their limits and supply observations for creative choices. |
| [version](version/SKILL.md) | Explore, compare, preserve and reuse versions; use Git to connect source, refs and locks to audio. |
| [visual](visual/SKILL.md) | Make pictures that follow the music's time in any form — a video, a page that plays, live visuals — and measure their sync. |
| [interactive](interactive/SKILL.md) | Give a work an interface: its time map for players and pictures, decisions and performances as inputs, rendering on request, checked joins and browser delivery. |

Compose uses version when starting and adopting revisions, and links to DSP and
measurement when an idea needs them; interactive builds on compose when other code reads or
changes the work, and visual joins pictures to its time. Resources supplies external audio
when compose needs material. All seven are independently
usable. Builtin functions, Pedalboard and local Python are ordinary options. The skills
provide working methods and adaptable examples; musical form and aesthetics remain yours.

## Install from a checkout

From a clean Tactus checkout root, with Codex:

```bash
codex plugin marketplace add .
codex plugin add tactus@tactus
```

With Claude Code:

```bash
claude plugin marketplace add "$PWD"
claude plugin install tactus@tactus
```

Start a new session after installation. The skills are under the `tactus` plugin namespace
(for example, `/tactus:compose` in Claude Code). Existing `tactus-authoring` installations
should be removed after verifying the replacement, including any old skill symlinks; keep
user-authored copies until their changes have been migrated.
Installations from the earlier `tactus-local` marketplace (`tactus@tactus-local`) are replaced
by removing that marketplace, adding this one and installing `tactus@tactus`.

Both marketplaces point at the repository root, following the single-product layout used
by Rytho and My-wiki. Host manifests live in `.claude-plugin/plugin.json` and
`.codex-plugin/plugin.json`; the shared skill content lives in `skills/`.
Keep these platform entry points at their current locations:

| Path | Responsibility |
|---|---|
| `.claude-plugin/plugin.json` | Claude plugin metadata |
| `.claude-plugin/marketplace.json` | Claude marketplace catalog, targeting `.` |
| `.codex-plugin/plugin.json` | Codex plugin metadata and the shared `./skills/` path |
| `.agents/plugins/marketplace.json` | Codex marketplace catalog, targeting `.` |

The shared content has one owner:

```text
skills/
  compose/SKILL.md
  resources/SKILL.md
  dsp/SKILL.md
  measure/SKILL.md
  version/SKILL.md
  interactive/SKILL.md
  visual/SKILL.md
  references/
  examples/
```

References and small synthetic examples stay with the skills, so their relative links
work in installed copies. Installing the plugin does not install the Python runtime.
This follows the [Codex local marketplace format](https://developers.openai.com/plugins/build/plugins).
The two host manifests share the runtime's version (`0.1.0`); update both when versioning a
release, including the Claude marketplace entry. `pyproject.toml` owns the package name,
version and description; `tests/test_plugin.py` checks their consistency across manifests
and catalogs, marketplace names and root source paths, shared skills and installed-copy
references. Run `uv run pytest tests/test_plugin.py` after editing any of these entry points.
Install plugin and runtime from the same revision where possible. A work's own lock
can still pin another version: `tactus doctor`, installed signatures and `--help` are the
authority for what that work can execute. Reinstall/update a plugin after changing its source,
then start a new session to load it; cached installations are not editable source directories.

## Install from a development checkout

Local plugin installers can copy the source tree, including Git-ignored work files.
Installing from a checkout containing pools or dogfood runs can copy large audio files
or fail on their permissions. Use a separate clean checkout, or export the committed
revision into a persistent plugin source directory:

```bash
# From the development checkout; commit the plugin changes you want to install first.
plugin_source="$(mktemp -d "$HOME/tactus-plugin-source.XXXXXX")"
git archive HEAD | tar -x -C "$plugin_source"
cd "$plugin_source"
```

Then run the Codex or Claude installation commands above. Keep this directory while it
is registered as a local marketplace. The snapshot contains committed tracked files;
uncommitted changes and ignored audio pools are excluded. To adopt a newer revision,
export a new snapshot, replace the registered marketplace source using the host's
marketplace commands, then update/reinstall the plugin.

## Runtime and references

Install/select the runtime using [Creating a work](references/runtime.md#creating-a-work).
The plugin supplies guidance, not an MCP server or Python dependency installer.

- [Runtime contract](references/runtime.md): materials, render, candidates, takes, receipts.
- [Project commands](references/project-commands.md): custom analysis/export, delivery with the map and environment selection.
- [Rendering on request](references/serve.md): `tactus serve` for works that render while they play.
- [Packages and integration notes](references/packages.md): tool selection, layouts, timing and state.
- [Builtin DSP](references/dsp.md): available functions and behavior worth considering when adapting them.
- [Synthesis building blocks](references/synth.md): oscillators, seeded noise, envelopes, resonators, plucked strings and grains.
- [Devices](references/devices.md): a sampler, pads and a step sequencer to import or copy.
- [Ways of making music](references/techniques.md): techniques for recorded material and your own renders.
- [Accelerating DSP and synthesis code](references/acceleration.md): measurement steps and where Numba helps or loses.
- [Creative connections](references/connections.md): connect observations, time changes and processing.
- [Source regions and audio delivery](references/production.md): loop-body/tail boundaries and channel/master relationships.
- [Runnable examples](examples/README.md): synthetic, editable starting points; no sample downloads.

To verify the package in its repository, run `uv run pytest tests/test_skill.py tests/test_plugin.py`
and `claude plugin validate .claude-plugin/marketplace.json --strict` for the marketplace. Validate the plugin itself
with `claude plugin validate .claude-plugin/plugin.json`. Its warning about root `CLAUDE.md`
is expected: repository development instructions are separate from the installed skills.
Plugin loading and example execution
verify availability and technical behavior; they do not prove an increase in creativity.
