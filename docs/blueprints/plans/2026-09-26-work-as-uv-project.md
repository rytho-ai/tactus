# Every work is a uv project — plan

> Generated: 2026-09-26 · Source: Paul ("整個 tactus 都要用 uv 做環境管理"), agreed direction: each work
> is its own uv project that depends on a pinned Tactus. · Grounding: `src/tactus/cli.py`,
> `src/tactus/run.py` (`dependency_lock`, `environment`), a feasibility test in scratch `uvwork/`.

## Context

- **Tactus itself uses uv, but works do not.** A work is a folder with `song.py` that borrows
  Tactus's environment through `uv run --project <tactus>`.
- **Consequences:**
  - a work cannot add a package of its own;
  - its receipt had no lock of its own (`dependency_lock` null), which is why A7 had to add
    `environment`;
  - its environment moves whenever the Tactus checkout moves.
- **The feasibility test** (`uv init --bare`, then `uv add "tactus @ git+https://github.com/rytho-ai/tactus@<commit>"`):
  - the private repo installs, and pytimestretch resolves to its pinned commit through Tactus's
    own `tool.uv.sources`;
  - but uv did not enforce Tactus's `requires-python <3.13` and built the environment on
    Python 3.13.5, where Pedalboard's wheel crashes at import (exit 132, the known AVX-512 issue);
  - pinning the work to `>=3.12,<3.13` fixed it.

  Details like this belong in one place, not in every Agent's memory.

## Resolved choices

- **`tactus init DIR`** (new command). It creates the work folder (it must not exist or must be
  empty) with:
  - `pyproject.toml`:
    - `name` derived from the folder name;
    - `requires-python` copied from the running Tactus's own metadata (today `>=3.12,<3.13`);
    - `dependencies = ["tactus"]`;
    - `[tool.uv.sources] tactus = {git = <url>, rev = <commit>}`;
  - `.gitignore` with `runs/`, `.venv/` and `__pycache__/`;
  - and then runs `uv lock`, recording `uv` as the tool it needs.

  It does not write `song.py`: the work's content is the Agent's.
- **Which Tactus.** By default, the running Tactus's own origin, read from `package_sources`
  logic (`direct_url.json`):
  - installed from Git → that URL and commit;
  - an editable checkout → that checkout's `origin` remote URL and `HEAD`, only when the checkout
    is clean and `HEAD` is on the remote. Otherwise `init` fails with a clear message.

  `--tactus-path PATH` pins an editable path dependency for development. `--tactus URL@REV` pins
  an explicit source.
- **Running a work.** Inside the work: `uv run tactus run song.py --out runs/NAME`. The receipt's
  `dependency_lock` is then the work's own `uv.lock`, which pins Tactus and every package.
  `uv add PACKAGE` adds a package to the work only.
- **Older works** without a `pyproject.toml` keep running as before; nothing is refused.
- **The skill:** a new step 0 (create the work with `tactus init`), running inside the work,
  `uv add` for extra packages, and a shorter rebuild paragraph: check out the work's commit, then
  `uv sync --frozen`.

## Approach

1. `cli.py` and a small `init.py` (a module that owns work scaffolding): write the files, resolve
   the Tactus source, and run `uv lock` (`tool("uv")` is not a render tool; just use
   `shutil.which` and fail clearly).
2. Reuse the PEP 610 reading from `run.py` (`_package_sources`); move it to a shared helper
   rather than duplicate it.
3. Skill and README; design.md's execution section.
4. Tests:
   - scaffolding content, including the `requires-python` pin;
   - refusal on a non-empty folder;
   - Tactus source resolution for Git, editable-clean and editable-dirty cases (monkeypatched
     metadata, a temporary Git repo);
   - `--tactus-path` and `--tactus`;
   - `uv lock` is invoked (mocked in unit tests), plus one integration test marked slow that
     really creates, syncs and runs a tiny work with `--tactus-path` pointing at this checkout.

## Verification

- pytest, Ruff, and a real `tactus init` → `uv sync` → `uv run tactus run` in scratch against the
  pushed Tactus commit. Check that the receipt's `dependency_lock` is the work's lock.
- A fresh-Agent probe: a new Agent, given only the skill, creates and renders a short work from
  nothing and adds one extra package. Pass: it ends on Python 3.12 with a working render, its
  receipt names the work's own lock, and it needed nothing outside the skill.

## Out of scope

Publishing Tactus to an index, a work template with music, migrating existing dogfood and probe
works, and managing non-Python tools (`sfizz_render`) with uv.
