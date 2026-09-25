# Folder material and tool identity — plan

> Generated: 2026-09-25 · Source: board ▶ Next 1, agreed with Paul · Grounding:
> `src/tactus/inputs/` (`material`, `tool`, `pool`), `src/tactus/cli.py`, the full-song dogfood
> and the Pedalboard probes. Status: implemented 2026-09-25; VCS directories (`.git`, `.hg`, `.svn`) are
> skipped, added in review after the swagbass folder carried a 139 MB `.git`.

## Context

`material()` and `tool()` identify single files only.

- **SFZ instruments.** An SFZ instrument is a folder: `.sfz` programs `#include` sibling files
  and reference sample folders by relative path. The Karoryfer bass used in the full-song
  dogfood is 2.1 GB in 2,340 files. The Agent had to leave it as an unpinned path, as
  phonon-ballad still does for `sfz_piano`.
- **VST3 bundles.** A VST3 plugin is also a folder (`Name.vst3/Contents/...`). Every probe Agent
  had to learn that `tool()` takes the binary inside the bundle while `load_plugin` takes the
  bundle folder.

## Resolved choices

- **Ref format.** A folder ref is `tree:sha256:<hex>`, distinct from a file ref
  `sha256:<hex>`, so resolution knows to rebuild a folder.
- **Tree digest.** The digest is the SHA-256 of a canonical manifest: one line per regular
  file, `<relative posix path>\t<file sha256>\n`, sorted by path, UTF-8.
  - Symlinks, special files and empty relative names are rejected with a clear error.
  - Empty folders are not represented.
  - The manifest is stored in the pool as an ordinary blob under the tree digest, and each
    file is stored as its own blob (deduplicated).
- **Resolution.** `material("tree:sha256:X")` reads and verifies the manifest blob, then
  materializes `<pool>/trees/X/` with a hardlink to each verified blob (copy when hardlinks
  fail), and returns that folder path.
  - Every resolve re-verifies each file's hash, consistent with file materials; this takes
    seconds for 2 GB.
  - A missing blob gives `missing`; a hash mismatch gives `corrupt`.
  - Materialization is atomic: build in a temp dir, then rename.
  - An existing materialized folder is reused after verification against the manifest,
    including that it holds no extra files.
- **Import.** `tactus material add PATH...` accepts folders and prints `tree:sha256:…` for
  them.
- **`tool(path_to_folder)`.** It computes the tree digest of the folder in place, without
  storing it, and records `{name, path, sha256: <tree digest>, kind: "tree"}`. It returns the
  folder path, so `pedalboard.load_plugin(tool(".../Name.vst3"))` is one step. File tools gain
  `kind: "file"`. The receipt `tools` entries document `kind`.
- **Receipt.** `materials` entries keep `{"ref": ...}`; the ref prefix tells file from tree.

## Approach

1. `src/tactus/inputs/tree.py`: manifest building from a folder, digest, parsing, and
   materialization with verification. `pool.py` stays bytes-only.
2. `inputs/__init__.py`: `material()` dispatches on the ref prefix; `tool()` accepts folders.
   Update module headers.
3. `cli.py`: `material add` accepts folders; its JSON keeps `{path: ref}`.
4. **Adoption.**
   - phonon-ballad's `sfz` palette takes `sfz_piano` as a `tree:sha256:` ref plus a program
     name, resolved through `material()`, instead of an unpinned path. It still cannot be
     parity-checked without an SFZ piano on this machine; say so.
   - The skill documents folder materials and `tool()` on bundles, and replaces the
     "two paths" VST snippet with the one-step form.
5. **Tests.** A synthetic folder with nested dirs and an `#include`-style relative reference:
   - the same digest from any location;
   - a changed file, rename or extra file changes the digest;
   - a symlink is rejected;
   - resolve rebuilds the exact tree (relative reads work);
   - a missing or corrupt blob fails with `material_unavailable`;
   - a tampered materialized folder is detected and rebuilt, or reported;
   - `tool(folder)` records `kind` `tree`, and the digest is stable;
   - CLI `material add DIR`.

## Verification

- pytest, Ruff and the skill drift test.
- A real import of the Karoryfer swagbass folder (306 MB): time the add and a resolve, and
  render one note with `sfizz_render` from the materialized folder, so relative `#include`
  paths resolve.
- `tool(~/.vst3/OB-Xf.vst3)` plus `load_plugin` on the returned path.

## Out of scope

Partial or lazy verification, garbage collection of materialized trees, remote sync, and
parsing SFZ files to find only the samples they use.
