# Audition acceptance and Git revision record — plan

> Generated: 2026-09-24 · Source: Paul approved planning the audition/acceptance loop after the
> [second production](2026-09-24-second-production-through-run.md). It covers inventory items A3
> and A4 from the
> [implementation inventory](../thoughts/2026-09-24-implementation-evidence-inventory.md); A5 is
> deferred. · Grounding: fresh reads of `src/tactus/run.py` and the
> audition/Git thoughts and probes (listed in Context). Status: steps 1–2 and 5 shipped in `d102e83`.
> Step 3 (`tactus accept`) was built and tested, then shelved on branch `shelved/tactus-accept`:
> an A/B probe with fresh Agents showed that explicit skill guidance alone prevents the error it
> guards against. See the [accept probe](../thoughts/2026-09-24-accept-necessity-probe.md); the branch
> was deleted on 2026-09-26 ([why](../thoughts/2026-09-26-delete-tactus-accept.md)). Step 4 and
> step 5's guidance now describe keeping a candidate with Git.

## Context

Today a candidate is a `tactus run` with `--params`. Each run gets a fresh process and a new
output directory, and the receipt records the effective parameters and the SHA-256 of every
entry-directory `.py` file plus the nearest `uv.lock` (`run.py:235-265`, `352-369`).

Accepting a candidate is a manual source edit. Nothing checks that the source is still the one
the candidate came from, and nothing confirms that the accepted source reproduces the candidate's
audio ([design](../../design.md) 試聽 section). Positioning §6 requires that discarding a
candidate leaves the work untouched, and that accepting one forms a traceable revision.

The receipt has no Git information. A commit hash alone would misstate a run from a dirty tree,
and `source_files` hashes prove which bytes ran but cannot restore them.

Prior evidence:

- [transactional audition](../thoughts/2026-09-23-transactional-audition.md): promotion is a
  guarded, one-time source edit that conflicts on stale base and verifies the formal output. It
  deliberately did not choose how to locate the "target expression".
- The 09-15/16 Git probes (`../tactus-daw/docs/blueprints/thoughts/2026-09-15-python-rcp-git-probe.md`,
  [plain Python + Git](../thoughts/2026-09-16-plain-python-git-beatmaking-probe.md)): plain Git
  handled commit, clone, revert and rebuild. A one-line parameter edit produced a one-line diff.
  No Tactus-owned Git commands were needed.
- No reusable implementation exists in either repository.

The target expression is now well defined. `render` accepts only keyword-only parameters with
JSON-valued defaults (`run.py:_bind`). A candidate differs from the source only in those
parameter values, so accepting it means rewriting the matching default literals in `render`'s
signature. `ast` gives each default's exact source span, so only those characters change.

Compatibility boundary: `render`, `run`, `tactus run`, and the manifest are unchanged. The
receipt gains fields and stays `format_version` 2, because additions do not break its readers
(the skill and a test).

## Resolved questions

- **No GitPython; Git is called as `git` with list arguments and `--` before paths.** Absent Git
  or a non-repository yields a null `git` record, never a failure.
- **Target expression = a default in `render`'s signature.** Promotion covers declared
  parameters only. Structural Python changes stay outside `accept`.
- **Base identity = the receipt's `source_files` + `dependency_lock`.** It is content-based, so
  it works with or without Git and inside worktrees.
- **`accept` never commits** (Paul, 2026-09-24). It edits source, verifies the audio, and prints
  the diff; the author or Agent commits with plain `git`.
- **Any inventoried change is a conflict** (Paul, 2026-09-24): any entry-directory `.py` file or
  the lock changing after the candidate ran blocks acceptance.
- **A5 range audition is deferred** (Paul, 2026-09-24) until a real production asks for
  section-only listening. `elapsed_seconds` provides the evidence for that decision.

## Approach

**1. Git revision record** (new `src/tactus/revision.py`, adopted by `run.py`).
- Before execution, `_execute` records `git`:
  - `commit`: the `HEAD` SHA;
  - `dirty`: whether tracked files under the entry directory differ from `HEAD`;
  - `untracked`: untracked `.py` files under the entry directory;
  - `patch`: when dirty, the relative path of `source.patch`, the output of
    `git diff HEAD --binary -- <entry dir>` saved in the run directory, so `commit` + `patch`
    restores the executed source.
