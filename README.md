# omegaclaw-deontic

omegaclaw-deontic gives an OmegaClaw agent a reasoning engine for two questions its
belief engines (NAL and PLN) do not answer: what follows by default when rules
conflict, and what is obligated, permitted, or forbidden. On top of that engine it
adds a task orchestrator, so the agent can also plan and coordinate dependency-ordered
work. Everything installs onto a stock OmegaClaw-Core clone and reverts cleanly.

## Defaults and exceptions

A general rule can have a more specific exception that overrides it. The classic case
is Tweety the penguin: birds normally fly, penguins are birds, but penguins normally
do not fly, and the penguin rule is the more specific one.

```metta
(given bird) (given penguin)
(normally r1 bird flies)
(normally r2 penguin (not flies))
(prefer r2 r1)                 ; when they collide, the penguin rule wins
```

Run it:

```metta
!(import! &self (library OmegaClaw-Core lib_deontic))
!(dl-run (dl-path examples/deontic/penguin.metta))
; => ... (pd (lit neg none none flies ())) ... (nd (lit pos none none flies ())) ...
```

Read `(pd (lit neg none none flies ()))` as "defeasibly proven: not flies", and
`(nd (lit pos none none flies ()))` as "defeasibly refuted: flies". Every conclusion
carries a tag for how firmly it holds. `pD` and `nD` are definite, proven or refuted
from facts and strict rules alone; `pd` and `nd` are defeasible, where a rule fired and
every rule against it was beaten or outranked. Add a stronger fact later and a
defeasible conclusion can be retracted, which is the whole point: conclusions a new
fact can take back.

Rules come in three strengths. A strict rule (`always`) holds whenever its body does. A
defeasible rule (`normally`) holds unless something defeats it. A defeater (`except`)
proves nothing on its own, it only blocks the opposite. `(prefer A B)` says rule A
outranks rule B when the two collide.

## Obligations, permissions, prohibitions

The same engine reasons about norms. You write `(must p)` for an obligation,
`(forbidden p)` for a prohibition, `(permitted p)`, and the engine knows that
`forbidden p` is the same as `must (not p)`. While a request is unconfirmed, say,
deleting it is forbidden and replying is required:

```metta
(given unconfirmed)
(normally pr1 unconfirmed (forbidden delete))
(normally pr2 unconfirmed (must reply))
```

`(dl-run-deontic <path>)` closes a theory under those operators, and
`(deontic-compliance <path>)` tells you whether a course of action complies, violates,
or leaves a duty open. Two harder cases are handled rather than ignored. A
contrary-to-duty obligation is what becomes required once you have already broken a
duty (you should not delete it, but if you did, you must now log the deletion); the
engine compiles those reparation chains. And when two norms genuinely conflict with no
way to rank them, it reports the dilemma instead of quietly picking a side:

```metta
(given a)
(normally r1 a (must p))
(normally r2 a (forbidden p))     ; O p and O not-p, nothing to break the tie
```

```metta
!(deontic-dilemmas (dl-path examples/deontic/deontic_dilemma.metta))
; => ((lit pos O none p ()))      the obligation on p is flagged as unresolved
```

## Reasoning over time

Obligations and facts often hold only for a while. The engine includes an Event
Calculus, where an event initiates or terminates a fluent and the fluent holds at a
time if it was started before and not stopped since; the thirteen Allen relations
between intervals (before, meets, overlaps, during, and the rest); and deadlines in two
readings. An achievement deadline must be met by some time; a maintenance deadline must
hold across an interval.

```metta
(deadline (must pay) achieve 0 30 fine)            ; pay by t=30, else the fine applies
(deadline (forbidden trespass) maintain 0 100 penalty)
(given (during pay 25 25))                          ; paid at t=25, in time
```

`(dl-run-at <path> <time>)` reasons as of a reference time, so you can ask what was
obligated, met, or missed at any point.

## Trust

When facts come from sources of differing reliability, the engine carries a
weakest-link trust value along each proof, so a conclusion is only as trustworthy as
the least trustworthy fact it rests on. You give sources weights with `(trusts src v)`
and gate conclusions with `(threshold n v)`.

## It is also a task orchestrator

The directive layer is where it stops being only a logic engine. It treats a plan of
work as a defeasible theory: tasks are facts, and a readiness rule says a task becomes
ready once its dependencies are done. The engine then derives what you can work on right
now. Here is the core of a four-task plan where models and auth have no dependencies,
crud waits on models, and tests waits on crud and auth (the full plan, with agents and
assignment rules, is `tests/deontic/fixtures/basic-tasks.metta`):

```metta
(given task-auth) (given task-models) (given task-crud) (given task-tests)
(given no-deps-auth) (given no-deps-models)
(normally r-models (and task-models no-deps-models) ready-models)
(normally r-auth   (and task-auth   no-deps-auth)   ready-auth)
(normally r-crud   completed-models ready-crud)            ; crud needs models done first
(normally r-tests  (and completed-crud completed-auth) ready-tests)
```

Ask what the state is, what to do next, and for a board view:

```metta
!(import! &self (library OmegaClaw-Core lib_directive))
!(directive-status (dl-path plan.metta))
; => (status (tasks (auth crud models tests)) (ready (auth models))
;            (claimed ()) (blocked ()) (upstream-blocked ()) (completed ()))
!(directive-next (dl-path plan.metta))
; => (next-actions ((assign auth coder assign-to-auth-coder)
;                   (assign auth reviewer assign-to-auth-reviewer)
;                   (assign models coder assign-to-models-coder)))
!(directive-board (dl-path plan.metta))
; => (board (backlog (crud tests)) (ready (auth models)) (in-progress ()) (blocked ()) (done ()))
```

