# Tactus product handoff — plan

> Generated: 2026-09-23 · Source: Paul's approval to merge the old Tactus mainline, rename it tactus-legacy, and promote tactus-code to Tactus · Grounding: both repositories and GitHub inspected.

## Context

The old private `rytho-ai/tactus` repository has a completed Python session facade on `experiment/python-session-facade`, ahead of `main`, with no open PR. Six research documents remain untracked. The new local `tactus-code` repository has no remote; its ballad example revisions and research notes are uncommitted. Existing documentation still describes parallel experiments rather than a product succession.

## Resolved questions

- The code-first implementation becomes the sole active Tactus product. Its early maturity remains explicit.
- Preserve the old repository as `tactus-legacy`, merge completed work before renaming, and tag the preserved mainline `legacy-handoff-2026-09-23`.
- Keep the new remote private, matching the existing repository. Do not publish packages or archive the GitHub repository.
- Preserve the legacy Python import/distribution for historical execution in its own environment. The active product adopts distribution/import/CLI `tactus` at version `0.1.0`; these incompatible implementations require separate environments.
- Preserve existing research and example work. Record those changes separately from the package rename so authorship/history remain inspectable.

## Approach

1. Run legacy tests/lint; review branch scope and retain the untracked research documents. Mark README and board as legacy/reference-only. Merge the completed branch into main and push with the handoff tag.
2. Rename the GitHub repository to `tactus-legacy` and update its local remote. Rename the local directory only after merge verification.
3. Commit the new repository's existing work separately. Rename its package tree, distribution, CLI, generated-directory default, current documentation, tests, and runtime receipt identity. Preserve historical thoughts, with a supersession note on the old two-repository decision.
4. Rename the local directory to `tactus`, rebuild its virtual environment, create the private `rytho-ai/tactus` remote, and push verified history.
5. Update live workspace pointers discovered by scoped searches; keep historical references identifiable as historical. Correct the recent thought's premature graph-provenance roadmap item.

## Critical files

| Files | Change |
| --- | --- |
| Legacy README and `docs/blueprints/plan.md` | Reference-only status and successor link |
| New `pyproject.toml`, `uv.lock`, `src/tactus_code`, tests | Distribution/import/CLI transition |
| New README, board, agent guidance | Single active product and practical commands |
| Existing two-repo and temporal thoughts | Supersession and approved correction |

## Verification

- Legacy full pytest and Ruff gates before merging; inspect final main SHA and tag remotely.
- New pytest, Ruff, package build, CLI version/doctor, and copied-example build/render/inspect smoke tests.
- Confirm both GitHub names, visibility, remotes, default branches, local roots, and clean committed handoff changes.
- Verify installation after moving directories; retain displaced environments recoverably if reconstruction is needed.

## Out of scope

New musical capabilities, a graph architecture, temporal API implementation, PyPI publication, importing the legacy architecture, and changing unrelated repositories' product behavior.

## Completion evidence

- Legacy main: completed facade merged at `086aeb8`, handoff tag pushed; reference documentation
  and compact aligned board committed through `f7b9250`. The renamed repository is private at
  `https://github.com/rytho-ai/tactus-legacy`.
- New existing research/example work preserved separately at `5a08c24`. The active private
  repository is `https://github.com/rytho-ai/tactus`; local roots are now `tactus/` and
  `tactus-legacy/`, each with a correctly targeted origin.
- Both virtual environments were recreated at their final paths. Import checks resolve
  `tactus==0.1.0` to the active source and `tactus==0.0.6` to legacy source. Previous environments
  were moved recoverably into `/tmp/tactus-env-handoff.nKupjX/` and
  `/tmp/tactus-legacy-env-handoff.8DlVSJ/`.
- Active pytest: seven passed; Ruff passed; wheel and source distribution built. Real CLI
  version/doctor/build/inspect/render worked with the `.tactus/` default in a copied example.
  A pre-rename format-v1 artifact replayed with an identical mix SHA-256.
- Legacy relocation verification: 1,983 passed, four skipped after environment reconstruction.
  Local links and Git whitespace checks passed. A scoped search found no live sibling
  configuration pointers requiring a rename.
- Legacy align preserved every prior Next/Future category as deferred reference, with an
  immutable link to the complete old board. No research documents were deleted. The v3
  blueprint convention was retained. Mechanical executor dispatch was unavailable for the
  account; the primary agent completed the documentation pass inline.
