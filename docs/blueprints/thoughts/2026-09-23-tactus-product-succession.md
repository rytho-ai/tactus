# Tactus product succession

> 2026-09-23 · **Status: in force** · The Python-first repository formerly called `tactus-code` is the active Tactus product; the previous implementation was preserved as `tactus-legacy` and renamed `tactus-daw` on 2026-09-24.

## The call

Paul approved one active product and the ordered handoff: preserve and merge completed legacy
work into main, tag that implementation, rename its repository, then give the code-first product
the `tactus` name. This supersedes [the parallel-workstream decision](2026-09-23-two-repo-workstream-boundary.md).

The active repository, distribution, Python import, and CLI use `tactus`. The implementation
remains an early prototype; the name does not claim parity with the legacy feature set.
Its first version under the new identity is `0.1.0`. Old `tactus-code` consumers must migrate
their imports and commands. Existing format-v1 compiled artifacts remain readable.

## Legacy role

`rytho-ai/tactus-daw` preserves the old Git history and completed session facade. The
[handoff commit](https://github.com/rytho-ai/tactus-daw/commit/086aeb8a7d9910f8b8671859e38d7d69dc2fc79c)
identifies the preserved implementation. Further legacy work requires
an explicit request; its backlog is historical reference, not the active product roadmap.
At handoff, the old package retained its historical `tactus` import. The 2026-09-24 identity
rename changed its distribution and CLI to `tactus-daw` and its import to `tactus_daw`;
persisted document identifiers and machine-local asset paths remain historical.

## Authoring direction

Python source and declared inputs remain the creative source of truth. Temporal helpers are
optional and global BPM is optional. Existing compiled arrangement files are implementation
artifacts; a broader graph model is not a required product task. Revisit internal metadata only
when a concrete consumer demonstrates a need.

## Evidence

The handoff plan records checks and repository operations in
[`Tactus product handoff`](../plans/2026-09-23-tactus-product-handoff.md). Legacy tests passed
1,983 cases with four skipped before the merge; Ruff passed. Earlier research remains available
in both repositories without being silently promoted into new product requirements.
