# omegaclaw-deontic

A drop-in installer that adds a defeasible + deontic + temporal reasoning stack to
a stock [OmegaClaw-Core](https://github.com/asi-alliance/OmegaClaw-Core) agent. It
copies the deontic libraries into your clone and makes two small, reversible edits
to register them, so the agent gains normative reasoning skills without you editing
core files by hand. Everything it does is undone by `--uninstall`.

The same code is also available as the upstream PR series (deontic-core and its
layers); this bundle packages it so anyone running OmegaClaw-Core can add it locally
whether or not those PRs land.

## What it adds

The full stack, in one install. Where OmegaClaw's NAL and PLN grade *how much* a
fact is believed, this stack answers *what defeasibly holds* and *what is obligated,
permitted, or forbidden*.

| Layer | Files | Posture after a default install |
|---|---|---|
| Deontic engine | `lib_deontic.metta`, `src/deontic/**` | loaded; reasons via `dl-run` and friends |
| Task orchestration | `lib_directive.metta`, `src/directive/**` | loaded; defeasible plans over task state |
| Agent skills | `src/skills_deontic.metta` | loaded and advertised to the LLM |
| NAL/PLN bridge | `src/integration/nal.metta` | loaded; called explicitly, no automatic hook |
| Policy guardrail | `src/policy_guard.metta` | loaded but inert; opt in with `--enable-guardrail` |
| Semantic retrieval | `src/integration/semantic.metta` | off by default; opt in with `--enable-semantic` |

The engine runs on either of two interchangeable backends that yield identical
conclusions: a first-argument-indexed Prolog kernel (`prolog`, the default) and an
atomspace-native MeTTa engine (`native`). Select per run with `(dl-engine! native)`
or `OMEGACLAW_DL_ENGINE`.

## Requirements

- A clone of OmegaClaw-Core running on [PeTTa](https://github.com/trueagi-io/PeTTa).
- Python 3 (for the installer).
- SWI-Prolog, which OmegaClaw-Core already needs. Verified here against 9.2.9.

## Install (source clone)

From the bundle directory:

```
./install.sh /path/to/PeTTa/repos/OmegaClaw-Core
```

Useful flags (all pass through to `installer/install.py`, see `--help`):

- `--dry-run` shows the plan and writes nothing.
- `--enable-guardrail` routes the agent loop through the deontic guard (still inert until you supply a policy, see below).
- `--enable-semantic` enables FAISS-based semantic retrieval; this pulls and builds `faiss_ffi`, so it needs network and a C/C++ toolchain.
- `--skill-registry` refactor getSkills into an open catalogue so this and future plugins register skills without editing a shared list (see "The open skill registry" below).
- `--minimal` skips `tests/` and `docs/` (used by the Docker build).
- `--uninstall` reverts everything the install did.

## Install (Docker)

The prebuilt image bakes the clone at `/PeTTa/repos/OmegaClaw-Core`, so the plugin
goes in as a build-time overlay. From the bundle root:

```
docker build -f docker/Dockerfile -t omegaclaw-deontic:latest .
```

Then run it through the normal launcher by pointing `-d` at your image:

```
scripts/omegaclaw -d omegaclaw-deontic:latest start -t telegram ...
```

Enable optional layers at build time with `--build-arg FLAGS="--enable-guardrail"`.
The installer runs during the build, so the runtime security posture (dropping to
`nobody`, tmpfs, scrubbed environment) is unchanged.

## Using it

After install the agent is told about these skills and calls them with a quoted path
to a theory or plan file:

- `deontic-conclude path` defeasible conclusions of a theory, tagged `+D/-D` (definite) and `+d/-d` (defeasible).
- `deontic-norms path` conclusions under the Standard Deontic Logic closure, where O, P, F interact and `F p = O not p`.
- `deontic-conflicts path` unresolved deontic dilemmas, where `O p` and `O not p` are both applicable and neither is out-ranked.
- `directive-next path` the actionable tasks in a plan right now.
- `directive-status path`, `directive-board path`, `directive-summary path` task-state views of a plan.

A theory or plan is an ordinary `.metta` file. The forms are `(given p)` for a fact,
`(always L a b)` / `(normally L a b)` / `(except L a b)` for strict / defeasible /
defeater rules, `(prefer L1 L2)` for superiority, and `(must p)` / `(forbidden p)` /
`(permitted p)` for the deontic operators. See `examples/deontic/` and
`docs/reference-lib-deontic.md` for the full surface, including temporal (Event
Calculus, Allen relations, deadlines) and trust. The directive layer and its richer
programmatic surface are documented in `docs/reference-lib-directive.md`.

## The guardrail (opt-in)

`--enable-guardrail` makes the agent loop dispatch through `guarded-eval` instead of
`eval`. That alone changes nothing: `deonticGuardEnabled` defaults to `False`, so
`guarded-eval` is exactly `eval`. To actually govern actions, set
`(deonticGuardEnabled) True` and point `(policyPath)` at a deontic policy theory (see
`examples/deontic/policy.metta`). With a policy in force, an action the policy
forbids is blocked before it runs. This is normative reasoning over what the agent
*ought* to do, and is separate from the OS-level sandbox in `profile/policy.yaml`,
which restricts what the process *can* do.

## The open skill registry (opt-in)

By default the installer advertises the deontic skills by splicing catalogue lines
into OmegaClaw's `getSkills` list. That list is closed, so each addition edits a
shared list. Passing `--skill-registry` instead refactors `getSkills` into an open
catalogue,

```metta
(= (skill-doc) (superpose (;INTERNAL: ...core lines...)))
(= (getSkills) (collapse (skill-doc)))
```

and registers each deontic skill as its own equation, for example

```metta
(= (skill-doc) "- Defeasible + deontic reasoning over a theory file: deontic-conclude path")
```

Now any module advertises a skill to the agent by adding a `(= (skill-doc) "...")`
equation, with no edit to a shared list. With no equations added, `getSkills`
returns the original catalogue byte-for-byte, so the change is backward compatible,
and `--uninstall` restores the original `skills.metta`. This is the same change
proposed upstream; the flag lets you adopt it locally whether or not it lands there.

## Running under the sandbox

The directive layer keeps plan state by appending claims blocks to the plan `.metta`
file, so the plan file is its own durable, auditable state with no external store.
Under the OpenShell filesystem policy (`profile/policy.yaml`), the directory holding
your theory and plan files must be readable, and writable for any plan the agent
edits. Place them under a permitted path or widen the policy accordingly.

## Uninstall

```
./install.sh /path/to/OmegaClaw-Core --uninstall
```

This reads the install receipt (`.omegaclaw-deontic-receipt.json`), strips the two
managed blocks, reverts the optional loop route, removes the copied files, and prunes
the directories it created. The two patched core files return byte-for-byte to their
pre-install state.

## Compatibility

Tested against upstream OmegaClaw-Core at `origin/main` commit `519c342`. The
installer does not assume a fixed file layout: it anchors the import block on the
`lib_pln` import line and finds the `getSkills` splice point with a paren-balanced
scan. If a future upstream moves either anchor, the install aborts with a clear
message and writes nothing, rather than producing a half-patch.

## Verified

- The deontic golden suite passes 10/10 (93 checks) under SWI-Prolog 9.2.9, run from a freshly installed clone.
- Install is idempotent; `--uninstall` restores the patched files byte-for-byte and leaves the clone with a clean `git status`.
- The optional `--skill-registry` mode refactors getSkills and registers the deontic skills as `(= (skill-doc) ...)` equations; verified under PeTTa that the installed getSkills renders the original catalogue plus the deontic and directive skills, with byte-exact uninstall.
- The agent-facing skills run end to end from an installed clone, including the real `(deontic-conclude "path")` quoted-string convention, plus `deontic-norms` and `directive-status`.
- The Docker overlay builds clean: a `docker build` pulls `singularitynet/omegaclaw:latest`, runs the installer in-image (31 functional files under `--minimal`, both core patches applied at `/PeTTa/repos/OmegaClaw-Core`), and produces `omegaclaw-deontic:latest`.

## Layout

```
omegaclaw-deontic/
  install.sh              wrapper around the installer
  VERSION                 bundle version
  installer/install.py    copy + managed-block patch + receipt + uninstall
  payload/                the deontic files, mirroring the clone layout
  docker/Dockerfile       build-time overlay on the stock image
  README.md  DESIGN.md
```
