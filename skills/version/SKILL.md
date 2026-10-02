---
name: version
description: Use versions to explore musical directions, compare and adopt candidates, reuse earlier ideas or recover a Tactus work. Use Git to preserve source, refs and locks connected to render receipts.
---

# Version a Tactus work

Versions preserve creative possibilities. Keep a useful sketch, alternate direction or
earlier sound even when another version becomes the current delivery. Git records the
work's source, material refs and dependency lock. Render receipts connect
those revisions to generated audio. Use ordinary Git commands; Tactus records revisions
but does not create commits. Honor the user's limits on commits and publication.

## Decide how to use the versions

- **Explore a question.** State what you want to hear: sparse versus layered, dry versus
  spacious, or two rhythmic feels. Keep the inputs/context stable when comparing that
  choice. Name versions by their character or question rather than implying newer is better.
- **Choose continuation or divergence.** Continue a small understood revision in place.
  Keep separate source variants or a branch/worktree when directions deserve independent
  development. A branch can remain an alternative; adoption need not merge every idea
  into one final version. Commit useful exploration checkpoints as well as accepted results.
- **Compare in context.** Use the same musical passage and deliberate playback levels.
  Listening decides musical preference; measurements explain technical differences.
  Record the listener's choice and reason when given. Describe an unselected version as an
  alternative, not a failure, unless there is an identified fault.
- **Reuse parts.** Retrieve an earlier rhythm, processor, motif or pinned performance and
  explicitly connect it into the new source. Record its origin and inspect timing, tuning,
  rate and processing boundaries. See [audio delivery](../references/production.md#explain-the-stem-and-master-boundaries)
  before recombining prints. Versions can supply materials across works.
- **Keep sketches at their useful fidelity.** A short audio bounce or rough source sketch
  can preserve an idea without a complete reconstruction. Label what it captures and what
  is missing; reserve exact-recovery claims for preserved inputs, source, lock and verified
  output. Save existing rationale alongside the relevant commit/work note; avoid demanding
  a separate document for every experiment.

These practices adapt themes from
[Towards Creative Version Control](https://ssterman.web.illinois.edu/assets/pdfs/towards_creative_version_control.pdf)
(Sterman, Nicholas and Paulos, 2022): versions as materials, freedom to explore,
deliberately partial capture, and long-term reflection/reuse. Git is the current recording
tool; these creative choices are the skill's responsibility.

## Establish the work's history

1. **Check Git and the repository.** Run `git --version`, then from the work run
   `git rev-parse --show-toplevel` and `git status --short`. Git must be installed and on
   PATH for this workflow. If unavailable, report the missing prerequisite and keep the
   files; do not claim version history exists. An installed binary alone is insufficient.
2. **Verify the work is tracked.** Check `git ls-files -- song.py pyproject.toml uv.lock`
   (use the actual entry/module paths) and `git check-ignore -- song.py pyproject.toml uv.lock`.
   An ancestor repository is usable when it intentionally tracks the work. A product repo
   containing an ignored work does not version that work: create the new work outside it,
   or initialize a separate repository inside the work. Current `tactus init` creates a
   work's own Git root; older versions may reuse an ancestor. Verify the actual tracking
   rather than relying on `git_init` or receipt HEAD.
3. **Commit the starting source before rendering.** Track the entry and local modules,
   `pyproject.toml`, `uv.lock`, `.gitignore`, and any small data explicitly read by source.
   Keep generated runs, analyses, exports, caches, environments and the audio pool ignored.
   Read the diff and stage named paths so unrelated user edits remain untouched. Check
   `git var GIT_AUTHOR_IDENT`; use the user's existing identity, or ask for a missing one.
   Completion: `git ls-files` contains the work inputs and `git log -1` shows a work commit.

For a fresh work, adapt this example to its actual files:

```bash
git add -- song.py pyproject.toml uv.lock .gitignore
git diff --cached
git commit -m "Start the work"
tactus run song.py --out runs/baseline
```

Use `uv` for Python and dependency operations. Read
[Creating a work](../references/runtime.md#creating-a-work) for environment selection.
Git availability is required by current `tactus init`. The renderer still permits running
existing source without Git, and `tactus doctor` reports the environment without checking Git.

## Revise and adopt

1. **Record the base.** Read `git status --short`, `git log -1` and the existing candidate's
   receipt. Locate the musical choice in source before editing. For a parallel structural
   experiment, use a branch/worktree; ordinary small edits can remain in the checkout.
2. **Render a separate candidate.** Use a new `--out` and inspect its receipt's `git`,
   `source_files`, `dependency_lock`, `parameters` and material refs. An uncommitted
   candidate can have `dirty: true` and a patch; its HEAD alone is not the candidate.
   Keep listener-facing outputs in the main checkout's ignored `runs/` or another durable
   location, including when rendering from a disposable worktree.
3. **Adopt the listener's choice in source.** Set the selected defaults or material refs.
   If this changes what ran, render again and compare every output hash before identifying
   it as the selected result. Use [Saved takes](../references/runtime.md#saved-takes) when
   a performance varies between runs. Measurements alone do not establish musical approval.
4. **Preserve audio and commit the revision.** Follow
   [Keeping a candidate](../references/runtime.md#keeping-a-candidate) to pin the approved
   audio and name its run/hash in the commit message. Review/stage only the intended source,
   refs and lock changes. Git preserves refs, not the referenced audio: retain the pool and
   listener-facing files, and arrange a separate backup when sharing or moving machines.
5. **Verify the connection.** Check `git show --stat HEAD` and source/lock hashes against
   the chosen receipt. That receipt retains its original pre-commit attribution; never edit
   it to claim the new HEAD. A new render from the committed source provides a clean receipt
   linked to that commit. Compare all output hashes if claiming exact reproduction; otherwise
   report which audio was approved and which later render has not been verified/listened to.

Completion: the revision commit explains the musical change and identifies the preserved
approved audio; source and receipt identities are accounted for. Report the commit and run
to the user. Committing the Tactus product itself is a separate maintenance action.

## Inspect or recover history

Use `git log` and `git diff OLD..NEW -- PATHS` to explain changes. To audition an old revision,
use `git worktree add --detach PATH COMMIT`, `uv sync --frozen` there, restore its pinned
materials, and render to a new directory outside that temporary worktree. Compare every
output hash before claiming identical reproduction. Check user edits before cleanup and
keep all audio already handed to a listener available after removing the worktree.
When the work pins Tactus by a local path (`tactus init --tactus-path`), put the worktree beside
the work, at the same directory depth: `uv.lock` stores that path relatively, and a worktree at
another depth is refused as an out-of-date lock. A rebuild matches the old audio only while
Tactus and the other packages match the old receipt; the pinned audio is the lasting record.

A local commit is local history. Push, remote creation, branch merging and history rewriting
require authorization for that action; preserve unrelated work and existing history.
