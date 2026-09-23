# Material identity belongs in production source

> 2026-09-21 · Design finding from the Git-diff versus declared-graph probes. This records an invariant worth preserving; it does not yet decide whether the reference is written inline or through a tracked lockfile.

## Finding

Code can be the source of truth only when every creative input that can change the result has a stable identity visible to the versioned production source.

The material bytes do not need to live in Git. Their identity does.

```diff
-kick = material("sha256:82af...")
+kick = material("sha256:c19d...")
```

This makes a sample replacement an ordinary source change. Git records the change, an agent can understand it from the diff, and identical source references resolve to identical material bytes.

## Boundary

Ignored derived state is harmless:

```text
renders/
cache/
waveform previews
content-addressed material bytes
```

Ignored mutable identity is not. A production that reads a bare mutable path such as `/Samples/kick.wav` can produce different audio from the same Git revision when that file changes in place. In that case the code is not the complete source of truth.

The intended boundary is therefore:

```text
tracked production source or lockfile
└── immutable material identity
    └── ignored content-addressed material store
```

An ignored store remains safe because an object is addressed by its content digest and cannot silently become a different object under the same identity. Missing bytes are a retrieval error, not a change in musical meaning.

## Consequence for Git diff and graphs

If replacing a material necessarily changes a tracked identity, `Git diff + agent reasoning` can observe the creative change without a persistent Arrangement Graph. The graph does not need to watch ignored files for mutation.

This does not remove every use for a compiled graph. A graph or receipt may still support packaged replay, provenance, integrity checks, and selective execution. It does remove one proposed reason for requiring the graph: discovering that an anonymously mutable sample changed outside Git.

## Import contract

An ergonomic local import may begin with a path:

```python
kick = import_audio("~/Downloads/kick.wav")
```

But the durable result of that import must be a pinned identity in versioned state:

```python
kick = material("sha256:82af...")
```

The original path can then move, disappear, or change without altering the existing production. Choosing a new file is a new creative edit and produces a new material identity.

## Current implementation gap

The current `Project.asset(path)` hashes and materializes a project-local file during each build, then records the source and material hashes in generated inputs and the build receipt. The Python source itself still names a mutable path. The same source revision can therefore resolve to different material identities if the file changes outside versioned state.

Before treating the invariant as implemented, Tactus must choose one durable authoring form:

1. Write the material digest directly into production code.
2. Keep a tracked material lockfile mapping stable source names to immutable digests.

Both preserve code-first authority if the lockfile is considered part of the versioned production source. The choice between them remains open.

## Working invariant

> Material bytes may be ignored; material identity may not be invisible. Any creative replacement must produce a versioned source diff.