- Record `null` outside a repository or without Git. Use a timeout and `GIT_OPTIONAL_LOCKS=0`
  so reads never take locks.

**2. Timing.** Add `elapsed_seconds` for the render call to the receipt. Later decisions about
range audition and caching need measured waits (stateful-audition contract item 6).

**3. `tactus accept RUN_DIR`** (new `src/tactus/accept.py`, CLI in `cli.py`, public
`tactus.accept`).
1. Read the run's receipt and manifest.
2. Re-inventory the entry directory. If it differs from the receipt, fail with `base_changed`
   and list the changed paths.
3. Parse the entry file. For each receipt parameter whose value differs from the current
   default, replace the default's source span with the Python literal of the JSON value.
   Fail with `not_promotable` for a parameter without a default. Write the file atomically.
4. Re-run the source into a verification directory. Compare the manifest output hashes with
   the candidate's.
   - On a match, print JSON: the changed parameters, the source diff, and the verification
     run's paths.
   - On a mismatch (for example nondeterminism), restore the original bytes and fail with
     `not_reproduced`.
5. Accepting a run whose parameters already equal the defaults is a no-op that still verifies.

**4. Worktree guidance, not code.** Structural experiments (new stages, re-ordered processing)
use `git worktree`/branches directly. Each run's `git` record identifies its branch state, and
accepting such a candidate means merging with Git. Document this in the skill; add no wrapper.

**5. Skill and docs.** Update `skills/tactus-authoring/SKILL.md`:
- steps 3 and 5: candidates, then `tactus accept`, then commit with Git;
- the receipt `git` and `elapsed_seconds` fields;
- the worktree note.

Update `docs/design.md` (試聽 section), README, and the board.

## Critical files

| File | Role and planned change |
|---|---|
| `src/tactus/run.py` | Call revision record; add `git`, `elapsed_seconds`; expose inventory for reuse by accept |
| `src/tactus/revision.py` (new) | Git read-only queries and patch capture |
| `src/tactus/accept.py` (new) | Base check, AST default rewrite, verification run, restore on failure |
| `src/tactus/cli.py`, `src/tactus/__init__.py` | `accept` subcommand and export |
| `skills/tactus-authoring/SKILL.md`, `tests/test_skill.py` | Contract docs; drift test covers new fields |
| `tests/test_revision.py`, `tests/test_accept.py` (new) | Behavior tests |

## Verification

- **Revision:** tests use temporary Git repositories.
  - A clean tree gives the commit and `dirty: false`.
  - An edited file gives `dirty: true`, and applying `source.patch` to a checkout of the commit
    reproduces the inventoried source hashes.
  - An untracked `.py` file is listed.
  - A non-repository or a missing `git` on `PATH` gives `git: null`.
  - A run inside a `git worktree` records that worktree's `HEAD`.
- **Accept:**
  - Two candidates run from one source; accepting B rewrites only B's differing defaults.
    Formatting and comments elsewhere stay byte-identical, and the verification output
    matches B's manifest.
  - Discarding A leaves the source unchanged.
  - Editing any inventoried file after the candidate ran gives `base_changed`, and the file is
    untouched.
  - A render reading randomness without a seed gives `not_reproduced`, and the original bytes
    are restored.
  - String, bool, list, negative-float and `None` defaults all round-trip.
- **Real work:** on real-chop-flip, run `bass_gain_db=-9.0`, accept it, and confirm the mix
  hash equals the known candidate hash (`cd71371…`); then revert the example with Git.
- **Fresh-Agent pass:** one fresh sonnet Agent with the updated skill produces two candidates,
  accepts one, and commits. This costs about 100k tokens and needs Paul's go-ahead.
- **Gates:** pytest, Ruff (check + format), build, and installed-CLI checks for `accept`.

## Out of scope

Batch audition and a shared base snapshot directory (receipts already identify the base; add
them only if runs racing with edits become a real problem), range/stem audition (deferred), a checkpoint cache, promotion of non-parameter expressions, automatic merge of structural
candidates, and Tactus-owned branch, commit or worktree commands.