auth and models are ready because they have no open dependencies; crud and tests sit in
the backlog until theirs clear. The lifecycle is part of the same logic.
`(directive-claim plan task agent False)` and `(directive-complete plan task agent)`
append a small block of facts and rules to the plan file, each outranking the last, so
the most recent action wins and is still reversible, and completing a task's
dependencies unlocks its dependents on the next run. Blocking propagates through the
dependency graph: block one task and its descendants are marked `upstream-blocked`, so a
disruption is visible downstream. Because every action is appended to the plan `.metta`
file, the plan is its own durable, auditable history with no outside database, and a
process-mining layer can read that history back as an event log and recover the rules
from it.

## The skills your agent gets

After install the agent is told about these and calls each with a quoted path to a
theory or plan file:

- `deontic-conclude path` the defeasible conclusions of a theory.
- `deontic-norms path` the conclusions under the deontic closure.
- `deontic-conflicts path` the unresolved deontic dilemmas.
- `directive-next path`, `directive-status path`, `directive-board path`, `directive-summary path` the orchestration views above.

So a user can hand the agent a theory and ask a normative question, and the agent
answers by running the engine, for example `(deontic-conclude "examples/deontic/penguin.metta")`.

## Install

You need a clone of OmegaClaw-Core running on [PeTTa](https://github.com/trueagi-io/PeTTa),
Python 3, and SWI-Prolog (which OmegaClaw already needs; tested against 9.2.9). From this
directory:

```sh
./install.sh /path/to/PeTTa/repos/OmegaClaw-Core
```

The installer copies the deontic files into the clone and makes two small, reversible
edits to register them. `--uninstall` puts everything back, and `--dry-run` shows the
plan first. For the prebuilt image, build the overlay and point the launcher at it:

```sh
docker build -f docker/Dockerfile -t omegaclaw-deontic:latest .
scripts/omegaclaw -d omegaclaw-deontic:latest start -t telegram ...
```

## Two engines under the hood

The same theory runs on either of two backends that give identical conclusions:
`prolog`, a fast first-argument-indexed kernel that is the default, and `native`, an
atomspace-native MeTTa engine where every rule and derived atom stays an inspectable
atom. Switch per run with `(dl-engine! native)` or `OMEGACLAW_DL_ENGINE=native`. Native
grounding (instantiating variable rules over data) runs a few times slower than the
Prolog kernel, so prolog is the default for data-heavy theories while native is free on
propositional plans and easier to inspect.

## Options

The semantic layer adds embedding-based retrieval over concluded facts, but it needs the
`faiss_ffi` native build, so it is off unless you pass `--enable-semantic`.

By default the installer advertises the deontic skills by splicing lines into
OmegaClaw's `getSkills` list. Passing `--skill-registry` instead refactors that list
into an open catalogue, `(= (getSkills) (collapse (skill-doc)))`, and registers each
skill as its own `(= (skill-doc) "...")` equation, so you or any other module can add
skills without editing a shared list. With nothing added it returns the original
catalogue unchanged, and uninstall restores the file.

The guardrail lets the agent check an action against a policy before it runs it. You
write the policy as a deontic theory of what is forbidden and what is obligatory, like
the one in `examples/deontic/policy.metta` that forbids deleting an unconfirmed item and
requires replying to it. Pass `--enable-guardrail` to route the agent's actions through
the policy, then turn it on by setting `(deonticGuardEnabled) True` and pointing
`(policyPath)` at your policy. Until you do, it stays off and the agent runs exactly as
before. Once on, a forbidden action is blocked before it happens. This governs what the
agent ought to do, which is separate from the OS sandbox in `profile/policy.yaml` that
limits what the process is allowed to do at all.

## Under the sandbox

The directive layer writes its claim and completion blocks back into the plan `.metta`
file, so under the OpenShell policy in `profile/policy.yaml` the directory holding your
theories and plans has to be readable, and writable for any plan the agent edits. Put
them under a permitted path or widen the policy.

## Uninstall

```sh
./install.sh /path/to/OmegaClaw-Core --uninstall
```

This reads the install receipt, strips the two managed edits, removes the copied files,
and restores the patched files byte-for-byte.

## Compatibility and what's verified

Tested against upstream OmegaClaw-Core at `origin/main` commit `519c342`. The installer
finds its anchors by content rather than line number and aborts cleanly if upstream has
moved them, so it never leaves a half-patch.

The deontic golden suite passes 10 of 10 (93 checks) under SWI-Prolog 9.2.9 from a
freshly installed clone. Install is idempotent, and `--uninstall` restores the patched
files byte-for-byte with a clean `git status`. The agent skills run end to end from an
installed clone, the `--skill-registry` mode renders the same catalogue plus the new
skills, and the Docker overlay builds and installs in-image.

## Layout

```
install.sh              wrapper around the installer
installer/install.py    copy + reversible patch + receipt + uninstall
payload/                the deontic files, mirroring the clone layout
docker/Dockerfile       build-time overlay on the stock image
payload/docs/deontic/   the engine's own overview and references
```

More detail lives in `DESIGN.md` (how the installer works) and in
`payload/docs/deontic/README.md` and `payload/docs/reference-lib-*.md` (the engine and
directive APIs).
