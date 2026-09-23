# Transactional audition keeps experiments out of production source

> 2026-09-23 · Working design decision. The Agent may audition temporary candidates without
> changing the authoritative production code; only an accepted candidate becomes a source edit.
> The formal Tactus runtime has not implemented or validated this contract yet.

## The call

The Agent needs a fast **try → listen or measure → compare → accept** loop. Audition is a
temporary execution, not a creative revision. Python production source and declared material
identities remain the source of truth; Git records accepted changes. Candidate overrides,
rendered audio, metrics, compiled graphs, and caches are disposable derived state.

For a parameterized production, the first useful form is straightforward:

```python
def render_all(*, threshold_db: float = -18.0) -> dict[str, np.ndarray]:
    ...
```

```text
production.py still says threshold_db = -18.0
    → audition(threshold_db=-20.0)  # temporary candidate
    → audition(threshold_db=-16.0)  # another candidate
    → choose -20.0
    → make one guarded source edit and verify the committed candidate
```

The override changes an **execution input**, not the default in `production.py`. A cache may
reuse unaffected computations, but a cache is not what makes the audition transactional.
The transaction boundary is that discarded candidates never become authoritative source.

## Contract to test in the product

1. Record the base source revision, declared material identities, requested range/stems,
   candidate parameters, and plugin/runtime identity in each audition receipt. An audition
   artifact must be attributable to those inputs, not silently treated as the final render.
2. Resolve each candidate against the same immutable base. A second audition cannot inherit
   the first candidate's parameter values or DSP state. Stateful processing must still use
   the correct pre-roll, latency alignment, and tail policy for the requested region.
3. Produce audio plus optional observations/metrics without rewriting production source.
   The Agent can compare candidates and discard them without a Git diff.
4. Promotion is an explicit, guarded source change: check that the base revision and target
   expression still match, write the chosen value once, then rebuild or verify the official
   output. A concurrent or manual source edit must cause a conflict, not a silent overwrite.

The initial API should cover **explicit parameters** only. Arbitrary structural Python edits
may require a disposable worktree or source snapshot; do not promise that every literal or
computed expression can be overridden safely at runtime. Agent-authored creative logic stays
in Python, and the framework owns isolation, execution, validation, and receipts.

## Why this is distinct from the alternatives

- **Edit-and-revert audition:** every rejected option temporarily changes the formal source,
  creating noisy diffs and recovery work. It remains possible with Git, but Git alone does not
  provide isolated candidate execution or enforce a clean DSP state.
- **Fast offline audition alone:** rendering faster than playback shortens waiting, but still
  leaves the Agent modifying source for each trial unless the candidate is a separate input.
- **Real-time transport:** immediate playback can be useful for humans or live input; it is not
  required to provide an Agent with a temporary, stateful audition. The present default remains
  faster-than-real-time offline execution, subject to real workflow evidence.

## Evidence and open gate

[`Stateful audition first`](2026-09-21-stateful-audition-first.md) supports offline, stateful
audition and records why the formal runtime is the next gate. The
[`Pedalboard latency/tail/state probe`](2026-09-23-pedalboard-latency-tail-state-probe.md) shows
that a small chain can replay cleanly when its state and region context are handled explicitly.
Neither probe implemented the transaction above in `tactus-code`; this document records the
design reached in the September 2026 discussion, not a completed feature.

The deciding product test is: audition two parameter candidates from one unchanged source
revision, observe distinct outputs, discard one, promote the other once, and confirm that
the formal render matches the promoted candidate while no discarded candidate changed source.
Repeat with a stateful effect and a stale-base conflict. Measure audition latency separately
from correctness; a correct but slow transaction still needs optimization.
