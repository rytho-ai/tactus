# Tactus plugin

**Produce music with code. Built for agents.**

Arrange, render, analyze, and refine.

Three composable skills for making music with the separately installed Tactus Python runtime:

| Skill | Responsibility |
|---|---|
| [compose](compose/SKILL.md) | Develop and maintain a work as functional, modular code; render, listen and revise. |
| [dsp](dsp/SKILL.md) | Use or build processors and controls, validate their behavior and accelerate measured bottlenecks. |
| [measure](measure/SKILL.md) | Use or write analyses, evaluate their limits and supply observations for creative choices. |

Compose links to DSP and measurement when an idea needs them. All three are independently
usable. Builtin functions, Pedalboard and local Python are ordinary options. The skills
provide working methods and adaptable examples; musical form and aesthetics remain yours.

## Install from a checkout

From the Tactus repository root, with Codex:

```bash
codex plugin marketplace add .
codex plugin add tactus@tactus-local
```

With Claude Code:

```bash
claude plugin marketplace add "$PWD"
claude plugin install tactus@tactus-local
```

Start a new session after installation. The skills are under the `tactus` plugin namespace
(for example, `/tactus:compose` in Claude Code). Existing `tactus-authoring` installations
should be removed after verifying the replacement, including any old skill symlinks; keep
user-authored copies until their changes have been migrated.

Both marketplaces point at the repository root, following the single-product layout used
by Rytho and My-wiki. Host manifests live in `.claude-plugin/plugin.json` and
`.codex-plugin/plugin.json`; the shared skill content lives in `skills/`:

```text
skills/
  compose/SKILL.md
  dsp/SKILL.md
  measure/SKILL.md
  references/
  examples/
```

References and small synthetic examples stay with the skills, so their relative links
work in installed copies. Installing the plugin does not install the Python runtime.
This follows the [Codex local marketplace format](https://developers.openai.com/plugins/build/plugins).
The two host manifests share the runtime's version (`0.1.0`); update both when versioning a
release. Install plugin and runtime from the same revision where possible. A work's own lock
can still pin another version: `tactus doctor`, installed signatures and `--help` are the
authority for what that work can execute. Reinstall/update a plugin after changing its source,
then start a new session to load it; cached installations are not editable source directories.

## Runtime and references

Install/select the runtime using [Creating a work](references/runtime.md#creating-a-work).
The plugin supplies guidance, not an MCP server or Python dependency installer.

- [Runtime contract](references/runtime.md): materials, render, candidates, takes, receipts.
- [Project commands](references/project-commands.md): custom analysis/export and environment selection.
- [Packages and integration notes](references/packages.md): tool selection, layouts, timing and state.
- [Builtin DSP](references/dsp.md): available functions and behavior worth considering when adapting them.
- [Creative connections](references/connections.md): connect observations, time changes and processing.
- [Runnable examples](examples/README.md): synthetic, editable starting points; no sample downloads.

To verify the package in its repository, run `uv run pytest tests/test_skill.py tests/test_plugin.py`
and `claude plugin validate . --strict` for the marketplace. Validate the plugin itself
with `claude plugin validate .claude-plugin/plugin.json`. Its warning about root `CLAUDE.md`
is expected: repository development instructions are separate from the installed skills.
Plugin loading and example execution
verify availability and technical behavior; they do not prove an increase in creativity.
